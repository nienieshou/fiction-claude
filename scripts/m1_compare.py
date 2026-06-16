"""M1 A/B 漂移对照: Spine版 vs 非Spine版,各跑 extract_facts+cross_check,按类计数。"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki import prose_facts as pf

ARMS = [
    ("非Spine(基线)", "output/ZTGXY01837退婚后，她被财阀大佬娇养了_full_bestof3"),
    ("Spine仅名(M1)", "output/ZTGXY01837退婚_spine"),
    ("Spine+数值(M1.5②)", "output/ZTGXY01837退婚_spine_v2"),
]


def _counts(findings):
    by = {}
    for f in findings:
        by.setdefault(f["cat"], []).append(f)
    return {k: len(v) for k, v in by.items()}, by


async def one(cli, label, d):
    chs = pf.split_chapters((Path(d) / "final.md").read_text(encoding="utf-8"))
    facts = await pf.extract_facts(cli, chs)
    findings = pf.cross_check(facts)
    raw_counts, _ = _counts(findings)
    await pf.verify_identity(cli, findings, chs)            # M1.5 ①: 身份真矛盾门
    real = [f for f in findings if f.get("real")]
    real_counts, real_by = _counts(real)
    dropped = [f for f in findings if f.get("cat") == "身份" and not f.get("real")]
    return {"label": label, "n_chapters": len(chs),
            "raw_total": len(findings), "raw_counts": raw_counts,
            "real_total": len(real), "real_counts": real_counts,
            "real_by": {k: [f"{f.get('who')}: {f.get('why','')[:70]}" for f in v]
                        for k, v in real_by.items()},
            "dropped_id": [f"{f.get('who')}: {f.get('va')}|{f.get('vb')} ← {f.get('reason','')}"
                           for f in dropped]}


async def main():
    cli = Client()
    rows = [await one(cli, lb, d) for lb, d in ARMS]
    print("\n===== M1.5 A/B 承重漂移对照 (cross_check + 身份真矛盾门) =====")
    for r in rows:
        print(f"\n--- {r['label']} ({r['n_chapters']}章) ---")
        print(f"  raw(未过门)={r['raw_total']} {r['raw_counts']}  →  真矛盾={r['real_total']} {r['real_counts']}")
        for cat, items in r["real_by"].items():
            for it in items:
                print(f"    ✓真[{cat}] {it}")
        print(f"  (身份门滤除 {len(r['dropped_id'])} 条噪声,样例:)")
        for it in r["dropped_id"][:6]:
            print(f"    ✗滤[身份] {it}")
    print("\n>>> 真矛盾总览(身份/数值):")
    for r in rows:
        print(f"    {r['label']:18} 真矛盾={r['real_total']:2}  "
              f"身份={r['real_counts'].get('身份',0)} 数值={r['real_counts'].get('数值',0)}")
    num = {r['label']: r['real_counts'].get('数值', 0) for r in rows}
    base_n, spine_n, v2_n = list(num.values())
    print(f"\n>>> ② 隔离判据(数值真矛盾): Spine仅名={spine_n} → Spine+数值={v2_n}  "
          f"基线={base_n}  ({'② 有效降数值漂移' if v2_n < spine_n else '② 未降数值漂移'})")
    print(f"总成本 ¥{cli.cost_cny:.2f}")
    Path("output/m1_compare.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
