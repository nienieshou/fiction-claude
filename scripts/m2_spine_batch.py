"""M2: 线性甜区5本 · Spine 全套(名+数值+身份+里程碑) 单跑 n=3。
对照=已在盘的 baseline `<stem>_full_bestof3`(best-of-3,Opus承重 31/48/58/38/31)。
HIKI_SPINE=1 在进程内置(run 读 env)。串行(避 pro 限流),每本内部已并发。
用法: PYTHONPATH=src python scripts/m2_spine_batch.py
"""
import os
os.environ["HIKI_SPINE"] = "1"                       # 必须在 import/run 读 env 前置
import asyncio, json, sys, time
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.produce import run

SRC = Path("fictions_source")
BOOKS = [
    "现代言情/误嫁豪门，战神老公蓄意偏宠.txt",
    "现代言情/怀孕命剩三月，傅爷说要回家过夜.txt",
    "古代言情/傲世狂妃太逆天.txt",
    "年代纪实/1960六零饥荒年：我靠团购娇养冷面知青.txt",
    "现代言情/退婚后，她被财阀大佬娇养了.txt",
]


async def main():
    t0 = time.time()
    rows = []
    for b in BOOKS:
        src = SRC / b
        out = Path("output") / f"{src.stem}_spine_m2"
        bt = time.time()
        try:
            rep = await run(src, n_cand=3, out_dir=out)
            rows.append({"book": src.stem, "issues": rep.get("交付门"),
                         "cost": rep.get("cost_cny"), "dir": str(out),
                         "secs": round(time.time() - bt)})
        except Exception as e:
            rows.append({"book": src.stem, "error": f"{type(e).__name__}:{e}",
                         "secs": round(time.time() - bt)})
        print(f"[done {len(rows)}/5] {src.stem}  {rows[-1].get('issues') or rows[-1].get('error')}")
        Path("output/m2_spine_batch.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== M2 batch done, wall={time.time() - t0:.0f}s, "
          f"总¥{sum(r.get('cost', 0) or 0 for r in rows):.2f} ===")
    for r in rows:
        print(r)


if __name__ == "__main__":
    asyncio.run(main())
