# tests/test_defect_bank_invariants.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "assets" / "defect_bank.jsonl"
GUARDS = ROOT / "assets" / "gold_regression" / "clean_guards.json"

REQUIRED_KEYS = {"book", "path", "ch", "cat", "detector", "id", "baseline_hit"}


def _rows():
    return [json.loads(l) for l in BANK.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_every_row_has_required_keys():
    for r in _rows():
        missing = REQUIRED_KEYS - r.keys()
        assert not missing, f"defect {r.get('id','?')} 缺键 {missing}"


def test_ids_unique():
    ids = [r["id"] for r in _rows()]
    assert len(ids) == len(set(ids)), "defect_bank id 有重复"


def test_baseline_hit_is_bool():
    for r in _rows():
        assert isinstance(r["baseline_hit"], bool), f"{r['id']} baseline_hit 非 bool"


def test_clean_guards_present():
    guards = json.loads(GUARDS.read_text(encoding="utf-8"))
    assert set(guards) == {"ZYGGY02252", "ZYGGY02079", "CPBXN00188"}
