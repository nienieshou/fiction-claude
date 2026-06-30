# scripts/jury_to_scorecard.py
"""jury JSON → scorecard_<judge>.yaml(喂 scripts/hfl_ingest.py)。
用法: python scripts/jury_to_scorecard.py <jury_dir> --judge opus --out <dir>/scorecard_opus.yaml
见 spec '存储 + ingest 契约' 节。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

_DIMS = ("故事性", "笔力", "人", "承重")


def build_scorecard(jury_by_slug: dict, rater: str, date: str | None = None) -> dict:
    scores = {}
    for slug, j in jury_by_slug.items():
        scores[slug] = {
            **{k: j[k] for k in _DIMS if k in j},
            "追读": "", "最致命": j.get("reject_reason", ""), "点评": j.get("comments", ""),
        }
    out = {"rater": rater, "scores": scores}
    if date is not None:
        out["date"] = date      # date=None 时省略键: 防 hfl_ingest 把 YAML null 读成字符串 "None"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("jury_dir")
    ap.add_argument("--judge", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=None)
    a = ap.parse_args(argv)
    import yaml
    jd = Path(a.jury_dir)
    jury = {}
    for p in sorted(jd.glob(f"*__{a.judge}.json")):
        slug = p.name.split("__")[0]
        jury[slug] = json.loads(p.read_text(encoding="utf-8"))
    sc = build_scorecard(jury, rater=a.judge, date=a.date)
    Path(a.out).write_text(yaml.safe_dump(sc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"✓ {len(jury)} 本 → {a.out}")


if __name__ == "__main__":
    main()
