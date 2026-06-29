"""人工评分回流:读 <eval_dir>/scorecard_*.yaml + 各 slug report.json,
构造 schema-正确的 hfl 行(内联冻结 report['signals'] → 可拟合)+ 加权总分 + IRR,
幂等汇入 hfl.jsonl(喂校准飞轮)。
用法: PYTHONPATH=src python scripts/hfl_ingest.py <eval_dir> [--round R] [--write] [--allow-duplicate] [--hfl PATH]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:                                              # ⚠ skip 行走 stderr; Windows piped stderr 默认 gbk
    sys.stdout.reconfigure(encoding="utf-8")      # 会 UnicodeEncodeError(子进程崩)→ 同时硬化 stderr
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from hiki import calibration  # noqa: E402

DEFAULT_HFL = ROOT / "assets" / "hfl.jsonl"


def _existing_raw(path):
    """现有 hfl.jsonl 按 raw json dict 逐行读(非 load_hfl: 需保留 round/auto_signals 原 dict 算幂等键)。"""
    if not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    return out


def _extract_dims(scores_for_slug):
    """按可识别 schema 取四维(标签逐字保留, 不静默映射)。无完整 schema → 空(build_hfl_row 拒)。"""
    for w in calibration.RUBRIC_WEIGHTS.values():
        if all(k in scores_for_slug for k in w):
            return {k: scores_for_slug[k] for k in w}
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir")
    ap.add_argument("--round", default="human-eval-5")
    ap.add_argument("--write", action="store_true", help="实际追加(默认只预览)")
    ap.add_argument("--allow-duplicate", action="store_true", help="绕过幂等去重")
    ap.add_argument("--hfl", default=str(DEFAULT_HFL), help="目标 hfl.jsonl(默认 assets/hfl.jsonl)")
    a = ap.parse_args()
    d = Path(a.eval_dir)
    cards = [p for p in sorted(d.glob("scorecard_*.yaml")) if "template" not in p.name]
    if not cards:
        print(f"没找到 {d}/scorecard_<名>.yaml(template 不算)")
        return
    import yaml
    ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing = _existing_raw(a.hfl)
    records, by_book, skipped = [], {}, 0
    for c in cards:
        doc = yaml.safe_load(c.read_text(encoding="utf-8")) or {}
        rater = doc.get("rater", c.stem)
        scores = doc.get("scores") or {}
        date = str(doc.get("date", "")) or None
        for slug, s in scores.items():
            rep_path = d / slug / "report.json"
            if not rep_path.exists():
                print(f"  ⚠ 跳过 {rater}/{slug}: 无 report.json", file=sys.stderr)
                skipped += 1
                continue
            report = json.loads(rep_path.read_text(encoding="utf-8"))
            comments = f"追读{s.get('追读','')} | 最致命:{s.get('最致命','')} | {s.get('点评','')}"
            try:
                row = calibration.build_hfl_row(
                    scorer=rater, slug=slug, dims=_extract_dims(s), comments=comments,
                    report=report, round_=a.round, output_dir=d / slug,
                    ingested_at=ingested_at, date=date)
            except ValueError as e:
                print(f"  ⚠ 跳过 {rater}/{slug}: {e}", file=sys.stderr)
                skipped += 1
                continue
            if not a.allow_duplicate and calibration.find_duplicate(existing, row):
                print(f"  ⚠ 跳过 {rater}/{slug}: 重复(scorer/slug/round/signals_hash 已存在)", file=sys.stderr)
                skipped += 1
                continue
            records.append(row)
            existing.append(row)   # 防同批内重复
            by_book.setdefault(slug, []).append((rater, row["dims"], row["total"]))

    print(f"\n=== 人工评分汇总(round={a.round}) ===")
    for slug, rows in by_book.items():
        n = len(rows)
        tots = [r[2] for r in rows]
        mt = round(sum(tots) / n, 1)
        spread = round(max(tots) - min(tots), 1) if n > 1 else 0.0
        print(f"{slug:18} 评委{n} 总分{mt} IRR±{spread}")

    out = Path(a.hfl)
    if a.write:
        with out.open("a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n✓ 追加 {len(records)} 条 → {out}(跳过 {skipped})")
    else:
        print(f"\n(预览 {len(records)} 条, 跳过 {skipped}; 加 --write 落 {out})")


if __name__ == "__main__":
    main()
