"""R11-0: 邻章版本互斥检测器召回测试。
真值=团宠r9版评审坐实的邻章重演对(渡劫ch57→58重演/飞升ch59→60两版)+R10版点修前
评审坐实但已修的对不可用 → 以 r9 为主,负对照=星际厨神(已点修干净)全部相邻对。
判据: 真值对≥2/3命中 且 对照误报≤10% → 接线;否则弃(R8'章级查重零检出'前科)。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki import prompts, gate
from hiki.client import Client
from hiki.prose_facts import split_chapters

R9 = Path("output/ZYGGY03733团宠小师妹靠摆烂带飞全宗门_full_r9/final.md")
CLEAN = Path("output/ZYGWJ02935大佬她美飒全星际_full/final.md")
TRUTH_PAIRS = [(57, 58), (59, 60)]   # (前章,后章) 1-based: 渡劫重演 / 飞升两版


async def check_pair(cli, prev_t, head_t):
    sys_c, usr_c = prompts.ADJ_DUP_CHECK
    for t in range(3):
        raw = await cli.complete("chunk_extract", sys_c,
                                 usr_c.format(prev=prev_t[-1500:], head=head_t[:1500]),
                                 json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
        r = gate._safe_json(raw) or {}
        if isinstance(r, dict) and "dup" in r:
            return r
    return {}


async def scan(cli, chs):
    res = await asyncio.gather(*[check_pair(cli, chs[i - 1], chs[i]) for i in range(1, len(chs))])
    return {i + 1: r for i, r in enumerate(res, start=1) if r.get("dup") is True}
    # 键=后章号(1-based)


async def main():
    cli = Client()
    chs9 = split_chapters(R9.read_text(encoding="utf-8"))
    hits9 = await scan(cli, chs9)
    hit_pairs = [(a, b) for a, b in TRUTH_PAIRS if b in hits9]
    print(f"团宠r9: 检出{len(hits9)}对: {[(k, v.get('issue', '')[:20]) for k, v in sorted(hits9.items())]}")
    print(f"真值命中 {len(hit_pairs)}/{len(TRUTH_PAIRS)}: {hit_pairs}")
    chsC = split_chapters(CLEAN.read_text(encoding="utf-8"))
    hitsC = await scan(cli, chsC)
    fp = len(hitsC) / max(1, len(chsC) - 1)
    print(f"星际(净书对照): 误报{len(hitsC)}/{len(chsC) - 1}={fp:.0%}: "
          f"{[(k, v.get('issue', '')[:20]) for k, v in sorted(hitsC.items())][:5]}")
    ok = len(hit_pairs) >= 2 and fp <= 0.10
    print(f"\n判定: {'✅接线' if ok else '⛔不接(召回不足或误报超限)'} | ¥{cli.cost_cny:.2f}")


asyncio.run(main())
