"""Tier1 全书产线：全书深挖 → 两层规划(macro→分章) → 复用切片后端起草/选优/审计。

与 slice_validate 的区别：前端换成 mining.mine_book(全书map-reduce厚bible+全局场景池+源分级)
和两层规划(PLAN_MACRO 60章骨架 → PLAN_CHAPTER 并发分章)；后端(BoN/refine/gold/控字/归一/37维)
直接复用 slice_validate 的函数。目标=回收源里本就存在的人/承重/爽点深度。
用法：python -m hiki.produce <源.txt> [--chapters 60] [--chunks 12] [-n 3]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from . import prompts, gate, ledger, audit, mining, prose_continuity, prose_facts, config, event_audit, signals
from .client import Client
from .ingest import ingest
from .slice_validate import (_process_scene, _fit_chapter, _truncate, _assemble,
                             _load_gold, _json, _strip_markers)


import re as _re
import collections


_DLG = _re.compile(r"[「『“\"'][^」』”\"'\n]*[」』”\"']")  # 对话引号(粗)

# R15 高潮事件关键词。强高潮词(查 title+key_events): 明确不可拆。境界词(仅查 title):
# 只有"本章标题就是该境界突破"才算高潮章——避免"配角突破金丹"等key_events噪声误伤普通章("突破"太泛已删)。
_CLIMAX_STRONG = ("飞升", "渡劫", "破虚", "九九", "天劫", "认主", "夺舍", "决战", "陨落", "合体", "大乘")
_CLIMAX_REALM = ("化神", "元婴", "结丹", "凝丹", "金丹", "筑基")


def _is_climax_ch(ch: dict) -> bool:
    title = str(ch.get("title", ""))
    blob = title + "".join(str(e) for e in (ch.get("key_events") or []))
    return any(k in blob for k in _CLIMAX_STRONG) or any(k in title for k in _CLIMAX_REALM)


def _first_person_ratio(text: str) -> float:
    """引号外叙述里第一人称占比（对话内'我'不计）。判 POV 离群章用。"""
    narr = _DLG.sub("", text)
    fp = len(_re.findall(r"我", narr))
    tp = len(_re.findall(r"[他她]", narr))
    return fp / max(1, fp + tp)


def _pov_outliers(ch_texts: list[str]):
    """返回 (全书主人称person, 需修的离群章索引)。主三人称→修一人称离群章；主一人称→不动(尊重源)。"""
    ratios = [_first_person_ratio(t) for t in ch_texts]
    first_chs = sum(1 for r in ratios if r > 0.5)
    if first_chs > len(ratios) / 2:          # 全书本就第一人称 → 不强转
        return 1, []
    outliers = [i for i, r in enumerate(ratios) if r > 0.5]   # 三人称书里的一人称离群章
    return 3, outliers


def _safe_filename(name: str, fallback: str = "成品") -> str:
    """清掉 Windows 非法字符(\\ / : * ? \" < > |)+控制符，给成品起干净文件名。"""
    name = _re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name or "").strip().strip(".")
    name = _re.sub(r"\s+", " ", name)
    return name[:40] or fallback


def _source_id(ref: str) -> str:
    """从源名/输出目录名取库内源 ID（前缀字母+数字码，如 CPBGX00192）；无码则取净化前缀兜底。"""
    ref = _re.sub(r"_full$", "", ref or "")
    m = _re.match(r"[A-Za-z]+\d+", ref)
    return m.group(0) if m else (_safe_filename(ref)[:12] or "源")


def _book_filename(source_ref: str, safe_title: str) -> str:
    """成书交付命名：<源ID><新书名>.txt —— 干净交付名；档/日期/状态剥离至 report.json，源ID 为对账锚。"""
    return f"{_source_id(source_ref)}{safe_title}.txt"


def _delivery_path(out_dir: Path, deliverable: bool, out_name: str) -> Path:
    """交付件落盘路径：可交付汇聚 <out_dir 上级>/_deliverable/；不可交付隔离 <out_dir>/_rejected/。
    靠位置区分交付资格，文件名本身不带状态(A2-a)。"""
    base = (out_dir.parent / "_deliverable") if deliverable else (out_dir / "_rejected")
    return base / out_name


def _started_at(out_dir: Path, now: float) -> float:
    """单一总历时:首次 Ingest 开始时间戳,持久化一次(out_dir/_timing.json),续跑不覆盖。
    seconds = 终点(停哪算哪:通过→Assemble/门拒→Evaluate/早拒→判定点) − 此 started_at。"""
    f = out_dir / "_timing.json"
    try:
        v = json.loads(f.read_text(encoding="utf-8")).get("started_at")
        if isinstance(v, (int, float)):
            return float(v)
    except Exception:
        pass
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"started_at": now}), encoding="utf-8")
    except Exception:
        pass
    return now


async def _decliche_chapters(cli: Client, ch_texts: list[str], cap: int = 22,
                             over_book_min: int = 8, per_chapter_min: int = 2):
    """Tier2 套话硬重写门：按**全书累积疲劳**定位过度复读的套话类别,重写它们聚集的章(治读者累积腻)。
    阈值经 human-eval-5 校准:現言隐婚22章重写后笔力90(机制有效,不松);古言/修仙残留AI感属欠检
    (未来按评委标注扩 audit._CLICHE 词表),非过检。旋钮入 config.decliche 供后续多评委数据调。"""
    full = "\n".join(ch_texts)
    over_book = {lab for lab, c in audit.cliche_hits(full).items() if c >= over_book_min}   # 全书≥此=疲劳类
    if not over_book:
        return ch_texts, []
    scored = []
    for i, t in enumerate(ch_texts):
        h = audit.cliche_hits(t)
        inst = sum(c for lab, c in h.items() if lab in over_book)
        present = [lab for lab in h if lab in over_book]
        if inst >= per_chapter_min:                 # 本章含≥此个疲劳套话实例 → 候选
            scored.append((inst, i, present))
    scored.sort(reverse=True)
    jobs = [(i, present) for _, i, present in scored[:cap]]   # 取最密的 cap 章
    if not jobs:
        return ch_texts, []
    sys_p, usr_t = prompts.DECLICHE
    res = await asyncio.gather(*[
        cli.complete("draft", sys_p, usr_t.format(cliches="、".join(present), text=ch_texts[i][:12000]),
                     max_tokens=8000, temperature=0.5) for i, present in jobs])
    done = []
    for (i, _), t in zip(jobs, res):
        t = _strip_markers(t)
        if (t and len(t) > len(ch_texts[i]) * 0.7
                and sum(audit.cliche_hits(t).values()) < sum(audit.cliche_hits(ch_texts[i]).values())):
            ch_texts[i] = t
            done.append(i)
    return ch_texts, done


def _split_head(t: str, n: int = 1200) -> tuple[str, str]:
    """在 ~n 字附近的段落边界切出"章开头"，供章缝定向重写（只动开头，其余原样拼回）。"""
    cut = t.find("\n\n", int(n * 0.6))
    if cut == -1 or cut > n * 2:
        cut = min(len(t), n * 2)
    return t[:cut], t[cut:]


async def _seam_pass(cli: Client, ch_texts: list[str], cap: int = 60):
    """章缝衔接检修（治人工头号缺陷：相邻章时空/动作倒退）。
    detect(59对尾→头并发) → 定向重写断裂章的开头段(其余原样) → 采用守卫 → 回读复检。
    返回 (修后章文, 修复清单, 检出数, 修复未净清单)。修复未净=改写采用但重跑detect仍断裂。"""
    if len(ch_texts) < 2:
        return ch_texts, [], 0, []
    sys_c, usr_c = prompts.SEAM_CHECK

    async def _check(i: int) -> dict:
        for t in range(3):                       # retry-on-empty(flash偶发空响应,核心flaky类)
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-700:], head=ch_texts[i][:900]),
                                     json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if "ok" in r:
                return r
        return {}                                # 3次都空 → 认衔接正常(保守不误修)
    idxs = list(range(1, len(ch_texts)))
    checks = await asyncio.gather(*[_check(i) for i in idxs])
    bad = []
    for i, r in zip(idxs, checks):
        if r.get("ok") is False:
            bad.append((i, (r.get("issue") or "").strip() or "时空/动作衔接断裂"))
    found = len(bad)
    if not bad:
        return ch_texts, [], 0, []
    bad = bad[:cap]
    sys_f, usr_f = prompts.SEAM_FIX
    splits = {i: _split_head(ch_texts[i]) for i, _ in bad}
    res = await asyncio.gather(*[
        cli.complete("draft", sys_f,
                     usr_f.format(prev=ch_texts[i - 1][-700:], issue=iss, head=splits[i][0]),
                     max_tokens=4000, temperature=0.4) for i, iss in bad])
    adopted = []
    for (i, iss), t in zip(bad, res):
        head, rest = splits[i]
        t = _strip_markers((t or "").strip())
        if t and len(head) * 0.5 <= len(t) <= len(head) * 2.0:   # 守卫:开头没崩才采用
            ch_texts[i] = t + rest
            adopted.append((i, iss))
    rechecks = await asyncio.gather(*[_check(i) for i, _ in adopted])  # 回读复检:只查已采用章
    fixed, unresolved = [], []
    for (i, iss), rc in zip(adopted, rechecks):
        label = f"第{i + 1}章:{iss[:18]}"
        (unresolved if rc.get("ok") is False else fixed).append(label)
    return ch_texts, fixed, found, unresolved


def _trim_tail(t: str, look: int = 400) -> str:
    """章尾句界强制：章末不收在句号/叹号/问号/引号上→回退到最近句界裁掉残句。
    (团宠ch56实证: _truncate的逗号兜底在章尾位置='断在逗号上'肉眼可见,章尾必须整句。)"""
    t = t.rstrip()
    if not t or t[-1] in "。！？”…":
        return t
    for i in range(len(t) - 1, max(0, len(t) - look) - 1, -1):
        if t[i] in "。！？”":
            return t[:i + 1]
    return t


_FLASHBACK_RE = _re.compile(r"(三天前|三日前|几天前|数日前|一个时辰前|时间回到|回到.{0,4}(天|日|年)前|半(天|日)前)")


async def _adj_dup_pass(cli: Client, ch_texts: list[str], cap: int = 12):
    """R11 邻章头部重演检修: 后章开头把前章已演事件重演成互斥版本(冥夙双救场/茶壶两版类)。
    M0(scripts/m0_adjdup_recall.py): 头部类召回1/1,净书误报7%且抽查多为真伤;修复=重写后章开头
    承接前章(同 seam-fix 模式,采用守卫,采用后回读复检),深处互斥不在此环(归点修)。
    返回 (修后, 修复清单, 检出数, 修复未净清单)。"""
    if len(ch_texts) < 2:
        return ch_texts, [], 0, []
    sys_c, usr_c = prompts.ADJ_DUP_CHECK

    async def _check(i: int) -> dict:
        for t in range(3):
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-1800:], head=ch_texts[i][:2200]),
                                     json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if isinstance(r, dict) and "dup" in r:
                return r
        return {}
    idxs = list(range(1, len(ch_texts)))
    checks = await asyncio.gather(*[_check(i) for i in idxs])
    bad = [(i, (r.get("issue") or "互斥重演").strip()) for i, r in zip(idxs, checks)
           if r.get("dup") is True][:cap]
    found = len(bad)
    if not bad:
        return ch_texts, [], 0, []
    sys_f, usr_f = prompts.ADJ_DUP_FIX
    rewrites = await asyncio.gather(*[
        cli.complete("draft", sys_f, usr_f.format(issue=iss, prev=ch_texts[i - 1][-1500:],
                                                  text=ch_texts[i][:14000]),
                     max_tokens=8000, temperature=0.3) for i, iss in bad])
    adopted = []
    for (i, iss), t in zip(bad, rewrites):
        t = _strip_markers((t or "").strip())
        if t and len(t) >= len(ch_texts[i]) * 0.7:   # 采用守卫
            ch_texts[i] = t
            adopted.append((i, iss))
    rechecks = await asyncio.gather(*[_check(i) for i, _ in adopted])  # 回读复检
    fixed, unresolved = [], []
    for (i, iss), rc in zip(adopted, rechecks):
        label = f"第{i + 1}章:{iss[:20]}"
        (unresolved if rc.get("dup") is True else fixed).append(label)
    return ch_texts, fixed, found, unresolved


def _wave_bounds(beats: list[dict], n_ch: int,
                 fallback_cuts: list[int] | None = None, min_ch: int = 4) -> list[tuple[int, int]]:
    """R13 波次界: act 对齐 + 确定性护栏(泛性来自护栏不来自对齐)。
    切点=act转换处;单波>12强制加切;<min_ch并入邻波;act畸形(波数<3或>8)退化固定切口(默认8/20/33/46)。
    fallback_cuts/min_ch 可由 config.production 覆盖(D3);默认=历史校准值。返回 [(start,end)) 0-based。"""
    cuts = []
    prev_act = None
    for i, b in enumerate(beats[:n_ch]):
        act = b.get("act") if isinstance(b, dict) else None
        if prev_act is not None and act and act != prev_act:
            cuts.append(i)
        if act:
            prev_act = act
    def _to_waves(cs: list[int]) -> list[tuple[int, int]]:
        pts = [0] + sorted(set(c for c in cs if 0 < c < n_ch)) + [n_ch]
        return list(zip(pts, pts[1:]))
    waves = _to_waves(cuts)
    if not (3 <= len(waves) <= 8):                   # act 畸形 → 固定切口
        waves = _to_waves(fallback_cuts or [8, 20, 33, 46])
    merged: list[tuple[int, int]] = []               # 护栏①: <min_ch 先并入邻波
    for w in waves:
        if merged and (w[1] - w[0] < min_ch or merged[-1][1] - merged[-1][0] < min_ch):
            merged[-1] = (merged[-1][0], w[1])
        else:
            merged.append(w)
    out: list[tuple[int, int]] = []                  # 护栏②: >12 均匀分割(14→7+7,绝不产生<4的尾巴)
    for a, b in merged:
        n = b - a
        k = -(-n // 12)                              # ceil
        base, rem = n // k, n % k
        s = a
        for i in range(k):
            e = s + base + (1 if i < rem else 0)
            out.append((s, e))
            s = e
    return out


_ITEM_TERMINAL = ("碎", "毁", "耗尽", "丢失", "灰飞", "湮灭", "送出", "易主", "炸")


_MILESTONE_KW = [
    # '出生'已删:误匹配'出生入死/出生年月/出生证明'→假分娩里程碑(只留明确生产词)
    ("分娩", ("分娩", "生下", "产下", "生子", "生女", "临盆", "早产", "剖腹", "诞下", "生产")),
    ("成婚", ("完婚", "结婚", "大婚", "领证", "成婚", "婚礼", "嫁给", "迎娶", "出嫁")),
    ("离婚", ("离婚", "和离")),
    ("认亲", ("认亲", "认祖", "归宗", "相认", "身世揭", "验亲", "滴血", "亲子鉴定", "DNA")),
    # 跨题材不可逆里程碑(治非言情书 ev[:4] 兜底失效:同事件措辞漂移成多条)
    ("飞升突破", ("飞升", "渡劫成功", "突破至", "晋升", "成圣", "成神", "证道")),
    ("重生觉醒", ("重生", "觉醒", "丧尸化", "异变", "穿越", "夺舍")),
    ("继位", ("继位", "登基", "即位", "称帝", "夺嫡成功")),
    ("死亡", ("死亡", "身亡", "战死", "陨落", "牺牲")),  # 与生死账互补:措辞型死亡也归一
]


def _milestone_type(ev: str) -> str:
    """里程碑归类(同类只记首次):覆盖言情/修仙/末世/宫斗常见不可逆事件;不匹配则用前4字兜底。"""
    for t, kws in _MILESTONE_KW:
        if any(k in ev for k in kws):
            return t
    return ev[:4]


def _settle_facts(settled: dict, facts: list[dict], start_ch: int) -> None:
    """波间结算: extract_facts 的逐章事实并入滚动状态(只进不退,死亡/最高修为/事件)。
    R14: 物品终态账——碎/毁/耗尽类只记首次,后续波次铁律禁其完好复出(雷灵珠ch50碎→ch52复用实证)。"""
    for off, f in enumerate(facts):
        ch = start_ch + off + 1                      # 1-based
        for d in f.get("deaths") or []:
            who = (d.get("who") if isinstance(d, dict) else str(d) or "").strip()
            if who and 2 <= len(who) <= 6:
                settled["deaths"].setdefault(who, ch)
        for pair in f.get("power") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                settled["power"][str(pair[0]).strip()] = (str(pair[1])[:20], ch)
        for pair in f.get("items") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                name, state = str(pair[0]).strip(), str(pair[1]).strip()
                if name and 2 <= len(name) <= 8 and any(k in state for k in _ITEM_TERMINAL):
                    settled.setdefault("items", {}).setdefault(name, (state[:12], ch))
        for pair in f.get("milestones") or []:       # M1.5: 不可逆人生里程碑账(治孕产/婚育时间线退步)
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                who, ev = str(pair[0]).strip(), str(pair[1]).strip()
                if who and 2 <= len(who) <= 6 and ev:
                    t = _milestone_type(ev)          # 按类型去重(措辞每章不同,'分娩'类只记首次)
                    settled.setdefault("milestones", {}).setdefault(who, {}).setdefault(t, (ev[:24], ch))


def _spine_map(bible: dict) -> dict:
    """Fact Spine(M1): 从 bible 全量配角+主角编成冻结角色表 {本名:{role,aliases,rel}}。
    M0 实证: 现有 id_map 只钉身份不钉名,且长尾配角漏列→同角色多名漂移(生父4名/顾明骁↔景)。
    Spine 把全量角色的规范名+禁用别名+血缘关系编成硬约束注入起草。"""
    sm: dict = {}
    for c in (bible.get("characters") or []):
        n = (c.get("name") or "").strip()
        if not n:
            continue
        sm[n] = {"role": (c.get("role") or "").strip()[:24],
                 "aliases": [a.strip() for a in (c.get("aliases") or []) if isinstance(a, str) and a.strip() and a.strip() != n][:5],
                 "rel": (c.get("key_relation") or c.get("relation_arc") or "").strip()[:30]}
    p = bible.get("protagonist") or {}
    if (p.get("name") or "").strip():
        sm[p["name"].strip()] = {"role": str(p.get("identity") or "")[:24],
                                 "aliases": [a for a in (p.get("aliases") or []) if a][:5], "rel": "主角"}
    return sm


def _pin_block(label: str, rows: list, rule: str, cap: int = 16) -> str:
    """共享渲染: 行表 →「label: a；b；c\n  铁律: rule」。空则空串。
    收掉 _spine_block/_spine_facts/_spine_roster 三处重复的 join+铁律 包装(#8 altitude)。"""
    if not rows:
        return ""
    return f"\n{label}: " + "；".join(rows[:cap]) + f"\n  铁律: {rule}"


def _spine_block(cur: dict, spine_map: dict) -> str:
    """本章登场角色的冻结角色表(只列本章点到名/别名的角色),硬约束: 禁改名/禁新造名/身份钉死。"""
    if not spine_map:
        return ""
    ch_txt = json.dumps(cur, ensure_ascii=False)
    rows = []
    for name, info in spine_map.items():
        if not (name in ch_txt or any(a in ch_txt for a in info["aliases"])):
            continue
        seg = name
        if info["rel"]:
            seg += f"〔{info['rel']}〕"
        if info["role"]:
            seg += f"={info['role']}"
        if info["aliases"]:
            seg += f"(全书只称「{name}」,禁用异名:{'/'.join(info['aliases'])})"
        rows.append(seg)
    return _pin_block(
        "角色名钉死(Fact Spine·冻结,违者即承重硬伤)", rows,
        "本章涉及的角色一律只用上列**本名**,**禁止为任何角色新造名字或改用别名/改写身份血缘**"
        "(治同一角色多名/同名多身份漂移);上表没有的新角色才可命名。", cap=10)


def _spine_alive_baseline(spine_map: dict) -> str:
    """Fact Spine(§4 事前预防): 存活基线——主要人物默认全书健在,禁 draft 在未铺垫处顺带写其死亡。
    M0 实证(plan_spine §4):DYBXN00061「父亲第1章被顺带写'生前'(暗示已故)却第3章在场」=plan 未跟踪的配角,
    draft 无冻结存活状态时自由现编死亡。事前冻结基线 → 结构上不产生(同名/数值钉死思路)。"""
    names = list(spine_map.keys())
    if not names:
        return ""
    return _pin_block(
        "存活基线(Fact Spine·事前,默认健在)", names,
        "上列人物默认全书健在;**严禁在未正式铺写完整死亡情节的章节顺带提及其「已故/生前/去世/死去/遗像/坟前/遗物」等死亡暗示**"
        "(治自由现编配角死亡:某角被顺带写「生前」却在后文在场);确需其死亡→必须在对应章正式铺写死亡情节后方可。", cap=16)


def _spine_facts(bible: dict) -> str:
    """Fact Spine(M1.5 ②): bible.facts(归并单值设定数值)→「数值钉死」硬约束。
    M1 实证只钉名+身份不够(彩礼30/60/15万照漂);冻结单值注入每章,优先级>brief。"""
    rows = []
    for f in (bible.get("facts") or []):
        if not isinstance(f, dict):
            continue
        item, val = str(f.get("item") or "").strip(), str(f.get("value") or "").strip()
        if not (item and val):
            continue
        rule = str(f.get("rule") or "").strip()
        rows.append(f"{item}={val}" + (f"〔{rule}〕" if rule else ""))
    return _pin_block(
        "数值钉死(Fact Spine·冻结单值,违者即承重数值矛盾)", rows,
        "涉及上列设定数值时**只能用冻结值**(单调标记者只可按序递增,绝不写低/回退);"
        "brief 或情节需要而上表未列的数值才可自定,且全书须自洽。", cap=16)


def _spine_roster(spine_map: dict) -> str:
    """M1.5③ 身份维钉死: 全书角色身份 always-on 冻结总表(治身份漂移)。
    名钉死(_spine_block)只防同角色多名;身份漂移=draft给已知角色另派身份/职务/辈分,或复用人名作新职务
    (周柏森 律师↔人力总监,M1.5③精读头号残留致命)——需身份维硬约束+「新功能角色另起新名」。"""
    rows = [f"{name}={tag}" for name, info in spine_map.items()
            if (tag := ((info.get("role") or "").strip() or (info.get("rel") or "").strip()))]
    return _pin_block(
        "角色身份钉死(Fact Spine·全书冻结,违者即承重硬伤)", rows,
        "①上列角色的身份/职业/头衔/辈分/亲属称谓一经设定全书不得变更"
        "(禁:顾家大少写成二少、表弟写成表叔、律师写成总监、哥哥写成父亲);"
        "②同一人名绝不承担两种互斥身份/职务;③需要新职务的功能性角色(某公司总监/某律师等)"
        "**必须另起新名,严禁复用上表或前文已出现过的人名**。", cap=18)


def _spine_world(bible: dict) -> str:
    """M2 失效类: 世界观体系登记表(地点/势力/战力体系钉死),治地名横跳+战力体系乱序。"""
    out = ""
    places = [p.get("name", "").strip() for p in (bible.get("places") or [])
              if isinstance(p, dict) and p.get("name")][:20]   # 容纳 enrich_places 自愈回灌的新地名
    facs = [f.get("name", "").strip() for f in (bible.get("factions") or [])
            if isinstance(f, dict) and f.get("name")][:8]
    sysdef = (bible.get("power_system") or "").strip()
    if places:
        out += "\n地点钉死(全书规范地名/城名,禁中途改名换城): " + "、".join(places)
    if facs:
        out += "\n势力/机构钉死(规范名,禁异名): " + "、".join(facs)
    # 体系门: 现言/无体系书 model 措辞多样(无/无明确体系/现实世界...),用前缀+长度稳健判,不靠两个魔法字面值(#6)
    if sysdef and len(sysdef) >= 6 and not sysdef.startswith(("无", "现实", "没有", "暂无", "不适用", "N/A", "n/a")):
        out += "\n战力/体系钉死(全书唯一阶梯,禁混用别套或等级乱序/回退): " + sysdef[:220]
    if out:
        out += "\n  铁律: 涉及上列地点/势力/体系一律用规范称谓与单一体系,禁中途改地名、换公司名、混用别套战力或等级倒退。"
    return out


_TRANSMIGRATION_KW = ("穿越", "重生", "魂穿", "夺舍", "借尸还魂", "重活", "重回", "再活一世", "一朝穿", "穿书")


def _open_premise(bible: dict, plan: dict) -> str:
    """检测开篇是否穿越/重生类→需代入视角锚今世主角(human-eval-5: 和谈/团宠 栽在原主视角开篇+原身设定
    自相矛盾+NPC点破金手指)。返回命中的前提词(供铁律标注),否则''。"""
    p = bible.get("protagonist", {}) or {}
    hay = " ".join(str(x) for x in (json.dumps(p, ensure_ascii=False), bible.get("genre", ""),
                                    bible.get("logline", ""), bible.get("voice", "")))
    chs = plan.get("chapters") or []
    if chs:
        hay += " " + json.dumps(chs[0], ensure_ascii=False)
    for kw in _TRANSMIGRATION_KW:
        if kw in hay:
            return kw
    return ""        # 仅关键词触发;aliases-only(双名)误报(隐婚'顾知夏'=真千金本名非前世名,C实证)→不作信号


def _control_plane(ci: int, si: int, plan: dict, settled: dict, prev_exit: str,
                   id_map: dict | None = None, spine_map: dict | None = None,
                   spine_global: str = "", open_premise: str = "") -> str:
    """R13 章级控制面(inkos控制面+WriteHERE inclusion/exclusion+autonovel病例的反面):
    事实由代码编译进起草输入,不靠模型回忆;铁律优先级>brief。
    B1-bug修(R13锚-8.8根因): inclusion(本章必演)是**章级**清单,原先每场景都注入→
    章内后场景被铁律命令重演首场景已完成的事件(团宠ch49近逐字复刻实锤)。
    改: 必演/开场前提只进首场景(si==0);后场景(si>0)把这批事件改标"已演完,绝不重演,只顺势推进"。
    R14 账本扩面(团宠三臂实证:有对账守得住/错账更糟/无账放任漂移):
    +身份账(canon,bible来源,治傅礼三版身份) +物品账(prose终态,治雷灵珠碎后复用)。"""
    chs = plan["chapters"]
    cur = chs[ci]
    inc = [str(k) for k in (cur.get("key_events") or []) if str(k).strip()][:3]
    excl: list[str] = []
    for j in range(max(0, ci - 3), ci):              # 近3章已演事件(邻章互斥重灾区)
        for k in (chs[j].get("key_events") or []):
            if str(k).strip():
                excl.append(f"第{j + 1}章已演:{str(k)[:40]}")
    dead = [f"{w}(第{c}章亡,绝不再出场)" for w, c in sorted(settled["deaths"].items(), key=lambda x: x[1])][-8:]
    pw = [f"{w}={v}(截至第{c}章)" for w, (v, c) in list(settled["power"].items())[-6:]]
    # R14 身份账: 本章场景文本里点到名的 canon 角色,身份钉死(确定性匹配,cap5防膨胀)
    ids: list[str] = []
    if id_map:
        ch_txt = json.dumps(cur, ensure_ascii=False)
        ids = [f"{n}={r}" for n, r in id_map.items() if n and n in ch_txt][:5]
    # R14 物品账: 已终结物品,禁完好复出
    items = [f"{n}(第{c}章{s},绝不再完好出现/使用)" for n, (s, c) in
             list(settled.get("items", {}).items())[-6:]]
    lines = ["【控制面·铁律(优先级高于场景brief的叙述)】"]
    if prev_exit and si == 0:                        # 开场前提=章首场景的事,后场景接的是本章前序场景
        lines.append(f"开场前提: 上一章结束于——{prev_exit[:80]};本章从此处接续。")
    if ci == 0 and si == 0 and open_premise:          # B: 穿越/重生开篇代入铁律(治 human-eval-5 三类硬伤)
        lines.append(
            f"穿越/重生开篇·代入铁律({open_premise}): "
            "①代入视角从开篇第一句就锚定今世主角(穿越/重生者),绝不先用原主/原身视角铺垫其生平再写其死——"
            "原主之死只作主角醒来后的简短回溯,不单独开场代入(防读者先入为主代入一个即将死掉的人); "
            "②原身/前世设定一次性交代、全书口径唯一(原身是否已死、婚配状况只设一种,绝不前后矛盾——"
            "不可前文'原身已死穿越者来'、后文又写'原身嫁人苦死'); "
            "③金手指/系统由主角自己逐步发现,绝不让其他角色在本章当面点破/说出主角的金手指(它是主角对读者的底牌,非NPC可一眼看穿)。")
    if dead:
        lines.append("生死账(已结算,违者即硬伤): " + "；".join(dead))
    if pw:
        lines.append("修为/数值账(只升不降): " + "；".join(pw))
    if ids:
        lines.append("身份账(canon,全书不变,违者即硬伤): " + "；".join(ids))
    spine_on = os.environ.get("HIKI_SPINE") == "1"
    sb = _spine_block(cur, spine_map) if (spine_map and spine_on) else ""
    sb += spine_global if spine_on else ""           # roster+facts+world 全书常量,run() 算一次
    if spine_on and settled.get("milestones"):       # M1.5: 里程碑账(不可逆,治孕产/婚育时间线退步)
        # 不截断: 里程碑(分娩/成婚...)本就少,旧 [-8:] 会把女主早期'已分娩'挤出晚章铁律→孕产退步复发(#2)
        ms = [f"{w}: " + "、".join(f"{ev}(第{c}章)" for ev, c in types.values())
              for w, types in settled["milestones"].items()]
        lines.append("里程碑账(已发生·不可逆,绝不退回此前状态/不重演该事件;如已分娩绝不再写未孕待产、已完婚绝不再写未婚): "
                     + "；".join(ms))
    if items:
        lines.append("物品账(已终结): " + "；".join(items))
    if inc:
        if si == 0:                                  # 章首场景才命令演出本章关键事件
            lines.append("本章必演(具体写出过程与结果): " + "；".join(inc))
        else:                                        # 后场景: 同批事件已在本章前序场景演完→禁重演
            lines.append("本章关键事件已在前序场景演出完毕(绝不重演/换角度重写,只顺势推进其后续): "
                         + "；".join(inc))
    if excl:
        lines.append("绝不重演(已在前章演出完毕,只可一句带过): " + "；".join(excl[-6:]))
    return "\n" + "\n".join(lines) + sb + "\n"


async def _plan_dedup_pass(cli: Client, plan: dict, cap: int = 16) -> list[str]:
    """R12 plan级邻章节拍查重: R11实证版本互斥重灾区=act边界(ch30-33/45-46/57-60,五本全中),
    大事件禁演只盖关键词类(渡劫/大婚),战斗/对峙/求娶类漏——相邻章场景计划判'同事件覆盖',
    后章brief注禁演(确定性标注,起草前,LLM只判不改)。"""
    chs = plan["chapters"]
    if len(chs) < 2:
        return []
    sys_p, usr_t = prompts.PLAN_DUP_CHECK

    def _digest(ch: dict) -> str:
        # R16: 喂 key_events(剧情进展信号)+brief——治邻章"同一剧情进展无推进"(ch23-24试探江清清),
        # 旧版只喂brief判不出(brief措辞不同但剧情原地踏步)。
        ke = "；".join(str(e)[:40] for e in (ch.get("key_events") or []))
        return (str(ch.get("title", "")) + " | 进展:" + ke + " | " + " ; ".join(
            str(sc.get("brief", ""))[:120] for sc in ch.get("scenes", []) if isinstance(sc, dict)))[:700]

    async def _check(j: int) -> dict:
        for t in range(3):
            raw = await cli.complete("chunk_extract", sys_p,
                                     usr_t.format(prev=_digest(chs[j - 1]), cur=_digest(chs[j])),
                                     json_mode=True, max_tokens=200, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if isinstance(r, dict) and "dup" in r:
                return r
        return {}
    idxs = list(range(1, len(chs)))
    checks = await asyncio.gather(*[_check(j) for j in idxs])
    fixed = []
    for j, r in zip(idxs, checks):
        if r.get("dup") is True and len(fixed) < cap:
            ev = (str(r.get("event") or "同一事件")).strip()[:20]
            for sc in chs[j].get("scenes", []):
                if isinstance(sc, dict):
                    sc["brief"] = (f"(铁律:「{ev}」已在上一章演出完毕,本章绝不重演/换角度重写它,"
                                   f"只写其后续推进) ") + (sc.get("brief") or "")
            fixed.append(f"第{j + 1}章:{ev}")
    return fixed


async def _verify_advisories(cli: Client, claims: list[str], bible: dict) -> list[str]:
    """R11 灰区判读: 只有'读者可感知的硬矛盾'才保留为advisory(进fc/门)。
    实证噪声类: 龙套未列(郑金花/刘长老/魔皇)、能力延伸(冰系∈水系)、goal剧情演进、口径差
    (圣经练气圆满vs正文措辞)。存疑保守: 判不出=保留。"""
    if not claims:
        return []
    sys_p, usr_t = prompts.ADVISORY_VERIFY
    bx = json.dumps({k: bible.get(k) for k in ("protagonist", "characters", "setting")},
                    ensure_ascii=False)[:2500]
    checks = await asyncio.gather(*[
        cli.complete("chunk_extract", sys_p,
                     usr_t.format(claim=str(c)[:200], bible_excerpt=bx),
                     json_mode=True, max_tokens=200, temperature=0.1) for c in claims[:12]])
    out = []
    for c, r in zip(claims, checks):
        v = gate._safe_json(r) or {}
        if v.get("real") is not False:               # 只滤明确判否的
            out.append(c)
    return out


def _flashback_advisory(ch_texts: list[str]) -> list[str]:
    """确定性倒叙标记扫描(advisory): 章首即倒叙='ch41三天前重演颁奖典礼'型重演的直接信号。
    注: 曾试过'章级场合摘要→LLM查重'检测重演,在已知病书上零检出(章级表征看不见章内重演),
    已删——不可靠的检测器不能进交付门,防重演靠规划层铁律⑪⑫+邻章节拍注入,本扫描只做哨兵。"""
    out = []
    for i, t in enumerate(ch_texts):
        m = _FLASHBACK_RE.search(t[:200])
        if m:
            out.append(f"第{i + 1}章开头即倒叙({m.group()})——疑似重演前章事件")
    return out


def _handoff(jobs: list, plan: dict, i: int) -> str:
    """给场景 i 注入"紧邻前文"握手（上一场景 brief；跨章再附上一章 exit_state），治章缝倒退。"""
    if i == 0:
        return ""
    ci = jobs[i][0]
    pci, _, psc = jobs[i - 1]
    parts = [psc.get("brief") or ""]
    if pci != ci:
        ex = (plan["chapters"][pci].get("exit_state") or "").strip()
        if ex:
            parts.append(f"上一章收束状态:{ex}")
    txt = "；".join(x for x in parts if x)
    return f"\n紧邻前文(本场景开场必须从此接续,时空/动作不得倒退): {txt}" if txt else ""


def _title_ok(t: str) -> bool:
    """书名合法性守卫：必须像书名不像简介片段（治 setting[:12] 残句类 bug）。"""
    t = (t or "").strip()
    if not (3 <= len(t) <= 16):
        return False
    if any(c in t for c in "。，、…；"):                # 描述句标点=简介(冒号放行:主副标题是合法网文命名)
        return False
    if t[0].isdigit():                                  # "1970年代饥荒背景，女" 类残句
        return False
    if any(w in t for w in ("背景", "设定", "题材", "语域", "世界观", "主角", "复写")):
        return False
    return True


async def gen_title(cli: Client, bible: dict, ending: str = "") -> dict:
    """给复写新书起商业书名+卖点（flash，便宜）。喂实际结尾→书名/卖点贴真实结局(治承诺落空)。
    带重试+合法性守卫(flash 偶发吐空/吐残句)；兜底用主角名,绝不用 setting 描述片段当书名。"""
    p = bible.get("protagonist", {})
    sys_p, usr_t = prompts.TITLE
    usr = usr_t.format(
        protagonist=f"{p.get('name','')}/{p.get('identity','')}/{p.get('goal','')}",
        conflict=bible.get("central_conflict", ""), setting=bible.get("setting", ""),
        voice=bible.get("voice", ""), ladder=bible.get("escalation_ladder", ""),
        ending=ending[-3000:] or "（无）")
    r: dict = {}
    for t in range(3):                                  # 空/残句书名 → 重试(与其余 flaky 类同处理)
        raw = await cli.complete("plan_chapter", sys_p, usr,
                                 json_mode=True, max_tokens=2000, temperature=0.8 + 0.05 * t)
        r = gate._safe_json(raw) or {}
        if _title_ok(r.get("title", "")):
            return r
    name = (p.get("name") or "").strip()                # 三次仍不合法 → 主角名兜底,绝不拿 setting 描述
    fb = f"{name}的逆袭" if name else "绝世逆袭"
    return {"title": _safe_filename(fb), "tagline": r.get("tagline", ""), "alts": r.get("alts", [])}


async def _plan_macro(cli: Client, bible: dict, scenes: list[dict], n_ch: int, tries: int = 3) -> dict:
    """60章节拍图。pro 思考模式偶发吐空/截断 → 重试（与 reduce 同病）。"""
    sys_p, usr_t = prompts.PLAN_MACRO
    listed = "\n".join(
        f"{i}. [{sc.get('scene_type','')}/{sc.get('importance','')}] {sc.get('summary','')[:70]}"
        for i, sc in enumerate(scenes))
    bible_txt = json.dumps({k: bible.get(k) for k in
                            ("central_conflict", "escalation_ladder", "setting",
                             "protagonist", "factions")}, ensure_ascii=False)[:8000]
    usr = usr_t.format(n_ch=n_ch, bible=bible_txt, scenes=listed)
    best = {"chapters": []}
    for t in range(tries):
        raw = await cli.complete("plan_macro", sys_p, usr,
                                 json_mode=True, max_tokens=32000, temperature=0.4 + 0.1 * t)
        m = gate._safe_json(raw) or {}
        chs = m.get("chapters") or []
        if len(chs) >= int(n_ch * 0.8):             # 出≥80%章节才算成功(精简字段后60章应能整出)
            return m
        if len(chs) > len(best["chapters"]):
            best = m
    return best


async def _plan_one_chapter(cli: Client, beat: dict, scenes: list[dict], bible_brief: str,
                            tries: int = 2, prev_beat: str = "（无）", next_beat: str = "（无）",
                            prev_exit: str = "") -> dict:
    idx0 = beat.get("i", beat.get("index", 0))
    refs = [r for r in (beat.get("refs") or beat.get("source_scene_refs") or [])
            if isinstance(r, int) and 0 <= r < len(scenes)]
    sc_txt = "\n".join(f"[{r}] {scenes[r].get('summary','')} | 留:{scenes[r].get('key_excerpt','')}"
                       for r in refs) or "（无指定源场景，按节拍自行演绎）"
    sys_p, usr_t = prompts.PLAN_CHAPTER
    ch = {}
    for t in range(tries):                          # 单章偶发flaky→重试,防整章丢失致书变短
        raw = await cli.complete("plan_chapter", sys_p,
                                 usr_t.format(beat=json.dumps(beat, ensure_ascii=False)[:1500],
                                              scenes=sc_txt, bible_brief=bible_brief, index=idx0,
                                              prev_beat=prev_beat, next_beat=next_beat,
                                              prev_exit=prev_exit or "（未知,以上一章节拍收束处为准）"),
                                 json_mode=True, max_tokens=6000, temperature=0.5 + 0.1 * t)
        ch = gate._safe_json(raw) or {}
        if ch.get("scenes"):
            break
    for sc in ch.get("scenes", []):                 # 回填 source_ref 供起草学事件
        idx = sc.get("source_scene_index")
        if isinstance(idx, int) and 0 <= idx < len(scenes):
            s = scenes[idx]
            sc["source_ref"] = f"{s.get('key_excerpt','')} {s.get('summary','')}"
    ch.setdefault("index", idx0)
    ch.setdefault("title", (beat.get("beat") or beat.get("main_thread_beat") or "")[:20])
    ch.setdefault("scenes", [])
    ch.setdefault("end_hook", "")
    ch.setdefault("exit_state", "")
    ch.setdefault("start_state", "")
    return ch


async def _handshake_pass(cli: Client, plan: dict, beats: list[dict], scenes: list[dict],
                          bible_brief: str, cap: int = 20):
    """R8 plan层章间握手(M0实证: 章缝主源在plan节拍跳跃,prose缝合只能抹平句面→下沉到plan治根)。
    并行分章使第j+1章规划时看不见第j章exit_state → 规划后逐对flash判接续,
    断裂章带着上一章**真实exit_state**定向重规划(流程确定性,判读flash,宁放过不误报)。
    返回 (plan, 检出数, 重规划成功数)。"""
    chs = plan["chapters"]
    if len(chs) < 2 or not beats:
        return plan, 0, 0
    sys_h, usr_h = prompts.HANDSHAKE_CHECK

    async def _check(j: int) -> dict:
        prev, cur = chs[j - 1], chs[j]
        sc0 = (cur.get("scenes") or [{}])[0]
        brief = ((sc0.get("brief") if isinstance(sc0, dict) else str(sc0)) or "")[:300]
        for t in range(3):                           # retry-on-empty
            raw = await cli.complete("chunk_extract", sys_h,
                                     usr_h.format(prev_exit=prev.get("exit_state") or "（未知）",
                                                  hook=prev.get("end_hook") or "（无）",
                                                  start=cur.get("start_state") or "（未填）",
                                                  brief=brief or "（无）"),
                                     json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if "ok" in r:
                return r
        return {}                                    # 3次空 → 认衔接正常(保守不误修)

    idxs = list(range(1, len(chs)))
    checks = await asyncio.gather(*[_check(j) for j in idxs])
    bad = [j for j, r in zip(idxs, checks) if r.get("ok") is False][:cap]
    if not bad:
        return plan, 0, 0

    def _bb(b: dict) -> str:
        return (b.get("beat") or "")[:60] or "（无）"

    def _beat_for(j: int) -> dict:                   # 章→macro节拍: 按index对齐,丢章时退位置
        want = chs[j].get("index")
        cand = [b for b in beats if isinstance(b, dict)]
        if not cand:
            return {}
        return next((b for b in cand if b.get("i", b.get("index")) == want),
                    cand[min(j, len(cand) - 1)])
    replans = await asyncio.gather(*[
        _plan_one_chapter(cli, _beat_for(j), scenes, bible_brief,
                          prev_beat=_bb(_beat_for(j - 1)),
                          next_beat=_bb(_beat_for(j + 1)) if j + 1 < len(chs) else "（本章是全书结局）",
                          prev_exit=chs[j - 1].get("exit_state") or "")
        for j in bad])
    fixed = 0
    for j, nc in zip(bad, replans):
        if nc.get("scenes"):                         # 重规划flaky → 保留原章,不丢章
            chs[j] = nc
            fixed += 1
    return plan, len(bad), fixed


async def _stage_mine(cli: Client, src: Path, out_dir: Path, n_ch: int, n_chunks: int,
                      min_grade: str | None, prod: dict, force: bool = False) -> dict:
    """阶段1 mine(B1): ingest + map-reduce 厚bible + 场景筛选 + 源分级。
    → {bible,scenes,grade,meta,clean,all_scene_count,chunks} 或 {rejected,report}。
    resume(B2): bible/scenes/grade/mine.json 齐且 not force → 直接 load,跳过 ¥1-2 的 mine。"""
    meta = ingest(src, out_dir / "source")
    clean = (out_dir / "source" / "clean.txt").read_text(encoding="utf-8")
    arts = {n: out_dir / f"{n}.json" for n in ("bible", "scenes", "grade", "mine")}
    if not force and all(a.exists() for a in arts.values()):
        ld = {n: json.loads(a.read_text(encoding="utf-8")) for n, a in arts.items()}
        print(f"[resume] mine 产物已存在 → 载入 bible/scenes/grade(跳过深挖)")
        return {"bible": ld["bible"], "scenes": ld["scenes"], "grade": ld["grade"],
                "meta": meta, "clean": clean,
                "all_scene_count": ld["mine"].get("all_scene_count", len(ld["scenes"])),
                "chunks": ld["mine"].get("chunks", n_chunks)}
    print(f"源 {meta.approx_wan_zi}万字/{meta.chapter_count}章 → 全书深挖({n_chunks}窗)")
    keep_scenes = int(n_ch * prod.get("scene_per_chapter", 1.4))
    mined = await mining.mine_book(cli, clean, n_chunks, keep_scenes)
    bible, scenes, grade = mined["bible"], mined["scenes"], mined["grade"]
    p = bible.get("protagonist", {})
    # 厚 bible 无效 = 抽取/归并管道失败（flaky），绝不当成"源质量差"拒收 → 显式报错
    if not mining._bible_ok(bible):
        raise RuntimeError(f"REDUCE 失败：厚 bible 无效（主角/中心冲突缺失），非源质量问题。"
                           f"已重试仍空，请重跑。bible={json.dumps(bible, ensure_ascii=False)[:300]}")
    print(f"语域:{bible.get('voice','')} | 主角:{p.get('name')}({p.get('gender')}) "
          f"目标:{p.get('goal','')[:20]}")
    print(f"中心冲突:{bible.get('central_conflict','')[:40]}")
    print(f"全局场景 {mined['all_scene_count']}→筛{len(scenes)} | 源分级:{grade.get('grade')}"
          f"/{grade.get('mode')} 主角弧:{grade.get('protagonist_arc','?')} "
          f"暗黑预扫:{grade.get('source_dark_ratio', 0)} 风险:{grade.get('risk','')}")
    below_floor = (min_grade
                   and mining._GRADE_ORDER.index(grade.get("grade") or "B")
                   > mining._GRADE_ORDER.index(min_grade))
    if grade.get("grade") == "Q" or grade.get("mode") == "拒收" or below_floor:
        why = f"低于源门槛{min_grade}" if below_floor and grade.get("grade") != "Q" else "达不到85"
        report = {"source": src.name, "grade": grade, "rejected": True, "reject_why": why,
                  "cost_cny": round(cli.cost_cny, 2)}
        (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"⚠ 源分级={grade.get('grade')} → 拒收（{why}）。成本¥{cli.cost_cny:.2f}")
        return {"rejected": True, "report": report}
    # 把 agency 素材并进 arc，让起草的"主动"有真材料（决策:人维洼地）
    if p.get("agency_examples"):
        p["arc"] = (p.get("arc", "") + " | 主动事例:" + "；".join(p["agency_examples"][:3]))[:200]
    for nm, obj in (("bible", bible), ("scenes", scenes), ("grade", grade),
                    ("mine", {"all_scene_count": mined["all_scene_count"], "chunks": mined.get("chunks", n_chunks)})):
        (out_dir / f"{nm}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return {"bible": bible, "scenes": scenes, "grade": grade, "meta": meta, "clean": clean,
            "all_scene_count": mined["all_scene_count"], "chunks": mined.get("chunks", n_chunks)}


async def _stage_plan(cli: Client, bible: dict, scenes: list, out_dir: Path, n_ch: int,
                      force: bool = False) -> dict:
    """阶段2 plan(B1): macro 60章节拍 → 分章并发 → 确定性 plan-repair 栈。
    → {plan,beats,ordered,n_scenes,macro}。resume(B2): macro/plan.json 齐且 not force → load
    (plan.json 已是全部 repair 后的终态,ordered 由其展平)。"""
    if not force and (out_dir / "macro.json").exists() and (out_dir / "plan.json").exists():
        macro = json.loads((out_dir / "macro.json").read_text(encoding="utf-8"))
        plan = json.loads((out_dir / "plan.json").read_text(encoding="utf-8"))
        ordered = [sc for ch in plan["chapters"] for sc in ch["scenes"]]
        print(f"[resume] plan 产物已存在 → 载入 {len(plan['chapters'])}章/{len(ordered)}场景(跳过规划)")
        return {"plan": plan, "beats": macro.get("chapters", [])[:n_ch], "ordered": ordered,
                "n_scenes": len(ordered), "macro": macro}
    p = bible.get("protagonist", {})
    macro = await _plan_macro(cli, bible, scenes, n_ch)
    beats = macro.get("chapters", [])[:n_ch]
    if len(beats) < int(n_ch * 0.7):
        raise RuntimeError(f"PLAN_MACRO 失败：仅 {len(beats)}/{n_ch} 章节拍（flaky 截断），已重试仍不足，请重跑。")
    if len(beats) < n_ch:
        print(f"⚠ macro 仅 {len(beats)}/{n_ch} 章（截断残留），继续但成书略短")
    dropped = [str(d)[:20] for d in (macro.get("dropped_threads") or []) if d][:8]
    print(f"macro:{len(beats)}章 主线={macro.get('central_conflict','')[:30]}"
          f" | 砍线保肉:{dropped or '无'} → 分章并发...")
    bible_brief = json.dumps({"protagonist": {k: p.get(k) for k in ("name", "gender", "goal", "arc")},
                              "characters": [{"name": c.get("name"), "goal": c.get("goal")}
                                             for c in bible.get("characters", [])[:8]],
                              "setting": bible.get("setting")}, ensure_ascii=False)[:3000]
    if os.environ.get("HIKI_SPINE") == "1":             # Fact Spine: 规划也喂全量冻结角色名表(plan 用规范名)
        roster = "；".join(f"{n}={i['role']}" + (f"〔{i['rel']}〕" if i['rel'] else "")
                           for n, i in _spine_map(bible).items())[:2500]
        bible_brief += ("\n【冻结角色表(全书规范名,规划与命名只用这些本名,禁新造同义角色)】\n" + roster)
        facts_line = "；".join(f"{f.get('item')}={f.get('value')}" for f in (bible.get("facts") or [])
                              if isinstance(f, dict) and f.get("item") and f.get("value"))[:1500]
        if facts_line:
            bible_brief += ("\n【冻结设定数值(全书单值,节拍涉及时只用这些值)】\n" + facts_line)
        places_line = "、".join(p.get("name", "").strip() for p in (bible.get("places") or [])
                               if isinstance(p, dict) and p.get("name"))[:1200]
        if places_line:                                  # Plan-地点槽:场景 location 只从冻结地名取(治地名横跳+承重锚定)
            bible_brief += ("\n【冻结地点表(全书规范地名,场景 location 只用这些,跨地写明过渡)】\n" + places_line)
    def _beat_brief(b: dict) -> str:
        return (b.get("beat") or "")[:60] or "（无）"
    plan_chs = await asyncio.gather(*[
        _plan_one_chapter(cli, b, scenes, bible_brief,
                          prev_beat=_beat_brief(beats[j - 1]) if j > 0 else "（本章是开篇）",
                          next_beat=_beat_brief(beats[j + 1]) if j < len(beats) - 1 else "（本章是全书结局）")
        for j, b in enumerate(beats)])
    plan = {"chapters": [c for c in plan_chs if isinstance(c, dict) and c.get("scenes")]}
    for c in plan["chapters"]:                       # 第13鲁棒类: flaky LLM把场景吐成str→.get崩整本
        c["scenes"] = [s for s in c["scenes"] if isinstance(s, dict)]
    plan["chapters"] = [c for c in plan["chapters"] if c["scenes"]]
    # R10消融: 握手两轮(R8/R9)零正效——每书检出/重规划全量20(cap撞顶=过敏),churn了1/3的plan
    # 而章缝检出未降、R9锚-4.2。默认关,留 HIKI_HANDSHAKE=1 单变量验证。
    hs_found = hs_fixed = 0
    if os.environ.get("HIKI_HANDSHAKE") == "1":
        plan, hs_found, hs_fixed = await _handshake_pass(cli, plan, beats, scenes, bible_brief)
        if hs_found:
            print(f"plan握手: {hs_found} 处开场不接续 → 带上章exit_state重规划 {hs_fixed} 章")
    ordered = [sc for ch in plan["chapters"] for sc in ch["scenes"]]
    n_scenes = len(ordered)
    if n_scenes == 0:
        raise RuntimeError("PLAN_CHAPTER 全失败：无任何可起草场景（flaky），请重跑。")
    dup_removed = ledger.dedup_first_meetings(ordered)   # 治重复初遇:清后续重复标记→前情账本准
    if dup_removed:
        print(f"确定性去重: 清掉 {dup_removed} 个重复初遇/重复登场标记")
    ev_fixed = audit.fix_event_unique(plan)              # R10 大事件唯一(团宠渡劫4遍=macro排重实证)
    if ev_fixed:
        print(f"确定性禁演: {len(ev_fixed)} 处大事件重演标记: {ev_fixed[:4]}")
    plan_dups = await _plan_dedup_pass(cli, plan)        # R12 邻章节拍查重(act边界版本互斥shift-left)
    if plan_dups:
        print(f"plan邻章查重: {len(plan_dups)} 处同事件覆盖→后章注禁演: {plan_dups[:5]}")
    ent_fixed = audit.fix_entourage(bible, ordered)      # 维2 shift-left:随从阵营钉回canon再起草
    if ent_fixed:
        print(f"确定性修复: {ent_fixed} 个随从阵营钉回canon(治串线,免交付门误拦)")
    pw_fixed = audit.fix_power_monotonic(bible, ordered)  # 维5 shift-left:修为只升不降钉进plan
    if pw_fixed:
        print(f"确定性修复: {len(pw_fixed)} 个修为回退钉回当前最高(治正文修为乱序): {pw_fixed[:4]}")
    added_places = audit.enrich_places(bible, ordered)   # (b)地名表自愈:plan复现的物理新地名回灌bible→喂draft+降漂移
    if added_places:
        print(f"地点表自愈: 回灌 {len(added_places)} 个复现新地名→bible.places(治抽取召回缺口): {added_places[:6]}")
    place_drift = audit.check_places(bible, ordered)     # Plan-地点槽 advisory:场景location漂移(enrich后,新维不进门)
    n_loc = sum(1 for s in ordered if (s.get("location") or "").strip())
    if place_drift or n_loc:
        print(f"地点槽: {n_loc}/{len(ordered)} 场景有location | 漂移(advisory){len(place_drift)}: {place_drift[:4]}")
    for ch in plan["chapters"]:                          # 章尾钩纪律(治'每章结尾钩子弱')
        hk = (ch.get("end_hook") or "").strip()
        if hk and ch["scenes"]:
            last = ch["scenes"][-1]
            last["brief"] = (last.get("brief") or "") + f"；本章必须收在钩子上:{hk}(结尾留悬念/危机,不写圆满收场)"
    # R15 语义双版本治根: 高潮章场景2+的brief整个替换为纯收束(删高潮指令)+SUMMARIZE;非高潮章保留R13c前置标注
    climax_chs = intra_dup = 0
    for ch in plan["chapters"]:
        scs = ch["scenes"]
        if len(scs) < 2:
            continue
        if _is_climax_ch(ch):                        # 高潮章: 首场景演透, 其余只写后续
            core = (scs[0].get("brief") or str(ch.get("title", "")))[:50]
            for k in range(1, len(scs)):
                scs[k]["mode"] = "SUMMARIZE"
                scs[k]["brief"] = (f"(铁律: 本章高潮「{core}」已在第一个场景完整演出。本场景**严禁**以任何措辞"
                                   f"重写/重演/换角度复述该高潮过程; 只写它**之后**的直接后果——他人反应/"
                                   f"主角状态/一两句收束或转场, 压缩带过, 绝不再展开高潮本身)")
            climax_chs += 1
        else:                                        # 非高潮章: R13c 前置标注
            for k in range(1, len(scs)):
                pb = (scs[k - 1].get("brief") or "").strip()[:60]
                if pb:
                    scs[k]["brief"] = (f"(铁律:上一场景已把「{pb}」完整演出——本场景从其结束状态顺势推进，"
                                       f"绝不从头重写/换机制重演/换角度复述该事件) ") + (scs[k].get("brief") or "")
                    intra_dup += 1
    if climax_chs:
        print(f"R15高潮章单场景化: {climax_chs} 章(高潮后续场景强制收束+SUMMARIZE)")
    if intra_dup:
        print(f"章内禁重演标注(非高潮): {intra_dup} 个次场景")
    # 规划产物落盘(Tier3): 复评/选优点修/B实验都要"同plan重起草",规划不再是一次性中间态
    for nm, obj in (("bible", bible), ("macro", macro), ("plan", plan)):
        (out_dir / f"{nm}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    # 2.5) 承重确定性审计（advisory，仅打印;0 下游消费）
    det_struct = {k: v for k, v in audit.deterministic_audit(bible, ordered).items() if v}
    print(f"规划:{len(plan['chapters'])}章/{n_scenes}场景 | 承重硬检残留={sum(len(v) for v in det_struct.values())} → 起草...")
    return {"plan": plan, "beats": beats, "ordered": ordered, "n_scenes": n_scenes, "macro": macro,
            "stats": {"dropped": dropped, "hs_found": hs_found, "hs_fixed": hs_fixed,
                      "ev_fixed": ev_fixed, "plan_dups": plan_dups, "pw_fixed": pw_fixed,
                      "place_drift": place_drift, "loc_coverage": [n_loc, len(ordered)]}}


async def _stage_draft(cli: Client, bible: dict, scenes: list, p: dict, plan: dict, ordered: list,
                       beats: list, n_scenes: int, n_cand: int, refine_rounds: int,
                       target_chars: int, prod: dict, out_dir: Path, force: bool = False) -> dict:
    """阶段3 draft(B1-4): 造峰+gold+控制面 → 波次并行起草、波间事实结算。→ {ch_texts, waves}。
    (settled/jobs 纯阶段内部,0 下游消费)。resume(B2): 每章落 draft/ch_NN.md;崩溃只重画未完成章
    (最贵阶段 ¥4-5 的细粒度续跑);settled 由已画章重算,且只结算"下游仍有未画章"的波(全续跑零结算¥)。"""
    draft_dir = out_dir / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    n_chapters = len(plan["chapters"])
    spc = max(1.0, n_scenes / max(1, n_chapters))
    target = int(target_chars / spc * 0.92)
    jobs = [(ci, si, sc) for ci, ch in enumerate(plan["chapters"]) for si, sc in enumerate(ch["scenes"])]

    def _rich(sc: dict) -> int:
        idx = sc.get("source_scene_index")
        s = scenes[idx] if isinstance(idx, int) and 0 <= idx < len(scenes) else {}
        return len(s.get("payoffs", [])) + len(s.get("hooks", []))
    rich = [_rich(sc) for _, _, sc in jobs]
    n_peaks = max(2, n_scenes // int(prod.get("peak_divisor", 12)))
    peaks = {0} | set(sorted(range(len(jobs)), key=lambda i: rich[i], reverse=True)[:n_peaks])
    gold = _load_gold(bible.get("voice", ""))
    n_peak = n_cand + int(prod.get("n_peak_bonus", 5))
    n_per = [n_peak if i in peaks else n_cand for i in range(len(jobs))]
    print(f"造峰:{len(peaks)}场用N={n_peak}+金标{refine_rounds}轮,其余N={n_cand}|金标={'有' if gold else '无'}")
    starts: list[int] = []
    _acc = 0
    for ch in plan["chapters"]:
        starts.append(_acc)
        _acc += len(ch["scenes"])
    settled: dict = {"deaths": {}, "power": {}, "items": {}}
    id_map: dict = {}                                    # R14 身份账源: canon 角色名→身份(role+阵营),主角也入账
    for c in bible.get("characters", []):
        n, role, fac = (c.get("name") or "").strip(), (c.get("role") or "").strip(), (c.get("faction") or "").strip()
        if n and role:
            id_map[n] = (role + (f"({fac})" if fac and fac not in role else ""))[:24]
    if p.get("name") and p.get("identity"):
        id_map[p["name"].strip()] = str(p["identity"])[:24]
    spine_map = _spine_map(bible)
    spine_global = (_spine_roster(spine_map) + _spine_facts(bible) + _spine_world(bible)
                    + _spine_alive_baseline(spine_map))   # 全书常量,算一次(§4:+存活基线事前预防)
    open_premise = _open_premise(bible, plan)            # B: 穿越/重生→第1章锁代入视角+原身一致+金手指不被点破
    if open_premise:
        print(f"穿越/重生开篇铁律: 检测到'{open_premise}'前提 → 第1章第1场注入代入视角/原身一致/金手指底牌铁律")
    if os.environ.get("HIKI_SPINE") == "1":
        print(f"Fact Spine: 冻结 {len(spine_map)} 角色规范名 + {len(bible.get('facts') or [])} 数值设定"
              f" + {len(bible.get('places') or [])} 地点 + 身份/体系钉死")

    async def _draft_chapter(ci: int) -> str:           # 跨章并行、章内顺序(后场景见本章已写前文)
        parts: list[str] = []
        prev_exit = (plan["chapters"][ci - 1].get("exit_state") or "") if ci > 0 else ""
        for si, sc in enumerate(plan["chapters"][ci]["scenes"]):
            i = starts[ci] + si
            plane = _control_plane(ci, si, plan, settled, prev_exit, id_map, spine_map, spine_global, open_premise)
            ctx = (ledger.format_context(ledger.state_before(ordered, i)) + _handoff(jobs, plan, i) + plane)
            if parts:
                ctx += ("\n【本章已写前文(其中事件已发生,绝不重演/换角度重写,直接顺势接续)】\n"
                        + "\n\n".join(parts)[-4000:])
            res = await _process_scene(cli, sc, bible, bible.get("voice", "网文白话"), target,
                                       n_per[i], gold=gold, is_peak=(i in peaks),
                                       refine_rounds=refine_rounds, context=ctx)
            parts.append(res["winner"])
        return "\n\n".join(parts)

    waves = _wave_bounds(beats, n_chapters, prod.get("wave_fallback_cuts"),
                         int(prod.get("wave_min_chapters", 4)))
    print(f"波次: {len(waves)} 波 {[(a + 1, b) for a, b in waves]} (act对齐+护栏)")
    ch_texts: list = [None] * n_chapters
    for ci in range(n_chapters):                         # resume: 载入已画章
        f = draft_dir / f"ch_{ci + 1:02d}.md"
        if not force and f.exists():
            ch_texts[ci] = f.read_text(encoding="utf-8")
    done = sum(1 for t in ch_texts if t is not None)
    if done:
        print(f"[resume] draft 已画 {done}/{n_chapters} 章 → 续画其余(settled 由已画章重算)")
    for wi, (wa, wb) in enumerate(waves):
        need = [ci for ci in range(wa, wb) if ch_texts[ci] is None]
        if need:
            parts = await asyncio.gather(*[_draft_chapter(ci) for ci in need])
            for ci, txt in zip(need, parts):
                ch_texts[ci] = txt
                (draft_dir / f"ch_{ci + 1:02d}.md").write_text(txt, encoding="utf-8")
        # 末波不结算;且只结算"下游仍有未画章"的波(全续跑→无下游待画→零结算¥)
        if wb < n_chapters and any(ch_texts[ci] is None for ci in range(wb, n_chapters)):
            wfacts = await prose_facts.extract_facts(cli, [ch_texts[ci] for ci in range(wa, wb)])
            _settle_facts(settled, wfacts, wa)
            print(f"  波{wi + 1}({wa + 1}-{wb}章)结算: 生死账{len(settled['deaths'])} 修为账{len(settled['power'])} "
                  f"里程碑账{sum(len(v) for v in settled.get('milestones', {}).values())}")
    return {"ch_texts": ch_texts, "waves": waves}


async def _ending_guard(cli: Client, ch_texts: list[str]) -> dict:
    """4f 结尾收束守卫: 末章断尾→补收束拍; 预告事件被时间跳跃跳过→计入门。→ {ch_texts,ending_fixed,climax_skipped}。
    (B1-5: 原内联;这里曾发生 cont 变量遮蔽崩 3 本的根因,独立 scope 根除该类。)"""
    ending_fixed, climax_skipped = "", ""
    sys_ec, usr_ec = prompts.ENDING_CHECK
    prev_tail = ch_texts[-2][-800:] if len(ch_texts) >= 2 else "（无）"
    for t in range(3):                            # retry-on-empty
        raw = await cli.complete("chunk_extract", sys_ec,
                                 usr_ec.format(prev_tail=prev_tail, tail=ch_texts[-1][-2500:]),
                                 json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
        ec = gate._safe_json(raw) or {}
        if "ok" in ec:
            break
    else:
        ec = {}
    if ec.get("skipped") is True:                 # 兑现跳空没法补写一场大战 → 交付门拦
        climax_skipped = (ec.get("skipped_what") or "预告事件").strip()
        print(f"结尾守卫: 预告事件被跳过({climax_skipped}) → 计入交付门")
    if ec.get("ok") is False:
        prob = (ec.get("problem") or "结尾被截断").strip()
        sys_ef, usr_ef = prompts.ENDING_FIX
        tail_fix = await cli.complete("draft", sys_ef, usr_ef.format(problem=prob, tail=ch_texts[-1][-2500:]),
                                      max_tokens=2000, temperature=0.5)
        tail_fix = _strip_markers((tail_fix or "").strip())
        if 100 <= len(tail_fix) <= 1500:          # 守卫:收束拍合理长度才追加
            ch_texts[-1] = ch_texts[-1].rstrip() + "\n\n" + tail_fix
            ending_fixed = prob
            print(f"结尾守卫: 检出断尾({prob}) → 已补收束拍{len(tail_fix)}字")
    return {"ch_texts": ch_texts, "ending_fixed": ending_fixed, "climax_skipped": climax_skipped}


async def _fact_audit_repair(cli: Client, ch_texts: list[str], out_dir: Path,
                             life_arcs: dict | None = None) -> dict:
    """4i 事实表对账 + 生死/修为定向修复 + §3.6 Spine薄网。原地修 ch_texts、落 fact_table.json。
    → {ch_texts,fact_table_ok,fact_audit_crashed,spine_net_num,spine_net_id,ft_deaths_verified,fact_adv}。
    (A1/A2 硬化:抽取覆盖不足/非预期崩溃→fact_audit_crashed 计入门;B1-5 独立 scope。)"""
    life_arcs = life_arcs or {}
    ft_deaths_verified: list[dict] = []
    fact_table_ok = False
    fact_audit_crashed = False
    spine_net_num, spine_net_id = 0, 0
    fact_adv: list[str] = []
    try:
        ft = await prose_facts.fact_table_audit(cli, ch_texts)
        ft_texts = list(ch_texts)                     # #4: 抽取时快照(下游 repair 会原地改 ch_texts)
        if ft.get("n_unaudited", 0) > max(3, len(ch_texts) // 4):   # A1: >25%章抽取失败→审计不可信
            fact_audit_crashed = True
            print(f"⚠ 事实表对账 {ft['n_unaudited']}/{len(ch_texts)} 章抽取失败——审计覆盖不足,计入交付门")
        cand = [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
                 "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
                for f in ft["findings"] if f.get("cat") == "生死"
                and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(ch_texts)]
        if cand:
            ft_deaths_verified = await prose_continuity.verify_revivals(cli, ch_texts, cand)
        if ft_deaths_verified:                        # R9b: 拦不如修——verify过的复活直喂修复器
            ch_texts = await prose_continuity.repair_revivals_smart(cli, ch_texts, ft_deaths_verified)
            residual = await prose_continuity.verify_revivals(cli, ch_texts, ft_deaths_verified)
            # 项1 复活beat检测:复写**清楚交代了归来机制**(③忠实复活,内部自洽)→降advisory;死后突兀出场无说明(②漏复活/真矛盾)→进门。
            # beat检测失败(None)时退回源弧和解(life_arcs:dies_returns→放)。实证:桑念/上官尔蓝(树精/借尸还魂)放、纳珈(突兀出场)拦。
            checked = await prose_continuity.verify_revival_beats(cli, ch_texts, residual)
            gate_rev, adv_rev = [], []
            for r in checked:
                rendered = r.get("beat_rendered")
                if rendered is None:                      # beat检测失败→退回源弧和解
                    rendered = audit.reconcile_revival(life_arcs, r.get("who")) == "advisory"
                (adv_rev if rendered else gate_rev).append(r)
            print(f"事实表生死: {len(ft_deaths_verified)}处verify → 修复 → 残留{len(residual)}"
                  f"(进门{len(gate_rev)}/复活beat已渲染降级{len(adv_rev)})")
            if adv_rev:
                fact_adv += [f"{r.get('who')}死后复活beat已渲染({(r.get('beat_mech') or '')[:24]}),内部自洽→降advisory(非死人复活硬伤)"
                             for r in adv_rev]
            ft_deaths_verified = gate_rev
        ft["生死_verify后"] = [f"{r['who']}(第{r['revive_ch'] + 1}章)" for r in ft_deaths_verified]
        pw_cand = [f for f in ft["findings"] if f.get("cat") == "数值" and f.get("conf") == "中"
                   and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(ch_texts)]
        pw_fixed_n = 0
        if pw_cand:
            sys_pv, usr_pv = prompts.POWER_VERIFY
            pchecks = await asyncio.gather(*[
                cli.complete("chunk_extract", sys_pv,
                             usr_pv.format(who=f.get("who", ""), why=f.get("why", ""),
                                           text=ch_texts[f["ch_b"] - 1][:6000]),
                             json_mode=True, max_tokens=300, temperature=0.1) for f in pw_cand])
            pw_real = [f for f, c in zip(pw_cand, pchecks)
                       if (gate._safe_json(c) or {}).get("real") is True]
            if pw_real:
                sys_pr, usr_pr = prompts.POINT_REPAIR
                prew = await asyncio.gather(*[
                    cli.complete("draft", sys_pr,
                                 usr_pr.format(issues=f"修为/数值写岔:{f['why']}——本章对「{f['who']}」的"
                                               f"该数值统一为此前已确立的较高值,禁止回退",
                                               text=ch_texts[f["ch_b"] - 1][:14000]),
                                 max_tokens=8000, temperature=0.3) for f in pw_real])
                for f, t in zip(pw_real, prew):
                    t = _strip_markers((t or "").strip())
                    if t and len(t) >= len(ch_texts[f["ch_b"] - 1]) * 0.7:
                        ch_texts[f["ch_b"] - 1] = t
                        pw_fixed_n += 1
                print(f"修为闭环: {len(pw_cand)}候选→verify真{len(pw_real)}→修复{pw_fixed_n}")
        if os.environ.get("HIKI_SPINE") == "1":       # §3.6 薄网: cross_check真矛盾(对照冻结Spine)进交付门
            spine_net_num = sum(1 for f in ft["findings"] if f.get("cat") == "数值" and f.get("conf") == "低")
            if spine_net_num < 2 and any(f.get("cat") == "身份" for f in ft["findings"]):   # #7 短路
                await prose_facts.verify_identity(cli, ft["findings"], ft_texts)            # ①,抽取时快照#4
                spine_net_id = sum(1 for f in ft["findings"] if f.get("cat") == "身份" and f.get("real"))
            ft["spine_net"] = {"数值真矛盾": spine_net_num, "身份真矛盾": spine_net_id}
        fact_adv = [f["why"] for f in ft["findings"] if f.get("conf") in ("高", "中")]
        (out_dir / "fact_table.json").write_text(json.dumps(ft, ensure_ascii=False, indent=2), encoding="utf-8")
        fact_table_ok = True
    except json.JSONDecodeError as e:                 # 解析类=flaky LLM,容忍为 advisory
        fact_adv = [f"事实表对账解析失败(flaky):{e}"]
    except Exception as e:                            # A2: 非预期(代码bug/硬故障)→ 计入门
        fact_adv = [f"事实表对账中断:{type(e).__name__}:{e}"]
        fact_audit_crashed = True
        print(f"⚠ 事实表对账非预期中断({type(e).__name__}: {e})——承重审计不完整,计入交付门")
    if fact_adv:
        print(f"事实表对账(advisory): {len(fact_adv)} 条: {'；'.join(fact_adv[:3])}"
              f"{' | 生死verify后:' + str(len(ft_deaths_verified)) + '条进门' if ft_deaths_verified else ''}")
    return {"ch_texts": ch_texts, "fact_table_ok": fact_table_ok, "fact_audit_crashed": fact_audit_crashed,
            "spine_net_num": spine_net_num, "spine_net_id": spine_net_id,
            "ft_deaths_verified": ft_deaths_verified, "fact_adv": fact_adv}


async def _plane_check(cli: Client, ch_texts: list[str], plan: dict) -> tuple[list[str], list[str]]:
    """4j 控制面核对: 章正文 vs 近3章 exclusion 清单, 检版本互斥重演(高召回第一段)。
    第二段裁决: 对每个 raw hit 判 真重演 vs 视角转述(存疑保留), 只把真重演喂闸门。
    返回 (真重演清单, 视角转述滤除清单)。"""
    try:
        sys_pc, usr_pc = prompts.PLANE_CHECK
        sys_aj, usr_aj = prompts.REENACT_ADJUDICATE

        async def _pc(ci: int) -> list[tuple[int, str]]:
            excl = []
            for j in range(max(0, ci - 3), ci):
                for k in (plan["chapters"][j].get("key_events") or []):
                    if str(k).strip():
                        excl.append(f"第{j + 1}章:{str(k)[:40]}")
            if not excl:
                return []
            raw = await cli.complete("chunk_extract", sys_pc,
                                     usr_pc.format(exclusion="\n".join(excl[-6:]), text=ch_texts[ci][:6000]),
                                     json_mode=True, max_tokens=300, temperature=0.1)
            r = gate._safe_json(raw) or {}
            return [(ci, str(x)[:40]) for x in (r.get("reenacted") or []) if str(x).strip()]

        async def _adjudicate(ci: int, event: str) -> bool:
            raw = await cli.complete("chunk_extract", sys_aj,
                                     usr_aj.format(event=event, text=ch_texts[ci][:6000]),
                                     json_mode=True, max_tokens=200, temperature=0.1)
            r = gate._safe_json(raw) or {}
            return r.get("reenact") is not False        # 存疑保留: 仅显式 false 判视角转述

        raw_pairs = [p for lst in await asyncio.gather(*[_pc(ci) for ci in range(len(ch_texts))]) for p in lst]
        if not raw_pairs:
            return [], []
        keeps = await asyncio.gather(*[_adjudicate(ci, ev) for ci, ev in raw_pairs])
        reenact_hits, filtered = [], []
        for (ci, ev), keep in zip(raw_pairs, keeps):
            label = f"第{ci + 1}章重演[{ev}]"
            (reenact_hits if keep else filtered).append(label)
        if reenact_hits or filtered:
            print(f"控制面核对: {len(reenact_hits)} 真重演 + {len(filtered)} 视角转述滤除")
        return reenact_hits, filtered
    except Exception as e:
        print(f"控制面核对跳过:{type(e).__name__}")
        return [], []


def _run_ship_gate(bible: dict, ordered: list, final: str, det: list, advisory: list,
                   seam_residual: int, sig: dict, gate_thr: dict) -> dict:
    """B1-3(轻): 37维审计 + 信号组装 + 门决策。纯函数(0 LLM,可测)。
    sig=运行时连续性信号 dict(dark_ratio/climax_skipped/fact_table_ok/ft_deaths_verified/
    reenact_hits/intra_rep/spine_net_num/spine_net_id/fact_audit_crashed)。
    → {audit_struct,audit_fore,audit_mech,final_consistent,ship_issues,deliverable}。"""
    audit_struct = {k: v for k, v in audit.deterministic_audit(bible, ordered).items() if v}
    audit_fore = audit.foreshadow_advisory(ordered)
    audit_mech = audit.mechanical_audit(final)
    too_short = [d for d in det if d.startswith("过短")]
    # 篇幅类(过短/超长)不污染一致性位——过短≥3章由门单独拦
    final_consistent = not advisory and not [d for d in det if "长" not in d and "短" not in d]
    ship_signals = {
        "阵营串线": len(audit_struct.get("维2阵营串线") or []),
        "过短章数": len(too_short),
        "暗黑比": sig["dark_ratio"],
        "预告跳过": sig["climax_skipped"],
        "plan维14复活": len(audit_struct.get("维14死人复活") or []),
        "事实表跑过": sig["fact_table_ok"],
        "事实表复活残留": len(sig["ft_deaths_verified"]),
        "残缝": seam_residual,
        "final_consistent": final_consistent,
        "事件重演": len(sig["reenact_hits"]),
        "章内双版本": [f"第{i + 1}章{r:.0%}" for i, r in sig["intra_rep"]] if sig["intra_rep"] else None,
        "数值真矛盾": sig["spine_net_num"],
        "身份真矛盾": sig["spine_net_id"],
        "承重审计崩溃": sig["fact_audit_crashed"],
        "开篇代入感": sig.get("immersion_score"),
        "早段重复": sig.get("早段重复", 0),
    }
    ship_issues = gate.evaluate_ship_gate(ship_signals, gate_thr)
    return {"audit_struct": audit_struct, "audit_fore": audit_fore, "audit_mech": audit_mech,
            "final_consistent": final_consistent, "ship_issues": ship_issues,
            "deliverable": not ship_issues}


async def _stage_finalize(cli: Client, src: Path, out_dir: Path, bible: dict, final: str,
                          deliverable: bool, ship_issues: list, report: dict,
                          open_premise: str = "", immersion: dict | None = None) -> dict:
    """阶段9 finalize(B1-2): gen_title + 输出《书名》.md + craft审计 + 落 report.json。
    report 主体在 run() 组装(引用各相位局部);此处补 title/output/craft 字段并落盘后返回。"""
    tmeta = await gen_title(cli, bible, ending=final)
    title, tagline = tmeta.get("title", ""), tmeta.get("tagline", "")
    safe = _safe_filename(title, fallback=_safe_filename(src.stem))
    book = f"《{title}》\n\n{final}" if title else final   # 甲:纯文本头,无 markdown 记号
    (out_dir / "final.md").write_text(final, encoding="utf-8")
    out_name = _book_filename(out_dir.name, safe)          # <源ID><新书名>.txt(干净交付名)
    out_path = _delivery_path(out_dir, deliverable, out_name)   # 可交付→_deliverable/;不可交付→_rejected/
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(book, encoding="utf-8")
    if deliverable:
        print(f"成品命名：{out_name} —— {tagline}  → {out_path.parent}")
    else:
        print(f"⛔ 交付门拦截：{'；'.join(ship_issues)} → _rejected/{out_name}（重跑或拒收，绝不流向编辑）")
    try:                                          # craft 仅 advisory，绝不为它丢成品/报告
        audit_craft = await audit.craft_audit(cli, final[:9000])
    except Exception as e:
        audit_craft = [f"(craft审计跳过:{type(e).__name__})"]
    if immersion is None:                          # 兜底:run() 已门前算好并传入;独立调用时才现算
        immersion = await audit.opening_immersion_audit(cli, final, open_premise)
    imm_warn = (immersion.get("代入锚") == "warn" or immersion.get("premise清晰") == "warn"
                or (isinstance(immersion.get("代入感分"), (int, float)) and immersion["代入感分"] < 60))
    if imm_warn:
        print(f"⚠ 开篇代入感审计: 代入锚={immersion.get('代入锚')} premise={immersion.get('premise清晰')} "
              f"代入感分={immersion.get('代入感分')} | {'；'.join(immersion.get('issues') or [])[:120]}")
    report.update({"title": title, "tagline": tagline, "alt_titles": tmeta.get("alts", []),
                   "output_file": str(out_path), "audit_人+故事性_craft(advisory)": audit_craft or ["无"],
                   "开篇代入感审计(advisory)": immersion})
    if deliverable:                                    # 通过:总历时终点延到 Assemble 结束(含命名/审计)
        report["seconds"] = round(time.time() - _started_at(out_dir, time.time()), 1)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def run(src: Path, n_ch: int = 60, n_chunks: int = 12, n_cand: int = 3,
              refine_rounds: int = 5, min_grade: str | None = None,
              out_dir: Path | None = None, force: bool = False) -> dict:
    t0 = time.time()
    _cfg = config.load("pipeline") or {}                # D2/D3: 结构/成本旋钮入 config
    _out_cfg, prod = _cfg.get("output") or {}, _cfg.get("production") or {}
    target_chars = int(_out_cfg.get("chars_per_chapter", 3500))
    out_dir = out_dir or (Path("output") / (src.stem + "_full"))   # M3: best-of-K 并行跑用独立目录
    started = _started_at(out_dir, t0)                              # 单一总历时:首次 ingest 持久化,续跑不覆盖
    cli = Client()
    # 1) mine + 2) plan(B1 拆为纯阶段,各自 resume;B2)
    mine = await _stage_mine(cli, src, out_dir, n_ch, n_chunks, min_grade, prod, force)
    if mine.get("rejected"):                                        # 早拒:停在 mine 判定点
        rep = mine["report"]
        rep.setdefault("seconds", round(time.time() - started, 1))
        (out_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        return rep
    bible, scenes, grade = mine["bible"], mine["scenes"], mine["grade"]
    meta, clean = mine["meta"], mine["clean"]
    all_scene_count, chunks = mine["all_scene_count"], mine["chunks"]
    p = bible.get("protagonist", {})                     # 起草区 POV/人名归一仍用 p
    pl = await _stage_plan(cli, bible, scenes, out_dir, n_ch, force)
    plan, beats, ordered = pl["plan"], pl["beats"], pl["ordered"]
    n_scenes, macro = pl["n_scenes"], pl["macro"]
    _ps = pl.get("stats", {})                            # plan-repair 统计(供 report;resume 时缺省)
    dropped = _ps.get("dropped", [])
    hs_found, hs_fixed = _ps.get("hs_found", 0), _ps.get("hs_fixed", 0)
    ev_fixed, plan_dups, pw_fixed = _ps.get("ev_fixed", []), _ps.get("plan_dups", []), _ps.get("pw_fixed", [])

    # 3) draft(B1-4): 造峰+gold+控制面 → 波次并行起草、波间结算(逐章落盘,mid-draft resume)
    d = await _stage_draft(cli, bible, scenes, p, plan, ordered, beats, n_scenes, n_cand,
                           refine_rounds, target_chars, prod, out_dir, force)
    ch_texts, waves = d["ch_texts"], d["waves"]

    # 4) 后端：双向控字 + 硬截断 + POV统一 + 人名归一(双名守卫+近似名) + advisory连续性
    ch_texts = await asyncio.gather(*[_fit_chapter(cli, t, target_chars) for t in ch_texts])
    short = [i for i, t in enumerate(ch_texts) if len(t) < target_chars * 0.7]   # 扩写flaky残留→再试一次
    if short:                                                            # (过短≥3章会被交付门拦)
        refit = await asyncio.gather(*[_fit_chapter(cli, ch_texts[i], target_chars) for i in short])
        for i, t in zip(short, refit):
            ch_texts[i] = t
        print(f"控字: {len(short)} 章过短二次扩写")
    # 末章给1.6×上限(治断尾: 硬截断会把结局收束拍切掉,Fable预评坐实'最后一句是高潮中断')
    ch_texts = [_truncate(t, int(target_chars * (1.6 if i == len(ch_texts) - 1 else 1.15)))
                for i, t in enumerate(ch_texts)]
    # 4a) POV：把误用人称的离群章统一回全书主人称(治整章第一人称误用)
    person, outliers = _pov_outliers(ch_texts)
    if outliers:
        print(f"POV: 第{person}人称书，{len(outliers)}个离群章定向重写: {outliers}")
        sys_pv, usr_pv = prompts.POV_FIX
        fixed = await asyncio.gather(*[
            cli.complete("draft", sys_pv, usr_pv.format(person=person, name=p.get("name", "他"),
                                                        text=ch_texts[i]),
                         max_tokens=8000, temperature=0.3) for i in outliers])
        for i, t in zip(outliers, fixed):
            t = _strip_markers(t)
            if t and _first_person_ratio(t) < 0.5:    # 修成功才采用
                ch_texts[i] = t
    # 4a2) Tier2 套话硬重写门(D: 旋钮入 config,human-eval-5 校准默认不变)
    _dc = _cfg.get("decliche") or {}
    ch_texts, decliche_done = await _decliche_chapters(
        cli, ch_texts, cap=int(_dc.get("cap", 22)),
        over_book_min=int(_dc.get("over_book_min", 8)), per_chapter_min=int(_dc.get("per_chapter_min", 2)))
    if decliche_done:
        print(f"去套话门: 重写 {len(decliche_done)} 章")
    valid_names = set()
    for nm in [p.get("name", "")] + (p.get("aliases") or []):
        for part in str(nm).replace("、", "/").split("/"):
            if part.strip():
                valid_names.add(part.strip())
    for c in bible.get("characters", []):
        if c.get("name"):
            valid_names.add(c["name"].strip())
        for a in c.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                valid_names.add(a.strip())
    # 4b) 人名一致：靠 REDUCE 别名合并 + 下面 continuity_check(LLM, 安全归一到canon)。
    #     确定性编辑距离归一在中文里误报灾难性(强大→强森) → 已弃用。
    final = _assemble(plan, ch_texts)
    cont = await gate.continuity_check(cli, final[:60000], bible)
    applied = []
    for f in (cont.get("name_fixes") or []):
        w, r = (f.get("wrong") or "").strip(), (f.get("right") or "").strip()
        # 只归一到**冻结 canon 名**：r 必须是合法名，否则 LLM 可能返回指令串/解释 → 污染正文
        if w and r and w != r and w not in valid_names and r in valid_names and len(r) <= 8:
            ch_texts = [t.replace(w, r) for t in ch_texts]
            applied.append(f"{w}→{r}")
    # 4c) PROSE 层连续性(治 plan 审计够不到的:同人异名漂移 + 死人复活)——作用在生成正文上
    ch_texts, prose_rep = await prose_continuity.audit_and_repair(cli, ch_texts, canon_names=valid_names,
                                                                  source_text=clean)
    print(f"prose连续性: 异名归一={prose_rep['prose_name_fixes']} | 复活修复={prose_rep['prose_revivals_fixed']}")
    gate_thr = (config.load("pipeline") or {}).get("ship_gate") or gate.SHIP_GATE_DEFAULTS  # D1: 交付门阈值入config
    # 4d) PROSE 内容过滤(治暗黑厌女:bible级content_flag失灵,读实际场景净化)
    ch_texts, dark_rep = await prose_continuity.content_filter(cli, ch_texts)
    values_reject = dark_rep["dark_ratio"] > gate_thr["dark_ratio_max"]   # 暗黑饱和→净化救不动,应拒收
    if dark_rep["dark_fixed"] != ["无"]:
        print(f"内容过滤: 净化 {len(dark_rep['dark_fixed'])} 章 (暗黑比{dark_rep['dark_ratio']}"
              f"{'→暗黑饱和,标记拒收' if values_reject else ''})")
    # 4e) 章缝衔接检修(人工头号缺陷:相邻章时空/动作倒退,如'前章已开车,后章才拿钥匙')
    ch_texts, seam_fixed, seam_found, seam_unresolved = await _seam_pass(cli, ch_texts)
    if seam_found:
        print(f"章缝: 检出 {seam_found} 处断裂, 修复净 {len(seam_fixed)} 处, 未净 {len(seam_unresolved)} 处: {seam_fixed}")
    # 4e2) R11 邻章事件版本互斥检修(缺陷类演化: 整章重演→同章双版本→邻章双版本;
    #      M0限界: 只管后章**头部**重演(检出→重写开头,采用守卫),深处互斥归点修通道)
    ch_texts, adj_fixed, adj_found, adj_unresolved = await _adj_dup_pass(cli, ch_texts)
    if adj_found:
        print(f"邻章版本: 检出 {adj_found} 对头部重演, 修复净 {len(adj_fixed)} 对, 未净 {len(adj_unresolved)} 对: {adj_fixed[:6]}")
    # 4f) 结尾收束守卫(B1-5 → _ending_guard)
    eg = await _ending_guard(cli, ch_texts)
    ch_texts, ending_fixed, climax_skipped = eg["ch_texts"], eg["ending_fixed"], eg["climax_skipped"]
    # 4g) 倒叙哨兵(确定性advisory): 章首即倒叙=重演前章事件的直接信号
    flashbacks = _flashback_advisory(ch_texts)
    if flashbacks:
        print(f"倒叙哨兵: {flashbacks}")
    # 4h) 章尾句界强制(残句裁掉,治'断在逗号上')
    ch_texts = [_trim_tail(t) for t in ch_texts]
    # 4i) 事实表对账+生死/修为修复+薄网(B1-5 → _fact_audit_repair)
    fa = await _fact_audit_repair(cli, ch_texts, out_dir, bible.get("life_arcs"))
    ch_texts = fa["ch_texts"]
    fact_table_ok, fact_audit_crashed = fa["fact_table_ok"], fa["fact_audit_crashed"]
    spine_net_num, spine_net_id = fa["spine_net_num"], fa["spine_net_id"]
    ft_deaths_verified, fact_adv = fa["ft_deaths_verified"], fa["fact_adv"]
    # 4j) 控制面核对(B1-5 → _plane_check)
    reenact_hits, reenact_filtered = await _plane_check(cli, ch_texts, plan)
    final = _assemble(plan, ch_texts)

    # R14 章内自重复检测(确定性,0-LLM): 治整章双版本(ch59飞升写两遍/讨债两版类语义重演)。
    # 12-gram 章内两半重合>8%=同章把同一事件演两遍(读者可见killer);final_consistent兜底不可靠(ch59漏放)。
    def _intra_repeat(t: str, thr: float = 0.08) -> float:
        s = _re.sub(r"\s", "", t or "")
        if len(s) < 800:
            return 0.0
        h = len(s) // 2
        g1 = {s[i:i + 12] for i in range(0, h - 12, 3)}
        g2 = {s[i:i + 12] for i in range(h, len(s) - 12, 3)}
        return (len(g1 & g2) / max(1, min(len(g1), len(g2)))) if g1 and g2 else 0.0
    intra_rep = [(i, r) for i, t in enumerate(ch_texts) if (r := _intra_repeat(t)) > gate_thr["intra_repeat_thr"]]
    if intra_rep:
        print(f"章内自重复(整章双版本): {[(f'第{i+1}章', f'{r:.0%}') for i, r in intra_rep]}")

    det = [i for t in ch_texts for i in gate.deterministic_checks(t, bible, target_chars)]
    advisory_raw = [o for o in (cont.get("other_issues") or []) if o]
    advisory = await _verify_advisories(cli, advisory_raw, bible)   # R11 灰区判读后才进fc/门
    if len(advisory) < len(advisory_raw):
        print(f"灰区判读: advisory {len(advisory_raw)}→{len(advisory)} (滤掉龙套/延伸/口径差类)")

    # A接线(1-3,advisory): 逐实体事件/状态账。**不进门**——实测低召回(漏隐式死亡)+互斥遭遇多非真矛盾,
    # 仅记 report 供人工复核;死人复活已由 fact_table 生死门覆盖。behind HIKI_SPINE。
    event_adv: list[str] = []
    if os.environ.get("HIKI_SPINE") == "1":
        try:
            ev = await event_audit.event_state_audit(cli, ch_texts, bible)
            event_adv = [f"{c['entity']}·{c['type']}({'真矛盾' if c.get('real') else '存疑'}): {c['detail']}"
                         for c in ev["all_candidates"]]
            if ev["n_real"]:
                print(f"事件状态账(advisory): {ev['n_real']}真矛盾/{len(ev['all_candidates'])}候选/{ev['checked']}实体")
        except Exception as e:                       # 失败隔离:不崩整本
            print(f"事件状态账跳过(flaky): {type(e).__name__}: {e}")

    # C: 开篇代入感审计——提到门前算(低分进门,见 gate.opening_immersion_min);算一次,复用到 finalize
    open_premise = _open_premise(bible, plan)
    immersion = await audit.opening_immersion_audit(cli, final, open_premise)   # 标注穿越/重生
    early_rep = await audit.early_repeat_audit(cli, ch_texts)                    # 早段同事件重述(填 signals.early_repeat)
    # 5+5.5) 37维审计 + 交付门(B1-3轻: 纯函数 _run_ship_gate,可测;阈值在 config)
    sig = {"dark_ratio": dark_rep["dark_ratio"], "climax_skipped": climax_skipped,
           "fact_table_ok": fact_table_ok, "ft_deaths_verified": ft_deaths_verified,
           "reenact_hits": reenact_hits, "intra_rep": intra_rep, "spine_net_num": spine_net_num,
           "spine_net_id": spine_net_id, "fact_audit_crashed": fact_audit_crashed,
           "immersion_score": immersion.get("代入感分"),
           "早段重复": early_rep["count"]}
    g = _run_ship_gate(bible, ordered, final, det, advisory, seam_found - len(seam_fixed), sig, gate_thr)
    audit_struct, audit_fore, audit_mech = g["audit_struct"], g["audit_fore"], g["audit_mech"]
    final_consistent, ship_issues, deliverable = g["final_consistent"], g["ship_issues"], g["deliverable"]

    # 9) finalize(B1-2): report 主体在此组装(引用各相位局部),title/输出/落盘交给 _stage_finalize
    report = {
        "deliverable": deliverable, "交付门": ship_issues or ["通过"],
        "source": src.name, "wan_zi": meta.approx_wan_zi, "out_chapters": len(plan["chapters"]),
        "scenes": n_scenes, "all_scene_count": all_scene_count, "chunks": chunks,
        "grade": grade, "central_conflict": macro.get("central_conflict", ""),
        "砍掉支线": dropped or ["无"],
        "final_chars": len(final), "avg_chapter_chars": len(final) // max(1, len(plan["chapters"])),
        "spotlight_variety": _variety(beats),
        "mechanical": det or ["无"], "name_fixes_applied": applied or ["无"],
        "套话门_重写章数": len(decliche_done),
        "plan握手": f"检出{hs_found}/重规划{hs_fixed}",
        "大事件禁演": ev_fixed or ["无"],
        "plan邻章查重": plan_dups or ["无"],
        "波次": str([(a + 1, b) for a, b in waves]),
        "控制面重演核对": reenact_hits or ["无"],
        "控制面重演_视角转述滤除": reenact_filtered or ["无"],
        "邻章版本_检出": adj_found, "邻章版本_修复": adj_fixed or ["无"],
        "邻章版本_修复未净": adj_unresolved or ["无"],
        "事实表对账(advisory)": fact_adv or ["无"],
        "事实表生死_verify后": [f"{r['who']}(第{r['revive_ch'] + 1}章)" for r in ft_deaths_verified] or ["无"],
        "残句(advisory)": audit.broken_prose(ch_texts) or ["无"],
        "时代锚(advisory)": audit.era_anachronism(
            ch_texts, str(bible.get("voice", "")) + str(bible.get("setting", ""))) or ["无"],
        "章缝_检出": seam_found, "章缝_修复": seam_fixed or ["无"],
        "章缝_修复未净": seam_unresolved or ["无"],
        "早段重复(ch1-k)": early_rep["pairs"] or ["无"],
        "结尾守卫_补收束": ending_fixed or "无需",
        "倒叙哨兵(advisory)": flashbacks or ["无"], "预告跳空": climax_skipped or "无",
        "修为钉回_plan": pw_fixed[:6] or ["无"],
        "prose_异名归一": prose_rep["prose_name_fixes"], "prose_死人复活修复": prose_rep["prose_revivals_fixed"],
        "内容过滤_暗黑净化": dark_rep["dark_fixed"], "暗黑比": dark_rep["dark_ratio"],
        "事件状态账(advisory)": event_adv or ["无"],
        "values_reject(暗黑饱和应拒)": values_reject,
        "audit_承重_确定性硬检": audit_struct or {"全过": "✓"},
        "audit_维7伏笔序(advisory)": audit_fore or ["无"],
        "audit_笔力_机械": audit_mech or {"全过": "✓"},
        "advisory_issues": advisory or ["无"],
        "final_consistent": final_consistent,
        "calls": cli.calls, "cost_cny": round(cli.cost_cny, 2),
        "seconds": round(time.time() - started, 1),    # 此处=门拒终点(Evaluate);通过则 finalize 重算到 Assemble
    }
    # 冻结信号向量(可合池):每本落同一套 → 喂质量代理飞轮。人评行直接拷 report["signals"]。
    report["signals"] = signals.build_signal_vector(
        deliverable=deliverable, grade=(grade or {}).get("grade"),
        immersion_score=immersion.get("代入感分"), reenact_hits=len(reenact_hits),
        seam_detected=seam_found, seam_residual=seam_found - len(seam_fixed),
        dark_ratio=dark_rep["dark_ratio"], spine_num_contra=spine_net_num,
        spine_id_contra=spine_net_id, ft_revival_residual=len(ft_deaths_verified),
        too_short_chapters=len([d for d in det if d.startswith("过短")]),
        final_consistent=final_consistent, intra_repeat_chapters=len(intra_rep),
        early_repeat=early_rep["count"])
    # title/output/craft 字段 + 文件落盘由 finalize 阶段补全
    return await _stage_finalize(cli, src, out_dir, bible, final, deliverable, ship_issues, report,
                                 open_premise, immersion)         # C: 复用门前算好的 immersion(不重算)


def _variety(beats: list[dict]) -> str:
    """爽点类型跨章变化度（治通胀的指标）：相邻重复率越低越好。"""
    types = [b.get("pt") or b.get("spotlight_payoff_type") for b in beats
             if b.get("pt") or b.get("spotlight_payoff_type")]
    if len(types) < 2:
        return "n/a"
    repeats = sum(1 for a, b in zip(types, types[1:]) if a == b)
    return f"相邻重复{repeats}/{len(types)-1} | 种类{len(set(types))}"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--chapters", type=int, default=60)
    ap.add_argument("--chunks", type=int, default=12)
    ap.add_argument("-n", "--candidates", type=int, default=3)
    ap.add_argument("--refine-rounds", type=int, default=3, help="实证2-3轮即够,多轮震荡")
    ap.add_argument("--min-grade", default=None, choices=["S", "A", "B", "C", "D"],
                    help="源分级门槛:低于此档拒收(如 A=只产S/A好源)")
    ap.add_argument("--spine", action=argparse.BooleanOptionalAction, default=True,
                    help="Fact Spine 事前一致性(质量默认开;--no-spine 关闭)")
    a = ap.parse_args()
    os.environ["HIKI_SPINE"] = "1" if a.spine else "0"
    rep = asyncio.run(run(Path(a.src), a.chapters, a.chunks, a.candidates, a.refine_rounds,
                          min_grade=a.min_grade))
    print("\n=== 全书报告 ===")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"\n成品 → output/{Path(a.src).stem}_full/final.md（请人工评判）")


if __name__ == "__main__":
    main()
