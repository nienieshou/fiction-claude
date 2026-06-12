"""B路线 M0 事后差分测量(与生成解耦)。
背景: fact_audit 召回仅~18%(docs/plans/recall_result.md),不堪当主尺。
主指标改用生产中已验证的检测器: SEAM_CHECK 章缝检出数(顺序起草该治的头号类) + POV离群数(确定性)。
fact_audit 验真数降为辅助参考。用法: python scripts/m0_measure.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki import prompts, gate
from hiki.client import Client
from hiki.produce import _pov_outliers
from hiki.prose_facts import split_chapters

OUT = Path("output/_m0_seq")


async def seam_detect(cli: Client, ch_texts: list[str]) -> list[str]:
    """复刻 produce._seam_pass 的 detect 部分(不修复): 59对 尾→头 并发判衔接断裂。"""
    sys_c, usr_c = prompts.SEAM_CHECK

    async def _check(i: int) -> dict:
        for t in range(3):                       # retry-on-empty
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-700:], head=ch_texts[i][:900]),
                                     json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if "ok" in r:
                return r
        return {}
    idxs = list(range(1, len(ch_texts)))
    checks = await asyncio.gather(*[_check(i) for i in idxs])
    return [f"第{i + 1}章:{(r.get('issue') or '断裂').strip()[:24]}"
            for i, r in zip(idxs, checks) if r.get("ok") is False]


async def main():
    cli = Client()
    out = {}
    for name in ("parallel", "sequential"):
        f = OUT / f"final_{name}.md"
        if not f.exists():
            print(f"{name}: final 缺失,跳过")
            continue
        chs = split_chapters(f.read_text(encoding="utf-8"))
        seams = await seam_detect(cli, chs)
        person, pov_out = _pov_outliers(chs)
        fa = {}
        fj = OUT / f"fact_{name}.json"
        if fj.exists():
            fa = json.loads(fj.read_text(encoding="utf-8"))
        out[name] = {"章缝检出": len(seams), "章缝明细": seams,
                     "POV离群章": len(pov_out), "fact验真(辅助)": fa.get("n_verified"),
                     "章数": len(chs)}
        print(f"{name}: 章缝={len(seams)} POV离群={len(pov_out)} "
              f"fact验真={fa.get('n_verified')} 章数={len(chs)}")
    (OUT / "m0_measure.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    if "parallel" in out and "sequential" in out:
        p, s = out["parallel"], out["sequential"]
        ok = s["章缝检出"] <= p["章缝检出"] * 0.5
        print(f"\n主判据(章缝减半): 并行{p['章缝检出']} vs 顺序{s['章缝检出']} → {'成立' if ok else '不成立'}")
    print(f"测量成本 ¥{cli.cost_cny:.2f}")


asyncio.run(main())
