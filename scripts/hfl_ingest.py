"""人工评分回流:读 output/eval5/scorecard_*.yaml + 各 slug 的 report.json,
算加权总分(故30/笔25/人25/承20)+ 评委间一致性(IRR),汇入 assets/hfl.jsonl(喂校准器)。
用法: PYTHONPATH=src python scripts/hfl_ingest.py output/eval5 [--round human-eval-5] [--write]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
_W = {"故事性": 0.30, "笔力": 0.25, "人": 0.25, "承重": 0.20}
_DIMS = list(_W)


def _sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"


def _total(dims: dict) -> float:
    return round(sum(float(dims[d]) * w for d, w in _W.items()), 1)


def _auto_signals(slug_dir: Path) -> dict:
    rep = slug_dir / "report.json"
    if not rep.exists():
        return {}
    r = json.loads(rep.read_text(encoding="utf-8"))
    return {"deliverable": r.get("deliverable"), "交付门": r.get("交付门"),
            "grade": (r.get("grade") or {}).get("grade") if isinstance(r.get("grade"), dict) else r.get("grade"),
            "title": r.get("title"), "source": r.get("source")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir")
    ap.add_argument("--round", default="human-eval-5")
    ap.add_argument("--write", action="store_true", help="实际追加 assets/hfl.jsonl(默认只预览)")
    a = ap.parse_args()
    d = Path(a.eval_dir)
    cards = [p for p in sorted(d.glob("scorecard_*.yaml")) if "template" not in p.name]
    if not cards:
        print(f"没找到 {d}/scorecard_<名>.yaml(template 不算)"); return
    import yaml
    sha = _sha()
    records, by_book = [], {}                       # by_book[slug] = list[(rater, dims, total)]
    for c in cards:
        doc = yaml.safe_load(c.read_text(encoding="utf-8")) or {}
        rater, date, scores = doc.get("rater", c.stem), doc.get("date", ""), doc.get("scores") or {}
        for slug, s in scores.items():
            dims = {k: s.get(k) for k in _DIMS}
            if any(not isinstance(v, (int, float)) for v in dims.values()):
                print(f"  ⚠ 跳过 {rater}/{slug}: 维度分未填全 {dims}"); continue
            auto = _auto_signals(d / slug)
            tot = _total(dims)
            records.append({"date": date, "scorer": rater, "round": a.round,
                            "title": auto.get("title") or slug, "source": auto.get("source") or slug,
                            "slug": slug, "dims": dims, "total": tot,
                            "comments": f"追读{s.get('追读','')} | 最致命:{s.get('最致命','')} | {s.get('点评','')}",
                            "auto_signals": {k: auto.get(k) for k in ("deliverable", "交付门", "grade")},
                            "version": sha})
            by_book.setdefault(slug, []).append((rater, dims, tot))

    print(f"\n=== 人工评分汇总(round={a.round}, code={sha}) ===")
    print(f"{'slug':18} {'评委数':5} {'故':4}{'笔':4}{'人':4}{'承':4} {'总分':6} {'IRR(总分极差)':10}")
    for slug, rows in by_book.items():
        n = len(rows)
        means = {dd: round(sum(r[1][dd] for r in rows) / n) for dd in _DIMS}
        tots = [r[2] for r in rows]
        mt = round(sum(tots) / n, 1)
        spread = round(max(tots) - min(tots), 1) if n > 1 else 0.0
        print(f"{slug:18} {n:^5} {means['故事性']:<4}{means['笔力']:<4}{means['人']:<4}{means['承重']:<4} "
              f"{mt:<6} ±{spread}")
    if by_book:
        allt = [r[2] for rows in by_book.values() for r in rows]
        print(f"\n批均总分 {round(sum(allt)/len(allt),1)} | 出货线75 | 标杆90"
              f" — 对比机器 Opus四维(退婚~64/傲世~59/六零~68)看校准误差")

    out = Path("assets/hfl.jsonl")
    if a.write:
        with out.open("a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n✓ 追加 {len(records)} 条 → {out}")
    else:
        print(f"\n(预览 {len(records)} 条,未写;加 --write 落 {out})")


if __name__ == "__main__":
    main()
