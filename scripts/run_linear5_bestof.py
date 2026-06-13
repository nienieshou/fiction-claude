"""线性甜区5本 · best-of-3 量产(2026-06-13)
配方=泛化轮已验配方:每源跑K=3次,选 ship_issues 最少本(killer类加权),落 <源>_full_bestof3/。
本与本之间串行(避免15并发爆账号pro上限),每源内部K=3并发。
出 output/batch_summary_linear5.{json,md}。
用法: PYTHONPATH=src python scripts/run_linear5_bestof.py
"""
import asyncio, json, sys, shutil, time
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.produce import run

K, NCAND = 3, 3
SRC_DIR = Path("fictions_source")
BOOKS = [
    "ZTGXY01825误嫁豪门，战神老公蓄意偏宠.txt",       # 现言军婚甜宠
    "ZYGXY01893怀孕命剩三月，傅爷说要回家过夜.txt",     # 虐恋追妻火葬场
    "ZYGGY03052傲世狂妃太逆天.txt",                     # 女强宫斗
    "ZYGXN01960六零饥荒年：我靠团购娇养冷面知青.txt",   # 年代种田
    "ZTGXY01837退婚后，她被财阀大佬娇养了.txt",         # 豪门先婚后爱
]


def _issue_score(iss):
    if iss == ["通过"]:
        return 0
    killer = sum(2 for x in iss if any(k in str(x) for k in ("复活", "双版本", "暗黑饱和", "跳过")))
    return len(iss) + killer


async def best_of_one(src: Path) -> dict:
    dirs = [Path("output") / f"{src.stem}_bok{i}" for i in range(K)]
    reps = await asyncio.gather(*[run(src, n_cand=NCAND, out_dir=d) for d in dirs],
                                return_exceptions=True)
    rows = []
    for i, rep in enumerate(reps):
        if isinstance(rep, Exception):
            rows.append((i, 9999, [f"崩:{type(rep).__name__}"], 0.0, None))
        else:
            iss = rep.get("交付门", ["?"])
            rows.append((i, _issue_score(iss), iss, rep.get("cost_cny", 0.0), rep))
    rows.sort(key=lambda x: x[1])
    best = rows[0]
    total = round(sum(r[3] for r in rows), 2)
    final = Path("output") / f"{src.stem}_full_bestof3"
    rep = best[4]
    if rep is not None:
        if final.exists():
            shutil.rmtree(final)
        shutil.copytree(dirs[best[0]], final)
        json.dump([{"bok": i, "硬伤分": sc, "门": iss, "cost": c}
                   for i, sc, iss, c, _ in rows],
                  open(final / "best_of_summary.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    print(f"  best=bok{best[0]} 硬伤分{best[1]} {best[2]} | 总¥{total}")
    return {
        "src": src.name, "best_bok": best[0], "best_score": best[1],
        "ship_issues": best[2], "deliverable": rep.get("deliverable") if rep else None,
        "rejected": rep.get("rejected") if rep else None,
        "grade": (rep.get("grade") or {}).get("grade") if rep else None,
        "暗黑比": rep.get("暗黑比") if rep else None,
        "out_chapters": rep.get("out_chapters") if rep else None,
        "final_chars": rep.get("final_chars") if rep else None,
        "output_file": (f"{src.stem}_full_bestof3/" + (rep.get("output_file", "") if rep else "")),
        "k_cost": total, "all_scores": [(i, sc) for i, sc, *_ in rows],
    }


async def main():
    t0 = time.time()
    results = []
    for n, b in enumerate(BOOKS, 1):
        src = SRC_DIR / b
        print(f"\n[{n}/{len(BOOKS)}] best-of-{K}: {b[:24]} ...")
        try:
            results.append(await best_of_one(src))
        except Exception as e:
            results.append({"src": b, "error": f"{type(e).__name__}: {e}"})
            print(f"  ⚠ 整本崩: {e}")
    wall = round(time.time() - t0, 1)
    cost = round(sum(r.get("k_cost", 0) or 0 for r in results), 2)
    deliv = [r for r in results if r.get("deliverable")]
    summary = {"批": "线性甜区5本 best-of-3", "本数": len(BOOKS),
               "裸过门_可交付": len(deliv), "总成本_cny": cost, "墙钟_秒": wall,
               "results": results}
    out = Path("output")
    (out / "batch_summary_linear5.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 线性甜区5本 · best-of-3 量产  墙钟{wall}s  总¥{cost}",
             f"裸过门(可交付) {len(deliv)}/{len(BOOKS)}", "",
             "| 源 | grade | 选中bok | best硬伤分 | 裸过 | 暗黑 | 章 | 字 | ship_issues | K成本¥ |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['src'][:24]} | **崩** | | | | | | | {r['error'][:30]} | |")
            continue
        bare = "✓" if r.get("deliverable") else ("Q拒收" if r.get("rejected") else "✗")
        iss = "；".join(r.get("ship_issues") or [])[:36]
        lines.append(f"| {r['src'][:24]} | {r.get('grade')} | bok{r.get('best_bok')} | "
                     f"{r.get('best_score')} | {bare} | {r.get('暗黑比')} | {r.get('out_chapters')} | "
                     f"{r.get('final_chars')} | {iss} | {r.get('k_cost')} |")
    (out / "batch_summary_linear5.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== 线性甜区5本完成 ===\n裸过门 {len(deliv)}/{len(BOOKS)} | 总¥{cost} | 墙钟{wall}s")
    print("明细 → output/batch_summary_linear5.md")


if __name__ == "__main__":
    asyncio.run(main())
