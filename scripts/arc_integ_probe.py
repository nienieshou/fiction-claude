"""集成探针:在真书源上跑 mine 的 MAP+生死弧聚合,核对 v3 真值。零起草。
真值(独立grep/v3全读坐实):桑念=dies_returns、袁麟/卢炳元=dies_final。"""
import asyncio, glob, json, os, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
os.environ["HIKI_SPINE"] = "1"
from hiki.client import Client
from hiki import mining, audit

CASES = [("output/ZTGGX02751听说我死后成了反派白月光_20260617_full", {"桑念": "dies_returns"}),
         ("output/_rerun_ZYGGX02148", {"袁麟": "dies_final", "卢炳元": "dies_final"})]
N_CHUNKS = 12

async def main():
    cli = Client()
    for book, gt in CASES:
        srcs = glob.glob(book + "/source/*.txt")
        if not srcs:
            print(f"!! 缺源: {book}"); continue
        clean = Path(srcs[0]).read_text(encoding="utf-8", errors="ignore")
        chunks = mining.chunk_by_chapters(clean, n_chunks=N_CHUNKS)
        results = await mining.map_extract(cli, chunks)
        arcs = mining.collect_life_events(results)
        print(f"\n== {os.path.basename(book)[:20]} | 抽到 {len(arcs)} 条生死弧 ==")
        for who, want in gt.items():
            got = arcs.get(who, {}).get("fate", "(无弧)")
            verdict = audit.reconcile_revival(arcs, who)
            ok = "OK" if got == want else "MISS"
            print(f"   {who}: 弧={got} 真值={want} [{ok}] | 门判定={verdict}")
    print(f"\n¥{cli.cost_cny:.2f} | {cli.calls} calls")

asyncio.run(main())
