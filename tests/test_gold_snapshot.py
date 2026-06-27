# tests/test_gold_snapshot.py
import json
import pytest
from pathlib import Path
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "gold_snapshot", Path(__file__).resolve().parents[1] / "scripts" / "gold_snapshot.py")
gold_snapshot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gold_snapshot)


def _report(**sig_over):
    sig = {
        "schema_version": 1, "deliverable": True, "grade": "A", "opening_immersion": 85,
        "reenact_hits": 4, "seam_detected": 13, "seam_residual": 1, "dark_ratio": 0.03,
        "spine_num_contra": 3, "spine_id_contra": 0, "ft_revival_residual": 0,
        "too_short_chapters": 0, "final_consistent": True, "intra_repeat_chapters": 0,
        "early_repeat": None, "opening_overload": None}
    sig.update(sig_over)
    return {"deliverable": sig["deliverable"], "signals": sig}


def test_snapshot_clean_ship():
    fx = gold_snapshot.snapshot_one(_report(), "ZYGGY02252", "clean_guard")
    assert fx["expected_deliverable"] is True
    assert fx["expected_ship_issues"] == []
    assert fx["signal_schema_version"] == 1


def test_snapshot_reject_too_short():
    fx = gold_snapshot.snapshot_one(
        _report(deliverable=False, too_short_chapters=4), "BPBXS00052", "reject_guard")
    assert fx["expected_deliverable"] is False
    assert any("过短" in i for i in fx["expected_ship_issues"])


def test_snapshot_refuses_when_decision_mismatch():
    # producer 记 deliverable=True，但信号含 4 章过短 → 还原必拒 → 不一致 → 拒写
    with pytest.raises(ValueError, match="决策不一致"):
        gold_snapshot.snapshot_one(
            _report(deliverable=True, too_short_chapters=4), "X", "snapshot")
