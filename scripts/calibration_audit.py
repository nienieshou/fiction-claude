"""E3 Slice1 只读审计入口: 打印 HFL 兼容性/假阳性/溯源分歧报告。零写入。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 报告含中文 + ⚠/∧/→ 等非 GBK 符号; Windows 控制台默认 GBK 编码会 UnicodeEncodeError
# (codex 实证 print('⚠') 即崩) → 强制 UTF-8 stdout。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from hiki import calibration  # noqa: E402


def main():
    rows, errors = calibration.load_hfl(ROOT / "assets" / "hfl.jsonl")
    gold = calibration.load_gold_signal_vectors(ROOT / "assets" / "gold_regression")
    compat = calibration.compat_report(rows, errors)
    fa = calibration.false_accept_lens(rows)
    prov = calibration.provenance_divergence(rows, gold)
    print(calibration.format_report(compat, fa, prov))


if __name__ == "__main__":
    main()
