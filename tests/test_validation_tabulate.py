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


def test_is_false_accept_rules():
    # 门放行 + 某judge deliver=no → 假阳
    r = _rec("b", True, (80, "yes"), (70, "no"))
    assert vt.is_false_accept(r, "gpt55") is True
    assert vt.is_false_accept(r, "opus") is False
    # 门放行 + 承重<50 → 假阳(即便 deliver=yes)
    r2 = _rec("b2", True, (45, "yes"), (80, "yes"))
    assert vt.is_false_accept(r2, "opus") is True
    # 门未放行 → 不算假阳(假阳是"门说行但judge说不行")
    r3 = _rec("b3", False, (10, "no"), (10, "no"))
    assert vt.is_false_accept(r3, "opus") is False


def test_false_accept_table_counts_and_overlap():
    recs = [
        _rec("p1", True, (40, "no"), (40, "no")),   # 两judge都假阳 → overlap
        _rec("p2", True, (80, "yes"), (45, "no")),  # 仅 gpt55 假阳
        _rec("p3", True, (90, "yes"), (90, "yes")), # 无假阳
        _rec("r1", False, (10, "no"), (10, "no")),  # 门未放行,不计入 passed
    ]
    t = vt.false_accept_table(recs)
    assert t["n_passed"] == 3
    assert t["per_judge"]["opus"]["n"] == 1 and t["per_judge"]["gpt55"]["n"] == 2
    assert t["n_overlap"] == 1 and t["overlap_slugs"] == ["p1"]
    # 行级证据表(spec 要):p1×2(两judge) + p2×1(gpt55) = 3 行
    assert len(t["rows"]) == 3
    assert any(r["slug"] == "p2" and r["judge"] == "gpt55" and r["承重"] == 45 for r in t["rows"])


def test_gate_decision_overlap_stop():
    # P>=4, 重叠假阳>=2 → unsafe_consensus
    recs = [_rec(f"p{i}", True, (40, "no"), (40, "no")) for i in range(2)] + \
           [_rec(f"q{i}", True, (90, "yes"), (90, "yes")) for i in range(3)]
    d = vt.gate_decision(recs)
    assert d["P"] == 5 and d["n_overlap"] == 2 and d["verdict"] == "unsafe_consensus"


def test_gate_decision_single_judge_investigate():
    # P>=4, 仅 gpt55 假阳>=2, 重叠<2 → single_judge_investigate(不全局停)
    recs = [_rec(f"p{i}", True, (90, "yes"), (40, "no")) for i in range(2)] + \
           [_rec(f"q{i}", True, (90, "yes"), (90, "yes")) for i in range(3)]
    d = vt.gate_decision(recs)
    assert d["verdict"] == "single_judge_investigate"
    assert d["per_judge_fp"]["gpt55"] == 2 and d["n_overlap"] == 0


def test_gate_decision_low_power():
    # P<4 → low_power_inconclusive(不当安全升档)
    recs = [_rec("p1", True, (90, "yes"), (90, "yes"))] + \
           [_rec(f"r{i}", False, (10, "no"), (10, "no")) for i in range(7)]
    d = vt.gate_decision(recs)
    assert d["P"] == 1 and d["verdict"] == "low_power_inconclusive"


def test_gate_decision_safe_advance():
    recs = [_rec(f"p{i}", True, (90, "yes"), (85, "yes")) for i in range(5)]
    d = vt.gate_decision(recs)
    assert d["verdict"] == "safe_advance"
