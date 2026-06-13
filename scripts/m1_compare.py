"""M1 A/B 漂移对照: Spine版 vs 非Spine版,各跑 extract_facts+cross_check,按类计数。"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki import prose_facts as pf

ARMS = [
    ("非Spine(基线)", "output/ZTGXY01837退婚后，她被财阀大佬娇养了_full_bestof3"),
    ("Spine(M1)", "output/ZTGXY01837退婚_spine"),
]


async def one(cli, label, d):
    chs = pf.split_chapters((Path(d) / "final.md").read_text(encoding="utf-8"))
    facts = await pf.extract_facts(cli, chs)
    findings = pf.cross_check(facts)
    by = {}
    for f in findings:
        by.setdefault(f["cat"], []).append(f"{f.get('who')}: {f.get('why','')[:70]}")
    return {"label": label, "n_chapters": len(chs), "by_cat": by,
            "counts": {k: len(v) for k, v in by.items()}, "total": len(findings)}


async def main():
    cli = Client()
    rows = [await one(cli, lb, d) for lb, d in ARMS]
    print("\n===== M1 A/B 漂移对照 (cross_check) =====")
    for r in rows:
        print(f"\n--- {r['label']} ({r['n_chapters']}章) 总漂移={r['total']} 分类={r['counts']} ---")
        for cat, items in r["by_cat"].items():
            for it in items:
                print(f"  [{cat}] {it}")
    print(f"\n总成本 ¥{cli.cost_cny:.2f}")
    Path("output/m1_compare.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
