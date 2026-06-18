"""用项1(复活beat检测)重判 6 本死人复活拒收书:逐条死人复活 finding 跑 verify_revival_beats,
分 ③忠实复活(复写已渲染归来机制→门会放) / ②漏复活(突兀出场→正确拦)。
给真实"该救几本/该拦几本":一本所有死人复活 finding 都③ → 该救(死人复活维度);任一② → 仍该拦。零起草。"""
import asyncio, glob, json, os, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki.prose_continuity import verify_revival_beats
from hiki.prose_facts import split_chapters


def death_books():
    out = []
    for d in sorted(glob.glob("output/*_full")):
        if "_rerun_" in d:
            continue
        ftp, rp = Path(d) / "fact_table.json", Path(d) / "report.json"
        fm = Path(d) / "final.md"
        if not (ftp.exists() and rp.exists() and fm.exists()):
            continue
        if json.loads(rp.read_text(encoding="utf-8")).get("deliverable"):
            continue
        sis = [f for f in (json.loads(ftp.read_text(encoding="utf-8")).get("findings") or [])
               if f.get("cat") == "生死" and isinstance(f.get("ch_a"), int) and isinstance(f.get("ch_b"), int)]
        if sis:
            out.append((d, sis, fm))
    return out


async def main():
    cli = Client()
    books = death_books()
    print(f"死人复活拒收书:{len(books)} 本\n")
    book_rescue = 0
    tot3 = tot2 = 0
    for d, sis, fm in books:
        chs = split_chapters(fm.read_text(encoding="utf-8"))
        n = len(chs)
        resid = [{"who": f["who"], "clue": (f.get("why") or "")[:20],
                  "death_ch": min(f["ch_a"], n) - 1, "revive_ch": min(f["ch_b"], n) - 1}
                 for f in sis if 1 <= f["ch_b"] <= n]
        checked = await verify_revival_beats(cli, chs, resid)
        all3 = bool(checked) and all(r.get("beat_rendered") is True for r in checked)
        if all3:
            book_rescue += 1
        print(f"== {os.path.basename(d)[:22]} | {'✅该救(全③)' if all3 else '⛔仍拦(有②)'} ==")
        for r in checked:
            br = r.get("beat_rendered")
            tag = "③渲染→放" if br is True else ("②突兀→拦" if br is False else "?判不出→保守拦")
            if br is True: tot3 += 1
            elif br is False: tot2 += 1
            print(f"   {r['who']} 死@{r['death_ch']+1}→活@{r['revive_ch']+1}: {tag} | {(r.get('beat_mech') or '')[:30]}")
        print()
    print("=" * 56)
    print(f"finding 级: ③忠实复活(放) {tot3} | ②漏复活/真矛盾(拦) {tot2}")
    print(f"书级: 死人复活维度该救回(全③) {book_rescue}/{len(books)} 本")
    print(f"\n¥{cli.cost_cny:.2f} | {cli.calls} calls")


asyncio.run(main())
