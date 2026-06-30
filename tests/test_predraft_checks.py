# tests/test_predraft_checks.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import predraft_checks as pc


def _bible(chars):
    return {"characters": [{"name": n, "key_relation": kr} for n, kr in chars]}


def test_kinship_dup_mother_flagged():
    b = _bible([("方欣", "苏媚禧生母"), ("李诗蕊", "苏媚禧生母"), ("顾巍", "苏媚禧小叔")])
    fs = pc.kinship_uniqueness(b)
    assert len(fs) == 1
    f = fs[0]
    assert f["category"] == "混名/认亲矛盾" and f["severity"] == "hard"
    assert "苏媚禧" in f["contradiction"] and "方欣" in f["contradiction"] and "李诗蕊" in f["contradiction"]
    assert set(f) == {"category", "severity", "evidence_path", "contradiction", "confidence", "parse_pattern"}


def test_kinship_unique_ok():
    b = _bible([("方欣", "苏媚禧生母"), ("苏强", "苏媚禧生父")])  # 不同角色,各唯一
    assert pc.kinship_uniqueness(b) == []


def test_kinship_same_claimant_not_dup():
    # 同一 claimant 名重复出现不算两人(去重 claimant)
    b = _bible([("方欣", "苏媚禧生母"), ("方欣", "苏媚禧亲生母亲")])
    assert pc.kinship_uniqueness(b) == []


def test_kinship_missing_field_no_crash():
    assert pc.kinship_uniqueness({"characters": [{"name": "甲"}]}) == []   # 无 key_relation
    assert pc.kinship_uniqueness({}) == []                                  # 无 characters
