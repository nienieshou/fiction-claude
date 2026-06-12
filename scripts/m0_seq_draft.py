"""B路线 M0: 同一plan下 顺序整本上下文起草 vs 并行分章起草 对照差分。
切换判据(三条同时成立才换起草层): 顺序矛盾数≤并行50% / 尾部章质量不塌 / 成本≤2×。
两臂同设置(n=3/无金标/无peak),跳过全部修复pass(修复会掩盖架构差异),只 fit+truncate+组装。
锚源=团宠(同源 r3/r6/round6 三版历史分可比)。规划只做一次(plan_artifacts.json 断点续跑)。"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki import mining, audit, ledger, prompts
from hiki.client import Client
from hiki.ingest import ingest
from hiki.produce import _plan_macro, _plan_one_chapter, _handoff
from hiki.slice_validate import _process_scene, _fit_chapter, _truncate, _assemble
from hiki.prose_facts import fact_audit

SRC = Path("fictions_source/ZYGGY03733团宠小师妹靠摆烂带飞全宗门.txt")
OUT = Path("output/_m0_seq")
OUT.mkdir(parents=True, exist_ok=True)
N_CH, N_CAND = 60, 3


async def plan_once(cli):
    pf = OUT / "plan_artifacts.json"
    if pf.exists():                                   # 断点续跑: 规划只做一次
        a = json.loads(pf.read_text(encoding="utf-8"))
        return a["bible"], a["plan"], a["scenes"]
    ingest(SRC, OUT / "source")
    clean = (OUT / "source" / "clean.txt").read_text(encoding="utf-8")
    mined = await mining.mine_book(cli, clean, 13, int(N_CH * 1.4))
    bible, scenes = mined["bible"], mined["scenes"]
    macro = await _plan_macro(cli, bible, scenes, N_CH)
    beats = macro.get("chapters", [])[:N_CH]
    p = bible.get("protagonist", {})
    bb = json.dumps({"protagonist": {k: p.get(k) for k in ("name", "gender", "goal", "arc")},
                     "characters": [{"name": c.get("name"), "goal": c.get("goal")}
                                    for c in bible.get("characters", [])[:8]],
                     "setting": bible.get("setting")}, ensure_ascii=False)[:3000]

    def _bb(b):
        return (b.get("beat") or "")[:60] or "（无）"
    chs = await asyncio.gather(*[
        _plan_one_chapter(cli, b, scenes, bb,
                          prev_beat=_bb(beats[j - 1]) if j else "（本章是开篇）",
                          next_beat=_bb(beats[j + 1]) if j < len(beats) - 1 else "（本章是全书结局）")
        for j, b in enumerate(beats)])
    plan = {"chapters": [c for c in chs if c.get("scenes")]}
    ordered = [sc for ch in plan["chapters"] for sc in ch["scenes"]]
    ledger.dedup_first_meetings(ordered)
    audit.fix_entourage(bible, ordered)
    audit.fix_power_monotonic(bible, ordered)
    pf.write_text(json.dumps({"bible": bible, "plan": plan, "scenes": scenes},
                             ensure_ascii=False), encoding="utf-8")
    return bible, plan, scenes


def _target(plan):
    n_sc = sum(len(c["scenes"]) for c in plan["chapters"])
    return int(3500 / max(1.0, n_sc / max(1, len(plan["chapters"]))) * 0.92)


async def arm_parallel(cli, bible, plan):
    voice = bible.get("voice", "网文白话")
    ordered = [sc for ch in plan["chapters"] for sc in ch["scenes"]]
    target = _target(plan)
    jobs = [(ci, si, sc) for ci, ch in enumerate(plan["chapters"]) for si, sc in enumerate(ch["scenes"])]
    res = await asyncio.gather(*[
        _process_scene(cli, sc, bible, voice, target, N_CAND,
                       context=ledger.format_context(ledger.state_before(ordered, i)) + _handoff(jobs, plan, i))
        for i, (_, _, sc) in enumerate(jobs)])
    out: dict[int, list[str]] = {}
    for (ci, _, _), r in zip(jobs, res):
        out.setdefault(ci, []).append(r["winner"])
    return ["\n\n".join(out.get(ci, [])) for ci in range(len(plan["chapters"]))]


async def arm_sequential(cli, bible, plan):
    voice = bible.get("voice", "网文白话")
    target = _target(plan)
    prev: list[str] = []
    for ch in plan["chapters"]:
        parts: list[str] = []
        for sc in ch["scenes"]:
            hist = "\n\n".join(f"# 第{i + 1}章\n{t}" for i, t in enumerate(prev)) or "（本书尚未开始）"
            if parts:
                hist += "\n\n# 本章已写部分\n" + "\n\n".join(parts)
            # history 含正文花括号会炸 .format → 先转义再替换占位
            tmpl = (prompts.DRAFT_SEQ[0],
                    prompts.DRAFT_SEQ[1].replace("{history}", hist.replace("{", "{{").replace("}", "}}")))
            r = await _process_scene(cli, sc, bible, voice, target, N_CAND,
                                     context="(前文见最上方已成章正文)", tmpl=tmpl)
            parts.append(r["winner"])
        prev.append("\n\n".join(parts))
        if len(prev) % 10 == 0:
            print(f"  顺序臂: {len(prev)}/{len(plan['chapters'])} 章", flush=True)
    return prev


async def finish(cli, chs):
    chs = await asyncio.gather(*[_fit_chapter(cli, t, 3500) for t in chs])
    return [_truncate(t, int(3500 * 1.15)) for t in chs]


def _cliche_count(txt: str) -> int:
    hits = audit.cliche_hits(txt) or {}
    n = 0
    for v in hits.values():
        n += sum(v.values()) if isinstance(v, dict) else (len(v) if isinstance(v, (list, set)) else int(v))
    return n


def tail_quality(chs):
    def block(idx):
        idx = list(idx)
        txt = "\n".join(chs[i] for i in idx)
        return {"套话": _cliche_count(txt),
                "均字": sum(len(chs[i]) for i in idx) // len(idx),
                "过短章": sum(1 for i in idx if len(chs[i]) < 3500 * 0.7)}
    return {"前10章": block(range(10)), "后10章": block(range(len(chs) - 10, len(chs)))}


async def main():
    cli = Client()
    bible, plan, _ = await plan_once(cli)
    print(f"规划就绪 {len(plan['chapters'])}章 ¥{cli.cost_cny:.2f}", flush=True)
    rep_path = OUT / "m0_report.json"
    rep = json.loads(rep_path.read_text(encoding="utf-8")) if rep_path.exists() else {}
    for name, arm in (("parallel", arm_parallel), ("sequential", arm_sequential)):
        if name in rep:                               # 断点续跑: 已完成的臂跳过
            print(f"{name} 已有结果,跳过", flush=True)
            continue
        c2 = Client()
        t0 = time.time()
        chs = await finish(c2, await arm(c2, bible, plan))
        (OUT / f"final_{name}.md").write_text(_assemble(plan, chs), encoding="utf-8")
        fa = await fact_audit(c2, chs)
        (OUT / f"fact_{name}.json").write_text(json.dumps(fa, ensure_ascii=False, indent=2), encoding="utf-8")
        rep[name] = {"矛盾总数": len(fa["findings"]), "矛盾验真": fa["n_verified"],
                     "by_cat": {c: sum(1 for f in fa["findings"] if f["cat"] == c and f["verified"])
                                for c in ("生死", "体系", "时间轴", "身份", "数值")},
                     "尾部质量": tail_quality(chs), "墙钟s": round(time.time() - t0, 1),
                     "成本¥": round(c2.cost_cny, 2)}
        rep_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(name, json.dumps(rep[name], ensure_ascii=False), flush=True)
    p, s = rep["parallel"], rep["sequential"]
    ok1 = s["矛盾验真"] <= p["矛盾验真"] * 0.5
    ok2 = (s["尾部质量"]["后10章"]["过短章"] <= 1
           and s["尾部质量"]["后10章"]["套话"] <= p["尾部质量"]["后10章"]["套话"] * 1.3)
    ok3 = s["成本¥"] <= p["成本¥"] * 2
    print(f"\n切换判据: 矛盾减半={ok1} 尾部不塌={ok2} 成本≤2×={ok3} → "
          f"{'换起草层' if ok1 and ok2 and ok3 else '留路线A'}")


asyncio.run(main())
