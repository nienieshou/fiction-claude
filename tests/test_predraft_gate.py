# tests/test_predraft_gate.py
from hiki.predraft import predraft_gate_check, PREDRAFT_MAX_PLAN_REGEN


def _plan(chapter_idxs):
    # chapter_idxs: 每章的 source_scene_index 列表
    return {"chapters": [{"scenes": [{"source_scene_index": i} for i in idxs]} for idxs in chapter_idxs]}


SCENES = [{"t": i} for i in range(20)]   # len=20


def test_gate_block_on_shared_source():
    g = predraft_gate_check(_plan([[5, 6], [6, 7]]), SCENES)   # ch0∩ch1={6}
    assert g["blocked"] is True
    assert any(f["severity"] == "hard" and f["category"] == "章节复制/注水" for f in g["findings"])
    assert "6" in str(g["evidence"]["dup_pairs"])


def test_gate_no_block_no_share():
    g = predraft_gate_check(_plan([[1, 2], [3, 4]]), SCENES)
    assert g["blocked"] is False


def test_gate_unsourced_warn_not_block():
    # 某章全 -1/越界 → unsourced 100% > 阈 → warn, 不 blocked
    g = predraft_gate_check(_plan([[-1, 99], [3, 4]]), SCENES)
    assert g["blocked"] is False
    assert any(f["severity"] == "warn" for f in g["findings"])
    assert 0 in [c for c in g["evidence"]["unsourced_chapters"]]


def test_gate_missing_fields_safe():
    assert predraft_gate_check({}, SCENES)["blocked"] is False
    assert predraft_gate_check({"chapters": [{"scenes": [{}]}]}, SCENES)["blocked"] is False   # 无 source_scene_index
    assert PREDRAFT_MAX_PLAN_REGEN == 2
