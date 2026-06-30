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


def _plan(chapter_scene_idxs):
    return {"chapters": [{"scenes": [{"source_scene_index": i} for i in idxs]} for idxs in chapter_scene_idxs]}


def test_dup_chapter_overlap_flagged():
    p = _plan([[5, 6], [6, 7], [9]])   # ch0∩ch1={6}
    fs = pc.duplicate_chapter_intent(p)
    assert len(fs) == 1
    assert fs[0]["category"] == "章节复制/注水" and fs[0]["severity"] == "hard"
    assert "6" in fs[0]["contradiction"]


def test_dup_chapter_no_overlap():
    assert pc.duplicate_chapter_intent(_plan([[1, 2], [3, 4]])) == []


def test_dup_chapter_excludes_sentinel():
    assert pc.duplicate_chapter_intent(_plan([[-1], [-1]])) == []   # -1=无源, 不算重复


def test_dup_chapter_missing_field_no_crash():
    assert pc.duplicate_chapter_intent({}) == []
    assert pc.duplicate_chapter_intent({"chapters": [{"scenes": [{}]}]}) == []   # 无 source_scene_index


def test_predraft_checks_aggregates():
    b = _bible([("方欣", "苏媚禧生母"), ("李诗蕊", "苏媚禧生母")])
    p = _plan([[5], [5]])
    fs = pc.predraft_checks(b, p)
    cats = sorted(f["category"] for f in fs)
    assert cats == ["混名/认亲矛盾", "章节复制/注水"]
