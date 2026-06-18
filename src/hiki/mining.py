"""Tier1 全书深挖（map-reduce）。

取代'开头4万字切片'：扫全本 → 分块并发抽取 → 归并成厚 bible + 全局场景池
→ 显式场景打分筛选 → REDUCE 后源分级。深度(人/承重/爽点素材)在 reduce 步从全书回收。
LLM 判断走 gate._safe_json 健壮解析（DeepSeek 思考模式易截断）。
"""
from __future__ import annotations
import asyncio
import json
import re
from collections import Counter
from . import prompts, gate
from .client import Client

_CH_RE = re.compile(r"^\s*第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章节回]", re.M)


# ============ ① 分块（按章界，窗间重叠防断裂）============

def chunk_by_chapters(clean: str, n_chunks: int = 12, overlap_ch: int = 1) -> list[str]:
    """按章界把全本聚成 ~n_chunks 个窗口，相邻窗重叠 overlap_ch 章。"""
    pos = [m.start() for m in _CH_RE.finditer(clean)]
    if len(pos) <= 1:
        return [clean]
    pos.append(len(clean))
    n_ch = len(pos) - 1
    n_chunks = max(1, min(n_chunks, n_ch))
    per = max(1, n_ch // n_chunks)
    chunks = []
    start_ch = 0
    while start_ch < n_ch:
        end_ch = min(n_ch, start_ch + per)
        lo = pos[max(0, start_ch - (overlap_ch if start_ch else 0))]
        hi = pos[end_ch]
        chunks.append(clean[lo:hi].strip())
        start_ch = end_ch
    return [c for c in chunks if c]


# ============ ② MAP：并发分块抽取 ============

async def _extract_one(cli: Client, chunk: str, idx: int) -> dict:
    sys_p, usr_t = prompts.EXTRACT_CHUNK
    raw = await cli.complete("chunk_extract", sys_p, usr_t.format(chunk=chunk[:60000]),
                             json_mode=True, max_tokens=8000, temperature=0.3)
    r = gate._safe_json(raw) or {}
    # 标记来源窗序，供场景排序
    for sc in r.get("scene_cards", []):
        sc["_chunk"] = idx
    return r


async def map_extract(cli: Client, chunks: list[str]) -> list[dict]:
    """K 窗并发抽取（你的硬约束：最大化协程）。"""
    return await asyncio.gather(*[_extract_one(cli, c, i) for i, c in enumerate(chunks)])


async def _extract_life_one(cli: Client, chunk: str) -> dict:
    sys_p, usr_t = prompts.LIFE_EVENTS
    raw = await cli.complete("chunk_extract", sys_p, usr_t.format(chunk=chunk[:60000]),
                             json_mode=True, max_tokens=1500, temperature=0.2)
    r = gate._safe_json(raw)
    # flaky LLM 偶尔直接吐裸数组 [...] 而非 {"life_events":[...]} → 容忍两种,绝不崩整本
    events = r if isinstance(r, list) else (r.get("life_events") or [] if isinstance(r, dict) else [])
    return {"life_events": [e for e in events if isinstance(e, dict)]}


async def extract_life_events_pass(cli: Client, chunks: list[str]) -> list[dict]:
    """方案B:专用轻 prompt 只抽生死事件,与主 map_extract 并发(独立细窗 life_chunks,见 mine_book n_life;
    flash+轻prompt 成本仍低)。返回按窗序的 [{"life_events":[...]}],喂 collect_life_events。
    实测召回 > 多任务 EXTRACT_CHUNK(后者已撤回 life_events;细窗治桑念复活漏抽)。"""
    return await asyncio.gather(*[_extract_life_one(cli, c) for c in chunks])


# ============ ③ REDUCE 准备：确定性归并 ============

def merge_scenes(chunk_results: list[dict]) -> list[dict]:
    """确定性合并场景卡：按窗序保序，去掉空摘要。全局场景池。"""
    out = []
    for r in chunk_results:
        for sc in r.get("scene_cards", []):
            if (sc.get("summary") or "").strip():
                out.append(sc)
    return out


def collect_observations(chunk_results: list[dict]) -> str:
    """把所有角色观察按名字聚合成文本（别名归一交给 REDUCE 的 LLM 做）。"""
    by_name: dict[str, list[dict]] = {}
    for r in chunk_results:
        for ob in r.get("char_observations", []):
            nm = (ob.get("name") or "").strip()
            if nm:
                by_name.setdefault(nm, []).append(ob)
    lines = []
    for nm, obs in by_name.items():
        did = "；".join(o.get("did", "") for o in obs if o.get("did") and o["did"] != "无主动行动")[:400]
        want = "；".join(o.get("wanted", "") for o in obs if o.get("wanted"))[:300]
        powers = [o.get("power", "") for o in obs if o.get("power")]
        rels = [f"{p[0]}→{p[1]}" for o in obs for p in (o.get("relation_beats") or []) if len(p) == 2]
        voice = next((o.get("voice", "") for o in obs if o.get("voice")), "")
        lines.append(f"【{nm}】出现{len(obs)}次 | 主动:{did or '少'} | 想要:{want or '?'} | "
                     f"实力:{'/'.join(powers[:4])} | 关系:{'、'.join(rels[:5])} | 腔调:{voice}")
    return "\n".join(lines)


def collect_facts(chunk_results: list[dict]) -> str:
    """归并各窗 fact_observations → 每个事实项的多值+频次(冲突原样留给 REDUCE 裁成单值)。
    M1.5 ②: 数值脊柱的原料——彩礼/年龄/婚龄/失散年数等应单值设定,各窗可能给冲突值。"""
    by_item: dict[str, Counter] = {}
    for r in chunk_results:
        for pair in r.get("fact_observations") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                item, val = str(pair[0]).strip(), str(pair[1]).strip()
                if item and val:
                    by_item.setdefault(item, Counter())[val] += 1
    lines = []
    for item, vals in by_item.items():
        shown = "、".join(f"{v}(×{c})" for v, c in vals.most_common(6))
        flag = " ⚠多值冲突,需裁单值" if len(vals) > 1 else ""
        lines.append(f"【{item}】{shown}{flag}")
    return "\n".join(lines) if lines else "(无)"


def collect_places(chunk_results: list[dict]) -> str:
    """归并各窗 places → 频次表(供 REDUCE 归并成规范名,治地名/公司名/城名横跳)。"""
    c: Counter = Counter()
    for r in chunk_results:
        for p in r.get("places") or []:
            if isinstance(p, str) and p.strip():
                c[p.strip()] += 1
    return "、".join(f"{p}(×{n})" for p, n in c.most_common(40)) if c else "(无)"


def collect_life_events(chunk_results: list[dict]) -> dict:
    """跨窗归并人物生死事件 → 生死弧。chunk_results 按窗序(=时间序)排列。
    有死亡且其后(含同窗)有复活 → dies_returns;只死 → dies_final;只复活无死亡 → 不建弧(噪声)。
    供 mine 冻进 bible['life_arcs'],喂和解感知生死门(audit.reconcile_revival)。"""
    ev: dict = {}
    for wi, r in enumerate(chunk_results):
        if not isinstance(r, dict):
            continue
        for e in (r.get("life_events") or []):
            who = (e.get("who") or "").strip()
            t = e.get("type")
            if not who or t not in ("死亡", "复活"):
                continue
            d = ev.setdefault(who, {"deaths": [], "returns": [], "death_q": "", "return_q": ""})
            if t == "死亡":
                d["deaths"].append(wi)
                d["death_q"] = d["death_q"] or (e.get("quote") or "")[:30]
            else:
                d["returns"].append(wi)
                d["return_q"] = d["return_q"] or (e.get("quote") or "")[:30]
    arcs = {}
    for who, d in ev.items():
        if not d["deaths"]:
            continue
        fate = "dies_returns" if (d["returns"] and max(d["returns"]) >= min(d["deaths"])) else "dies_final"
        arcs[who] = {"fate": fate, "death_q": d["death_q"], "return_q": d["return_q"],
                     "deaths": sorted(d["deaths"]), "returns": sorted(d["returns"])}
    return arcs


def scene_stats(scenes: list[dict]) -> str:
    c = Counter(sc.get("scene_type", "其它") for sc in scenes)
    return "、".join(f"{k}×{v}" for k, v in c.most_common())


# ============ ③ REDUCE：厚 bible（深度诞生）============

def _bible_ok(b: dict) -> bool:
    """有效厚 bible：有主角名 + 中心冲突/设定其一。防 flaky 空响应被当真。"""
    if not isinstance(b, dict):
        return False
    return bool((b.get("protagonist") or {}).get("name")) and \
        bool(b.get("central_conflict") or b.get("setting"))


async def reduce_bible(cli: Client, chunk_results: list[dict], scenes: list[dict], tries: int = 3) -> dict:
    """归并厚 bible。pro 思考模式偶发吐空/截断 → 重试（实测重试即成功）。"""
    sys_p, usr_t = prompts.REDUCE_BIBLE
    obs = collect_observations(chunk_results)
    usr = usr_t.format(observations=obs[:40000], fact_obs=collect_facts(chunk_results)[:8000],
                       place_obs=collect_places(chunk_results)[:4000], scene_stats=scene_stats(scenes))
    best = {}
    for t in range(tries):
        raw = await cli.complete("reduce", sys_p, usr,
                                 json_mode=True, max_tokens=20000, temperature=0.4 + 0.1 * t)
        b = gate._safe_json(raw) or {}
        if _bible_ok(b):
            return b
        if len(json.dumps(b, ensure_ascii=False)) > len(json.dumps(best, ensure_ascii=False)):
            best = b                       # 留最完整的一版兜底
    return best


# ============ 显式场景重要度打分（决策1：显式打分筛选）============

async def score_scenes(cli: Client, scenes: list[dict], keep_n: int) -> list[dict]:
    """给全局场景打分，选 top keep_n 进 60 章（其余可压成过渡/删）。"""
    if len(scenes) <= keep_n:
        return scenes
    listed = "\n".join(
        f"{i}. [{sc.get('scene_type','')}/{sc.get('importance','')}] {sc.get('summary','')[:60]}"
        for i, sc in enumerate(scenes))
    sys_p, usr_t = prompts.SCENE_SCORE
    raw = await cli.complete("scene_score", sys_p, usr_t.format(scenes=listed),
                             json_mode=True, max_tokens=8000, temperature=0.2)
    r = gate._safe_json(raw) or {}
    score_map = {s["i"]: s.get("score", 0) for s in r.get("scores", []) if isinstance(s.get("i"), int)}
    ranked = sorted(range(len(scenes)),
                    key=lambda i: score_map.get(i, scenes[i].get("importance") == "高" and 70 or 40),
                    reverse=True)
    keep_idx = sorted(ranked[:keep_n])          # 保留原时间序
    return [scenes[i] for i in keep_idx]


# ============ 源暗黑预扫（分级阶段抽样扫源文,省得生成完¥5-6才values_reject）============

async def dark_prescan(cli: Client, clean: str, n_win: int = 6, win_chars: int = 12000) -> dict:
    """均匀采样 n_win 个源文窗口扫'残忍当爽点'。返回 {ratio, issues}。
    bible 级 content_flag 已实证失灵(读设定看不见),只有读正文可靠 → 在源头就读。"""
    if len(clean) <= win_chars:
        wins = [clean]
    else:
        step = (len(clean) - win_chars) // max(1, n_win - 1)
        wins = [clean[i * step:i * step + win_chars] for i in range(n_win)]
    sys_p, usr_t = prompts.SOURCE_DARK_SCAN

    async def _vote(w: str, t: int) -> dict:
        for r2 in range(2):                      # retry-on-empty
            raw = await cli.complete("chunk_extract", sys_p, usr_t.format(text=w),
                                     json_mode=True, max_tokens=300,
                                     temperature=0.15 + 0.1 * t + 0.05 * r2)
            r = gate._safe_json(raw) or {}
            if "dark" in r:
                return r
        return {}

    async def _one(w: str) -> dict:
        votes = await asyncio.gather(*[_vote(w, t) for t in range(3)])   # 3票多数决:单票判暗黑噪声大
        darks = [v for v in votes if v.get("dark") is True]
        return darks[0] if len(darks) >= 2 else {}
    res = await asyncio.gather(*[_one(w) for w in wins])
    flags = [(r.get("issue") or "暗黑爽点") for r in res if r.get("dark") is True]
    return {"ratio": round(len(flags) / max(1, len(wins)), 2), "issues": flags[:4]}


# ============ ② 决策2：REDUCE 后源分级 ============

_GRADE_ORDER = ("S", "A", "B", "C", "D", "Q")
_GRADE_MODE = {"S": "保真压缩", "A": "保真压缩", "B": "强化改写",
               "C": "类型化重构", "D": "概念级重启", "Q": "拒收"}


def _cap_grade(g: dict, cap: str, why: str) -> None:
    """确定性降级到 cap（只降不升），mode 跟着档位走。"""
    if _GRADE_ORDER.index(g.get("grade") or "B") < _GRADE_ORDER.index(cap):
        g["grade"], g["mode"] = cap, _GRADE_MODE[cap]
        g["reason"] = (f"{why}→降{cap}: " + g.get("reason", ""))[:60]


async def grade_source(cli: Client, bible: dict, dark: dict | None = None) -> dict:
    sys_p, usr_t = prompts.SOURCE_GRADE
    brief = json.dumps({k: bible.get(k) for k in
                        ("central_conflict", "escalation_ladder", "setting", "voice")},
                       ensure_ascii=False)
    prot = bible.get("protagonist", {})
    brief += (f"\n主角弧:{prot.get('arc','')} | 主目标:{prot.get('goal','')}/{prot.get('goal_internal','')}"
              f"\n内在转变节点:{json.dumps(prot.get('arc_milestones') or [], ensure_ascii=False)}"
              f" | 主动事例:{len(prot.get('agency_examples') or [])}条")
    g = None
    for t in range(3):                               # 重试(配合 client 空响应重试),pro 偶发截断
        raw = await cli.complete("source_grade", sys_p, usr_t.format(bible=brief),
                                 json_mode=True, max_tokens=2500, temperature=0.3 + 0.1 * t)
        cand = gate._safe_json(raw)
        if isinstance(cand, dict) and cand.get("grade"):
            g = cand
            break
    if g is None:                                    # A5: 评级无法解析→不铸造可交付的B(否则Q源拿免费全本¥draft);失败即拒,省钱不裸奔
        return {"grade": "Q", "mode": "拒收", "reason": "源评级多次解析失败,无法判级→拒收(防裸奔出货)"}
    # 人物弧硬判据('人'维是源决定的,选源即选分): 无弧工具人→最高C,表面弧→最高B
    arc = (g.get("protagonist_arc") or "").strip()
    if arc.startswith("无"):
        _cap_grade(g, "C", "主角无弧(工具人)")
    elif arc.startswith("表面"):
        _cap_grade(g, "B", "主角弧表面")
    # 价值观红线: 源暗黑预扫(读正文,可靠)优先于 bible 级 content_flag(已实证失灵)
    dark = dark or {}
    if dark.get("ratio", 0) >= 0.4:              # 暗黑贯穿(≥40%抽样窗)→净化救不动
        _cap_grade(g, "Q", f"暗黑饱和(预扫{dark['ratio']})")
        g["content_flag"] = "；".join(dark.get("issues") or ["暗黑当爽点"])[:40]
    elif dark.get("ratio", 0) >= 0.2:
        g["content_flag"] = "；".join(dark.get("issues") or ["暗黑当爽点"])[:40]
    g["source_dark_ratio"] = dark.get("ratio", 0.0)
    cf = (g.get("content_flag") or "").strip()
    if cf and cf != "无":                        # 价值观红线硬降级
        _cap_grade(g, "D", "价值观红线")
    return g


# ============ 顶层：全书深挖一条龙 ============

async def mine_book(cli: Client, clean: str, n_chunks: int, keep_scenes: int) -> dict:
    """clean全本 → {bible(厚), scenes(全局池,已打分筛选), grade}。暗黑预扫与 map 抽取并发。"""
    chunks = chunk_by_chapters(clean, n_chunks=n_chunks)
    # 生死复活召回需更细窗:实测12窗漏桑念复活(误判dies_final),~30k字/窗(≥20窗)命中;独立细分,封顶48防失控
    n_life = min(48, max(20, len(clean) // 30000))
    life_chunks = chunk_by_chapters(clean, n_chunks=n_life)
    results, dark, life_results = await asyncio.gather(
        map_extract(cli, chunks), dark_prescan(cli, clean), extract_life_events_pass(cli, life_chunks))
    all_scenes = merge_scenes(results)
    bible = await reduce_bible(cli, results, all_scenes)
    kept = await score_scenes(cli, all_scenes, keep_scenes)
    grade = await grade_source(cli, bible, dark=dark)
    bible["life_arcs"] = collect_life_events(life_results)   # 方案B:专用轻prompt细窗pass,召回优于主MAP(实测桑念dies_returns命中)
    return {"bible": bible, "scenes": kept, "all_scene_count": len(all_scenes),
            "chunks": len(chunks), "grade": grade}
