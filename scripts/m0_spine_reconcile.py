"""M0 · 事实脊柱归并裁决可行性(2026-06-13,设计见 docs/design/fact_spine.md §7)
在 5 本已知承重缺陷的成品上跑 registry 空间归并裁决,验证能否消解已知病例:
- 同人多名 → cluster_names(detect→verify→merge,复用,带源在场守卫防误并)
- 同名多身份/数值/生死 → prose_facts.extract_facts + cross_check(复用,逐章抽→代码跨章对比)
判据(spec §7 M0): 已知缺陷类正确消解 ≥70% 且不引入错并。不生产、不改正文。
用法: PYTHONPATH=src python scripts/m0_spine_reconcile.py
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki import prose_continuity as pc
from hiki import prose_facts as pf

BOOKS = [
    ("误嫁豪门", "ZTGXY01825误嫁豪门，战神老公蓄意偏宠_full_bestof3",
     "已知:顾巍军衔 营级/团长/中校/少将多值; 绑架ch24/25双版本"),
    ("怀孕命剩三月", "ZYGXY01893怀孕命剩三月，傅爷说要回家过夜_full_bestof3",
     "已知:生父 徐正鸿/正清/山川/景德 四名"),
    ("傲世狂妃", "ZYGGY03052傲世狂妃太逆天_full_bestof3",
     "已知:母亲 肖澄仪/玄仙诗/沧玄长公主; 宋时奕 武王族弟/九皇子/太子"),
    ("六零团购", "ZYGXN01960六零饥荒年：我靠团购娇养冷面知青_full_bestof3",
     "已知:外公 沈元白/庄文泉/宋博翰; 婚龄 五/十/三年"),
    ("退婚财阀", "ZTGXY01837退婚后，她被财阀大佬娇养了_full_bestof3",
     "已知:顾明乾 养父/二哥/弟; 走失 20/26/17/23年; 顾明骁/顾明景"),
]


async def one(cli: Client, name: str, d: Path, known: str) -> dict:
    final = (d / "final.md").read_text(encoding="utf-8")
    chs = pf.split_chapters(final)
    full = "\n".join(chs)
    src_clean = ""
    sp = d / "source" / "clean.txt"
    if sp.exists():
        src_clean = sp.read_text(encoding="utf-8")

    # ① 同人多名归并(cluster_names: detect→verify→merge,源在场守卫)
    roster = await pc.extract_roster(cli, chs)
    fix_map = await pc.cluster_names(cli, roster["persons"], full, chs, source_text=src_clean)

    # ② 同名多身份 / 数值 / 生死(extract_facts→cross_check)
    facts = await pf.extract_facts(cli, chs)
    findings = pf.cross_check(facts)
    by_cat: dict[str, list] = {}
    for f in findings:
        by_cat.setdefault(f["cat"], []).append(
            f"{f.get('who')}: 第{f.get('ch_a')}「{f.get('why','')[:60]}」")

    return {
        "book": name, "known": known, "n_persons": len(roster["persons"]),
        "同人多名_归并": fix_map or {},
        "同名多身份(身份)": by_cat.get("身份", []),
        "数值矛盾": by_cat.get("数值", []),
        "生死矛盾": by_cat.get("生死", []),
        "cost_cny": round(cli.cost_cny, 2),
    }


async def main():
    cli = Client()
    rows = []
    for name, sub, known in BOOKS:
        d = Path("output") / sub
        print(f"\n=== {name} ===  ({known})")
        try:
            r = await one(cli, name, d, known)
            rows.append(r)
            print(f"  人物数={r['n_persons']}")
            print(f"  ① 同人多名归并: {r['同人多名_归并'] or '（无归并）'}")
            print(f"  ② 同名多身份: {r['同名多身份(身份)'] or '（无）'}")
            print(f"  ③ 数值矛盾: {r['数值矛盾'] or '（无）'}")
            print(f"  ④ 生死矛盾: {r['生死矛盾'] or '（无）'}")
        except Exception as e:
            rows.append({"book": name, "error": f"{type(e).__name__}: {e}"})
            print(f"  ⚠ 崩: {e}")
    out = {"M0": "事实脊柱归并裁决可行性", "本数": len(BOOKS),
           "总成本_cny": round(cli.cost_cny, 2), "rows": rows}
    Path("output/m0_spine_reconcile.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n总成本 ¥{cli.cost_cny:.2f} → output/m0_spine_reconcile.json")


if __name__ == "__main__":
    asyncio.run(main())
