# tests/test_gold_regression.py
"""金标回归网(E2 Tier-A): 冻结金标书的门决策不许被改动悄悄翻动。零 API,进 CI。
有意改动导致红灯 → 用 `python scripts/gold_snapshot.py --repin <slug>` 重钉,commit 写 re-pin。"""
import json
from pathlib import Path
import pytest
from hiki import gate

GOLD = Path(__file__).resolve().parents[1] / "assets" / "gold_regression"
FIXTURES = sorted(GOLD.glob("*/fixture.json"))


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_gold_set_nonempty():
    assert len(FIXTURES) >= 7, f"金标夹具不足: {len(FIXTURES)} < 7"


@pytest.mark.parametrize("fx_path", FIXTURES, ids=[p.parent.name for p in FIXTURES])
def test_gold_decision_frozen(fx_path):
    fx = _load(fx_path)
    gi = gate.signal_vector_to_gate_input(fx["signals"])
    issues = gate.evaluate_ship_gate(gi)
    assert issues == fx["expected_ship_issues"], (
        f"{fx['slug']} ship_issues 变动:\n  期望={fx['expected_ship_issues']}\n  实得={issues}\n"
        f"  若为有意改动→ python scripts/gold_snapshot.py --repin {fx['slug']}")
    assert (not issues) == fx["expected_deliverable"], f"{fx['slug']} 交付决策翻转"


def test_clean_guards_ship():
    # 认证净本必须保持可交付——误报守卫
    for p in FIXTURES:
        fx = _load(p)
        if fx["role"] == "clean_guard":
            assert fx["expected_deliverable"] is True, f"{fx['slug']} 净本竟不可交付"


def test_reject_guards_blocked():
    # 拒本必须保持被拦——漏放守卫
    for p in FIXTURES:
        fx = _load(p)
        if fx["role"] == "reject_guard":
            assert fx["expected_deliverable"] is False, f"{fx['slug']} 拒本竟可交付"
