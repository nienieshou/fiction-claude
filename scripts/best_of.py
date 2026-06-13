"""M3 best-of-K(stable-75路线核心): 同源并行跑K次,选交付门 ship_issues 最少的本。
确定性整本选择(用已可靠的交付门硬伤计数,绕开'整本质量判别器'难题)——
既买稳定性(挑±5方差的好一侧),也让 M1/M2 小增量攒进整体可测。
用法: python scripts/best_of.py <源.txt> [K=3]
"""
import asyncio, json, sys, shutil
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.produce import run

SRC = Path(sys.argv[1])
K = int(sys.argv[2]) if len(sys.argv) > 2 else 3
NCAND = int(sys.argv[3]) if len(sys.argv) > 3 else 3   # M6: 大N全场景选优(N=12吃模型尾部抬生成侧)


def _issue_score(iss):
    """ship_issues 越少越好;通过=0。平手时killer类(死人复活/双版本)更重。"""
    if iss == ["通过"]:
        return 0
    killer = sum(2 for x in iss if any(k in str(x) for k in ("复活", "双版本", "暗黑饱和", "跳过")))
    return len(iss) + killer


async def main():
    dirs = [Path("output") / f"{SRC.stem}_bok{i}" for i in range(K)]
    reps = await asyncio.gather(*[run(SRC, n_cand=NCAND, out_dir=d) for d in dirs],
                                return_exceptions=True)
    rows = []
    for i, (d, rep) in enumerate(zip(dirs, reps)):
        if isinstance(rep, Exception):
            rows.append((i, 9999, [f"崩:{type(rep).__name__}"], 0.0, None))
            continue
        iss = rep.get("交付门", ["?"])
        rows.append((i, _issue_score(iss), iss, rep.get("cost_cny", 0.0), rep))
    rows.sort(key=lambda x: x[1])
    best = rows[0]
    final = Path("output") / f"{SRC.stem}_full_bestof{K}"
    if final.exists():
        shutil.rmtree(final)
    shutil.copytree(dirs[best[0]], final)
    total = sum(r[3] for r in rows)
    print(f"=== best-of-{K}: {SRC.stem[:16]} ===")
    for i, sc, iss, c, _ in rows:
        mark = " ← 选中" if i == best[0] else ""
        print(f"  bok{i}: 硬伤分={sc} {iss} ¥{c}{mark}")
    print(f"→ 选 bok{best[0]}(硬伤分{best[1]}) → {final.name} | 总成本 ¥{total:.2f}")
    json.dump([{"bok": i, "硬伤分": sc, "门": iss, "cost": c} for i, sc, iss, c, _ in rows],
              open(final / "best_of_summary.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"  → 最终本: {final}/final.md (请 Fable 评判 best-of-{K} 的稳定性增量)")


if __name__ == "__main__":
    asyncio.run(main())
