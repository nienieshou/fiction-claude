"""CLI 入口。当前可用：ingest（P0 清洗，无需 API key）。"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .ingest import ingest


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="hiki", description="小说复写引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("ingest", help="P0 清洗单本源 txt")
    pi.add_argument("src", help="源 .txt 路径")
    pi.add_argument("--out", default=None, help="输出目录（默认 output/<源名>/source）")

    args = ap.parse_args()
    if args.cmd == "ingest":
        src = Path(args.src)
        out = Path(args.out) if args.out else Path("output") / src.stem / "source"
        meta = ingest(src, out)
        print(f"✓ ingest 完成 → {out}")
        print(meta.to_json())


if __name__ == "__main__":
    main()
