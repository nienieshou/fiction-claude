"""E3 Slice1b: produce._engine_commit best-effort + signals 不含 engine_commit。"""
import subprocess
from hiki import produce, signals


def test_engine_commit_success(monkeypatch):
    monkeypatch.setattr(produce.subprocess, "check_output", lambda *a, **k: b"abc123def456\n")
    assert produce._engine_commit() == "abc123def456"


def test_engine_commit_failure_returns_unknown(monkeypatch):
    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "git")
    monkeypatch.setattr(produce.subprocess, "check_output", boom)
    assert produce._engine_commit() == "unknown"


def test_signal_vector_never_carries_engine_commit():
    sv = signals.build_signal_vector(
        deliverable=True, grade="A", immersion_score=80, reenact_hits=0,
        seam_detected=1, seam_residual=0, dark_ratio=0.0, spine_num_contra=0,
        spine_id_contra=0, ft_revival_residual=0, too_short_chapters=0,
        final_consistent=True, intra_repeat_chapters=0)
    assert "engine_commit" not in sv   # 溯源必须 top-level, 绝不进冻结向量
