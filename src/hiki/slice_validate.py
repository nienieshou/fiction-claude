"""切片验证（M0 内核）：拿 90 标杆源的前若干章，跑 提取→规划→锦标赛起草→对照评估。

目的：最便宜地验证最危险的假设——纯 DeepSeek 能否把 90 源场景"提纯+选优"成更好看的成品。
产出供人工评判（用户=评分者）。用法：python -m hiki.slice_validate <源.txt> [--src-chapters 12] [--out-chapters 3] [-n 3]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from . import prompts, gate, ledger, audit
from .llm_validate import complete_validated
from .client import Client
from .ingest import ingest
from .textnum import SOURCE_CH_RE as _CH_RE


def _slice_source(clean_txt: str, n_src: int) -> str:
    """取前 n_src 章作为切片源。"""
    pos = [m.start() for m in _CH_RE.finditer(clean_txt)]
    if len(pos) > n_src:
        return clean_txt[: pos[n_src]].strip()
    return clean_txt.strip()


async def _extract_dna(cli: Client, slice_src: str) -> dict:
    """EXTRACT 抽取(健壮): 重试解析, 终败干净报错(非裸 JSONDecodeError)。"""
    sys_e, usr_e = prompts.EXTRACT
    dna = await complete_validated(cli, "extract", sys_e, usr_e.format(source=slice_src[:40000]),
                                   schema=lambda r: isinstance(r, dict) and isinstance(r.get("scenes"), list) and bool(r["scenes"]),
                                   retries=2, json_mode=True, max_tokens=8000, temperature=0.3)
    if dna is None:
        raise RuntimeError("EXTRACT 失败:抽取 JSON 解析/重试均无效(flaky 截断或无场景),请重跑。")
    return dna


_HEADER_RE = re.compile(r"^\s*(#+.*|.*场景[：:].*|---+|===+)\s*$", re.M)
# 出稿污染：扩写/改写点评、示范、写作指导、markdown 加粗漏进正文
_META_RE = re.compile(r"扩写思路|你看看|区别在哪|问题在哪|这样改|改写思路|原文的问题|示范版?|"
                      r"如下是|以下是改|\*\*|作者解释|写作建议")


def _strip_markers(text: str) -> str:
    """去掉漏进正文的标题/场景标记/分隔线。"""
    return "\n".join(ln for ln in text.split("\n") if not _HEADER_RE.match(ln)).strip()


async def _draft_candidates(cli: Client, sc: dict, bible: dict, voice: str,
                            target: int, n: int, gold: str = "", context: str = "",
                            tmpl: tuple[str, str] | None = None) -> list[str]:
    sys_p, usr_t = tmpl or prompts.DRAFT          # Tier3: 顺序起草用 DRAFT_SEQ(history-first)注入
    p = bible.get("protagonist", {})
    _chs = [c for c in bible.get("characters", []) if c.get("name")]   # 容缺:无名角色跳过
    chars = "、".join(f"{c['name']}({c.get('gender','')}/{c.get('role','')})" for c in _chs)
    char_goals = "；".join(f"{c['name']}:{c.get('goal','')}" for c in _chs if c.get("goal"))
    usr = usr_t.format(
        p_name=p.get("name", "主角"), p_gender=p.get("gender", ""), p_identity=p.get("identity", ""),
        characters=chars or "（见设定）", setting=bible.get("setting", ""),
        target=target, voice=voice, brief=sc.get("brief") or "推进本章剧情、保钩子爽点",
        source_ref=sc.get("source_ref", ""),
        gold=gold or "（无）", context=context or "（本场景为开篇，无前情）",
        p_goal=p.get("goal", "（推进剧情）"), p_arc=p.get("arc", "（主动掌控）"),
        char_goals=char_goals or "（各有私心）")  # 人维:主角目标/弧 + 配角动机
    temps = ([0.8, 1.0, 1.2] + [1.0] * n)[:n]
    tasks = [cli.complete("draft", sys_p, usr, max_tokens=8000, temperature=t) for t in temps]
    return [_strip_markers(c) for c in await asyncio.gather(*tasks)]


async def _process_scene(cli: Client, sc: dict, bible: dict, voice: str, target: int, n: int,
                         gold: str = "", is_peak: bool = False, refine_rounds: int = 5,
                         context: str = "", tmpl: tuple[str, str] | None = None) -> dict:
    """起草 N 候选（注入前情账本防重复）→ 锦标赛选优 →（peak）对照金标多轮精修。"""
    cands = await _draft_candidates(cli, sc, bible, voice, target, n, gold=gold[:600], context=context,
                                    tmpl=tmpl)
    cands = [c for c in cands if c.strip()] or cands     # 防全空
    # M1(stable-75): 选优判别器 PICK→GOLD_PK。判别器实验实锤: PICK(绝对自评)≈噪声(与对照仅25%一致,
    # Goodhart),对照GOLD_PK(候选vs金标95锚打分)75%命中。有金标→对照打分选最高(吃模型尾部);无金标退PICK。
    if gold and len(cands) > 1:
        pks = await asyncio.gather(*[gate.gold_pk(cli, c, gold) for c in cands])
        scores = [float(pk.get("score") or 0) for pk in pks]
        wi_idx = max(range(len(cands)), key=lambda i: scores[i])
        win = cands[wi_idx]
        pick = {"winner": wi_idx + 1, "method": "gold_pk", "scores": scores}
    else:                                                # 无金标(题材不匹配_load_gold空)→退PICK
        sys_p, usr_t = prompts.PICK
        listed = "\n\n".join(f"【候选{i+1}】\n{c}" for i, c in enumerate(cands))
        raw = await cli.complete("pk_final", sys_p, usr_t.format(n=len(cands), candidates=listed),
                                 json_mode=True, max_tokens=2500, temperature=0.3)
        pick = gate._safe_json(raw) or {}                # 健壮解析:单个flaky PICK绝不杀整本
        try:
            wi = int(pick.get("winner", 1))
        except (ValueError, TypeError):
            wi = 1                                        # 选裁flaky→退化取候选1
        win = cands[max(1, min(len(cands), wi)) - 1]

    gold_status = None
    if is_peak and gold:                          # 大件②：peak 对照金标(95上锚)多轮精修探测
        best, best_score, traj = win, -1, []
        for r in range(refine_rounds):
            pk = await gate.gold_pk(cli, win, gold)
            score = pk.get("score") or 0
            traj.append(score)
            if score > best_score:
                best, best_score, best_gap = win, score, pk.get("gap", "")
            if pk.get("reaches_gold"):
                break
            if len(traj) >= 3 and max(traj[-2:]) <= traj[-3]:   # 连续2轮无提升=平台期，停
                break
            win = await gate.refine_scene(cli, win, gold, pk.get("gap", ""))
        gold_status = {"best_score": best_score, "trajectory": traj,
                       "reached_gold": best_score >= 93, "final_gap": best_gap}
        win = best                                # 保留最高分版本，防回退
    return {"winner": win, "pick": pick, "gold": gold_status}


async def _fit_chapter(cli: Client, text: str, target: int) -> str:
    """双向控字：过长(>115%)精简、过短(<85%)扩写，区间内不动。"""
    r = len(text) / target if target else 1.0
    if r > 1.15:
        sys_p, usr_t = prompts.NORMALIZE
    elif r < 0.85:
        sys_p, usr_t = prompts.EXPAND
    else:
        return text
    out = await cli.complete("draft", sys_p, usr_t.format(target=target, text=text),
                             max_tokens=8000, temperature=0.4)
    out = _strip_markers(out)
    if _META_RE.search(out):          # 出稿污染(扩写点评/思路/示范/markdown泄漏)→弃用,保留原文
        return text
    return out or text


def _load_gold(genre: str) -> str:
    """大件①：按题材加载金标范文（95 上锚）。"""
    g = genre or ""
    name = ("xiuxian" if any(k in g for k in ("修仙", "玄幻", "仙侠"))
            else "guyan" if any(k in g for k in ("古", "宫", "重生", "女强", "穿越", "宅斗"))
            else "")
    if name:
        p = Path("assets/gold") / f"{name}.md"
        if p.exists():
            return "\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines()
                             if not ln.startswith("<!--")).strip()
    return ""


def _truncate(text: str, cap: int) -> str:
    """A3：过长时确定性截断到句子边界（不调 LLM，防 expand/normalize 震荡）。
    兜底升级：句界找不到再退逗号/顿号边界，绝不裸切半词（治"章末断在半句"）。"""
    if len(text) <= cap:
        return text
    cut = text[:cap]
    idx = max(cut.rfind(p) for p in ("。", "！", "？", "”", "\n"))
    if idx <= cap * 0.6:
        idx = max(cut.rfind(p) for p in ("；", "，", "、"))
    return cut[:idx + 1] if idx > cap * 0.6 else cut


def _assemble(plan: dict, ch_texts: list[str]) -> str:
    md = []
    for ci, ch in enumerate(plan["chapters"]):
        md.append(f"# 第{ch['index']}章 {ch.get('title','')}\n")
        md.append(ch_texts[ci])
    return "\n\n".join(md)


async def run(src: Path, n_src: int, n_out: int, n_cand: int, refine_rounds: int = 5) -> dict:
    t0 = time.time()
    out_dir = Path("output") / src.stem
    meta = ingest(src, out_dir / "source")
    clean = (out_dir / "source" / "clean.txt").read_text(encoding="utf-8")
    slice_src = _slice_source(clean, n_src)
    print(f"源 {meta.approx_wan_zi}万字/{meta.chapter_count}章 → 切片前 {n_src} 章({len(slice_src)}字)")

    cli = Client()
    # 1) 提取
    dna = await _extract_dna(cli, slice_src)
    voice = dna.get("voice", "网文白话")
    bible = dna.get("bible", {})
    p = bible.get("protagonist", {})
    print(f"语域: {voice}")
    print(f"圣经: 主角={p.get('name')}({p.get('gender')}) | 设定={bible.get('setting','')[:50]}")
    print(f"抽到 {len(dna['scenes'])} 场景")
    # 2) 规划（schema 已变厚 → 提 max_tokens + 健壮解析防截断崩溃）
    sys_p, usr_p = prompts.PLAN
    scenes = dna["scenes"]

    async def _do_plan(extra: str = "") -> dict:
        raw = await cli.complete("plan", sys_p,
                                 usr_p.format(n_ch=n_out, scenes=json.dumps(scenes, ensure_ascii=False)) + extra,
                                 json_mode=True, max_tokens=16000, temperature=0.5)
        p = gate._safe_json(raw) or {}
        for ch in p.get("chapters", []):
            for sc in ch.get("scenes", []):
                idx = sc.get("source_scene_index")
                if isinstance(idx, int) and 0 <= idx < len(scenes):
                    s = scenes[idx]
                    sc["source_ref"] = f"{s.get('key_excerpt','')} {s.get('summary','')}"
        return p

    plan = await _do_plan()
    # 2.5) 承重确定性审计（shift-left）。**硬**问题(重复/串线/崩坏/翻转)才触发 re-plan；伏笔序过敏感→仅 advisory
    def _hard_issues() -> list[str]:
        ordered_ = [sc for ch in plan.get("chapters", []) for sc in ch.get("scenes", [])]
        d = audit.deterministic_audit(bible, ordered_)
        flat = []
        for k, v in d.items():
            for it in v:
                if "伏笔" not in it:        # 伏笔序不触发昂贵 re-plan
                    flat.append(it)
        return flat
    ordered = [sc for ch in plan.get("chapters", []) for sc in ch.get("scenes", [])]
    tl_issues = _hard_issues()
    if tl_issues:
        print(f"承重硬审计 {len(tl_issues)} 问题 → 重规划: {tl_issues[:3]}")
        plan = await _do_plan(f"\n\n上一版有以下硬伤必须修正(重复事件/重复初遇/阵营串线/战力回退/立场无过渡翻转)：{'；'.join(tl_issues)}")
        ordered = [sc for ch in plan.get("chapters", []) for sc in ch.get("scenes", [])]
        tl_issues = _hard_issues()
    n_scenes = sum(len(ch["scenes"]) for ch in plan["chapters"])
    print(f"规划: {n_out} 章 / {n_scenes} 场景 | 时序残留={len(tl_issues)} → 起草(注入前情账本)+锦标赛+控字+闸门...")

    # 3) 并发处理所有场景（注入圣经；造峰：开篇+钩子/爽点最密的场景给大 N）
    spc = max(1.0, n_scenes / n_out)
    target = int(3500 / spc * 0.92)
    jobs = [(ci, si, sc) for ci, ch in enumerate(plan["chapters"]) for si, sc in enumerate(ch["scenes"])]

    def _richness(sc: dict) -> int:
        idx = sc.get("source_scene_index")
        s = scenes[idx] if isinstance(idx, int) and 0 <= idx < len(scenes) else {}
        return len(s.get("payoffs", [])) + len(s.get("hooks", []))
    rich = [_richness(sc) for _, _, sc in jobs]
    peaks = {0} | set(sorted(range(len(jobs)), key=lambda i: rich[i], reverse=True)[:2])
    gold = _load_gold(voice)                      # 大件①：金标上锚(用 voice 题材标签判，准)
    n_peak = n_cand + 5                            # 大件②：peak 大 N（造峰）
    n_per = [n_peak if i in peaks else n_cand for i in range(len(jobs))]
    print(f"造峰: 场景 {sorted(peaks)} 用 N={n_peak}+金标精修{refine_rounds}轮，其余 N={n_cand} | 金标={'有' if gold else '无'}")
    results = await asyncio.gather(*[
        _process_scene(cli, sc, bible, voice, target, n_per[i], gold=gold,
                       is_peak=(i in peaks), refine_rounds=refine_rounds,
                       context=ledger.format_context(ledger.state_before(ordered, i)))  # 时序前情账本
        for i, (_, _, sc) in enumerate(jobs)])
    gold_reach = [r["gold"] for r in results if r.get("gold")]
    chapters_out: dict[int, list[str]] = {}
    for (ci, si, sc), res in zip(jobs, results):
        chapters_out.setdefault(ci, []).append(res["winner"])
    ch_texts = ["\n\n".join(chapters_out.get(ci, [])) for ci in range(len(plan["chapters"]))]

    # 4) 架构A：canon已冻结+drafts已贴canon → 单次控字 + 单次确定性人名归一 + advisory连续性
    #    （删掉 LLM-repair 迭代环 = whack-a-mole 根源；canon事实靠注入预防、确定性归一兜底；
    #     残留矛盾仅 advisory 标记不再 repair，因 repair 重写引入的漂移多于其修复的）
    ch_texts = await asyncio.gather(*[_fit_chapter(cli, t, 3500) for t in ch_texts])  # 单次双向控字(补短/压长)
    ch_texts = [_truncate(t, int(3500 * 1.15)) for t in ch_texts]                     # 确定性硬截断兜底(防超长)
    # 冻结 canon 的合法名集合（含主角双名 + 显式 aliases + 配角名）→ 双名守卫
    p_b = bible.get("protagonist", {})
    valid_names = set()
    for nm in [p_b.get("name", "")] + (p_b.get("aliases") or []):
        for part in str(nm).replace("、", "/").split("/"):
            if part.strip():
                valid_names.add(part.strip())
    for c in bible.get("characters", []):
        if c.get("name"):
            valid_names.add(c["name"].strip())
    # 单次确定性人名归一（机械 replace，跳过合法名，杜绝 LLM-judge ping-pong）
    final = _assemble(plan, ch_texts)
    cont = await gate.continuity_check(cli, final, bible)
    applied = []
    for f in (cont.get("name_fixes") or []):
        w, r = (f.get("wrong") or "").strip(), (f.get("right") or "").strip()
        if w and r and w != r and w not in valid_names and r in valid_names and len(r) <= 8:
            ch_texts = [t.replace(w, r) for t in ch_texts]
            applied.append(f"{w}→{r}")
    final = _assemble(plan, ch_texts)
    det = [i for t in ch_texts for i in gate.deterministic_checks(t, bible, 3500)]
    advisory = [o for o in (cont.get("other_issues") or []) if o]   # 仅标记，不 repair
    (out_dir / "slice_final.md").write_text(final, encoding="utf-8")
    # 37 维审计：承重(确定性,起草后复检) + 笔力(机械) + 人/故事性(LLM craft, advisory)
    audit_struct = {k: v for k, v in audit.deterministic_audit(bible, ordered).items() if v}
    audit_fore = audit.foreshadow_advisory(ordered)
    audit_mech = audit.mechanical_audit(final)
    audit_craft = await audit.craft_audit(cli, final)
    report = {
        "source": src.name, "wan_zi": meta.approx_wan_zi, "out_chapters": n_out,
        "scenes": n_scenes, "candidates_per_scene": n_cand,
        "final_chars": len(final), "avg_chapter_chars": len(final) // n_out,
        "structural": gate.structural_lite(plan, dna),
        "peaks_reached_gold": f"{sum(1 for g in gold_reach if g.get('reached_gold'))}/{len(gold_reach)}",
        "peak_best_scores": [g.get("best_score") for g in gold_reach],
        "mechanical": det or ["无"],
        "name_fixes_applied": applied or ["无"],
        "audit_承重_确定性硬检": audit_struct or {"全过": "✓"},
        "audit_维7伏笔序(advisory)": audit_fore or ["无"],
        "audit_笔力_机械": audit_mech or {"全过": "✓"},
        "audit_人+故事性_craft(advisory)": audit_craft or ["无"],
        "advisory_issues": advisory or ["无"],
        "final_consistent": not advisory and not [d for d in det if "长" not in d],
        "calls": cli.calls, "cost_cny": round(cli.cost_cny, 2), "seconds": round(time.time() - t0, 1),
    }
    (out_dir / "slice_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--src-chapters", type=int, default=12)
    ap.add_argument("--out-chapters", type=int, default=3)
    ap.add_argument("-n", "--candidates", type=int, default=3)
    ap.add_argument("--refine-rounds", type=int, default=5)
    a = ap.parse_args()
    rep = asyncio.run(run(Path(a.src), a.src_chapters, a.out_chapters, a.candidates, a.refine_rounds))
    print("\n=== 切片报告 ===")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"\n成品 → output/{Path(a.src).stem}/slice_final.md（请人工评判）")


if __name__ == "__main__":
    main()
