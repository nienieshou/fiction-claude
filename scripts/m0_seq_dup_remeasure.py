"""R12 补测: M0 顺序/并行双臂的**版本互斥密度**(当时只测了章缝19→15,量错指标——
版本互斥才是承重真主类)。用 ADJ_DUP_CHECK 逐对扫两臂,差分决定 R13 是否翻案起草层结论。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki import prompts, gate
from hiki.client import Client
from hiki.prose_facts import split_chapters

OUT = Path("output/_m0_seq")


async def check_pair(cli, prev_t, head_t):
    sys_c, usr_c = prompts.ADJ_DUP_CHECK
    for t in range(3):
        raw = await cli.complete("chunk_extract", sys_c,
                                 usr_c.format(prev=prev_t[-1800:], head=head_t[:2200]),
                                 json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
        r = gate._safe_json(raw) or {}
        if isinstance(r, dict) and "dup" in r:
            return r
    return {}


async def main():
    cli = Client()
    res = {}
    for name in ("parallel", "sequential"):
        chs = split_chapters((OUT / f"final_{name}.md").read_text(encoding="utf-8"))
        checks = await asyncio.gather(*[check_pair(cli, chs[i - 1], chs[i])
                                        for i in range(1, len(chs))])
        hits = [(i + 1, r.get("issue", "")[:24]) for i, r in enumerate(checks, start=1)
                if r.get("dup") is True]
        res[name] = hits
        print(f"{name}: 邻章互斥 {len(hits)}/{len(chs) - 1} 对: {hits[:8]}")
    p, s = len(res["parallel"]), len(res["sequential"])
    print(f"\n差分: 并行{p} vs 顺序{s} → "
          f"{'顺序臂显著更低,起草层结论需翻案(R13)' if s <= p * 0.5 and p >= 4 else '无显著差异,维持现结论'}"
          f" | ¥{cli.cost_cny:.2f}")


asyncio.run(main())
