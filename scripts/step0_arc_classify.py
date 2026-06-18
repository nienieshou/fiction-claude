"""Step0:给死人复活拒收书补抽生死弧,把每个**被门 flag 的角色**分三类。
目的:量化"门重判能救回几本(dies_returns 假阳性)" vs "真矛盾需预防/点修(dies_final)" vs 模糊(无弧),
并用已知真值(桑念=dies_returns、phantom src_freq=0)校弧准确率。零起草,只跑专用弧 pass。"""
import asyncio, glob, json, os, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
os.environ["HIKI_SPINE"] = "1"
from hiki.client import Client
from hiki import mining, audit

# 已独立坐实的真值(grep/v3):用于校准弧准确率
GT = {"桑念": "dies_returns"}
PHANTOM_HINT = "src_freq=0 → 源书无此人,应判 not_a_character/无弧"


def death_books():
    """自动发现含 生死 findings 的拒收书(排除 _rerun 重跑产物,聚焦原拒收本)。"""
    out = []
    for d in sorted(glob.glob("output/*_full")):
        if "_rerun_" in d:
            continue
        ftp = Path(d) / "fact_table.json"
        rp = Path(d) / "report.json"
        if not ftp.exists() or not rp.exists():
            continue
        rep = json.loads(rp.read_text(encoding="utf-8"))
        if rep.get("deliverable"):          # 只看拒收
            continue
        ft = json.loads(ftp.read_text(encoding="utf-8"))
        flagged = [f for f in (ft.get("findings") or [])
                   if f.get("cat") == "生死" and f.get("ch_a") and f.get("ch_b")]
        if flagged:
            out.append((d, flagged))
    return out


async def main():
    cli = Client()
    books = death_books()
    print(f"死人复活拒收书:{len(books)} 本\n")
    rows = []
    for d, flagged in books:
        src = next(iter(glob.glob(d + "/source/*.txt")), None)
        if not src:
            print(f"!! 缺源: {d}"); continue
        clean = Path(src).read_text(encoding="utf-8", errors="ignore")
        n_life = min(48, max(20, len(clean) // 30000))     # mine_book 同款细窗
        chunks = mining.chunk_by_chapters(clean, n_chunks=n_life)
        results = await mining.extract_life_events_pass(cli, chunks)
        arcs = mining.collect_life_events(results)
        print(f"== {os.path.basename(d)[:22]} | {len(clean)}字/{n_life}窗 | 抽 {len(arcs)} 弧 ==")
        for f in flagged:
            who = f["who"]
            freq = clean.count(who)
            fate = arcs.get(who, {}).get("fate", "无弧")
            verdict = audit.reconcile_revival(arcs, who)
            gt = GT.get(who, "")
            note = f" [真值={gt}]" if gt else (" [phantom?]" if freq == 0 else "")
            rows.append({"book": os.path.basename(d)[:14], "who": who, "freq": freq,
                         "fate": fate, "verdict": verdict, "gt": gt})
            print(f"   {who}({freq}) 复写死@{f['ch_a']}→活@{f['ch_b']} | 源弧={fate} → 门={verdict}{note}")
        print()

    # 汇总
    print("=" * 56)
    fates = Counter(r["fate"] for r in rows)
    rescuable = sum(1 for r in rows if r["fate"] in ("dies_returns", "fake_death"))
    real = sum(1 for r in rows if r["fate"] == "dies_final")
    fuzzy = sum(1 for r in rows if r["fate"] == "无弧")
    n = len(rows)
    print(f"被 flag 角色 {n} 个,跨 {len(books)} 本")
    print(f"  ① dies_returns/fake_death(门重判→救回,假阳性): {rescuable}/{n}")
    print(f"  ② dies_final(真矛盾,需预防/点修):              {real}/{n}")
    print(f"  ③ 无弧(保守仍拦,模糊):                          {fuzzy}/{n}")
    # 弧准确率(仅对有真值/phantom 的)
    gt_hits = [(r["who"], r["fate"], r["gt"]) for r in rows if r["gt"]]
    print("\n真值校准:")
    for who, fate, gt in gt_hits:
        print(f"  {who}: 弧={fate} 真值={gt} {'✅' if fate == gt else '❌'}")
    phantoms = [r for r in rows if r["freq"] == 0]
    for r in phantoms:
        print(f"  {r['who']}(src=0,phantom): 弧={r['fate']} {'✅符合预期(无弧/not_a_char)' if r['fate'] == '无弧' else '⚠抽出了弧(可能误造)'}")
    # 按本统计可救
    by_book = {}
    for r in rows:
        by_book.setdefault(r["book"], []).append(r)
    book_rescue = sum(1 for b, rs in by_book.items()
                      if all(x["fate"] in ("dies_returns", "fake_death") for x in rs))
    print(f"\n整本可门重判救回(该本所有 flag 角色都是 dies_returns): {book_rescue}/{len(by_book)} 本")
    Path("output/_step0_arc.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n¥{cli.cost_cny:.2f} | {cli.calls} calls → output/_step0_arc.json")


asyncio.run(main())
