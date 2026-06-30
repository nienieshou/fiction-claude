# tests/test_validation_tabulate.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validation_tabulate as vt


def _rec(slug, deliverable, opus, gpt, observed=(), upstream=None, severity=None):
    """合成 BookRecord. opus/gpt = (承重, deliver) 简写; 其余维补占位."""
    def jud(t):
        carry, deliver = t
        total = round(60 * 0.30 + 60 * 0.25 + 60 * 0.25 + carry * 0.20, 2)  # story4(其余维=60)
        return {"故事性": 60, "笔力": 60, "人": 60, "承重": carry,
                "total": total, "deliver": deliver, "reject_reason": "", "comments": ""}
    return vt.BookRecord(slug=slug, deliverable=deliverable,
                         jury={"opus": jud(opus), "gpt55": jud(gpt)},
                         upstream=upstream or {"opus": [], "gpt55": []},
                         observed=list(observed),
                         severity=severity if severity is not None else min(opus[0], gpt[0]))


def test_failure_categories_present():
    assert "境界乱序" in vt.FAILURE_CATEGORIES
    assert "性别错" in vt.FAILURE_CATEGORIES
    assert len(vt.FAILURE_CATEGORIES) >= 8


def test_bookrecord_construct():
    r = _rec("b1", True, (80, "yes"), (60, "no"))
    assert r.slug == "b1" and r.deliverable is True
    assert r.jury["gpt55"]["承重"] == 60
    assert r.severity == 60
