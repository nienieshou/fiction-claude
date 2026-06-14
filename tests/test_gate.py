"""交付门纯函数 gate.evaluate_ship_gate(D1 后可测)。零 API。"""
from hiki import gate

D = gate.SHIP_GATE_DEFAULTS


def test_clean_signals_deliverable():
    assert gate.evaluate_ship_gate({}, D) == []
    assert gate.evaluate_ship_gate({"final_consistent": True}, D) == []


def test_threshold_boundaries():
    assert gate.evaluate_ship_gate({"过短章数": 2}, D) == []           # 2<3
    assert len(gate.evaluate_ship_gate({"过短章数": 3}, D)) == 1       # >=3
    assert gate.evaluate_ship_gate({"暗黑比": 0.25}, D) == []          # =0.25 不拦(>)
    assert len(gate.evaluate_ship_gate({"暗黑比": 0.26}, D)) == 1
    assert gate.evaluate_ship_gate({"残缝": 8}, D) == []               # =8 不拦(>)
    assert len(gate.evaluate_ship_gate({"残缝": 9}, D)) == 1
    assert len(gate.evaluate_ship_gate({"事件重演": 1}, D)) == 1       # >=1


def test_spine_net_min_2():
    assert gate.evaluate_ship_gate({"数值真矛盾": 1, "身份真矛盾": 0}, D) == []      # 1<2
    assert len(gate.evaluate_ship_gate({"数值真矛盾": 1, "身份真矛盾": 1}, D)) == 1  # 合计2


def test_death_authority_fact_table_over_plan_dim14():
    assert gate.evaluate_ship_gate({"plan维14复活": 2, "事实表跑过": True}, D) == []
    assert len(gate.evaluate_ship_gate({"plan维14复活": 2, "事实表跑过": False}, D)) == 1


def test_final_consistent_default_true():
    assert gate.evaluate_ship_gate({}, D) == []
    assert len(gate.evaluate_ship_gate({"final_consistent": False}, D)) == 1


def test_audit_crash_blocks():
    assert len(gate.evaluate_ship_gate({"承重审计崩溃": True}, D)) == 1


def test_config_thresholds_override():
    loose = {**D, "spine_net_min": 5}
    assert gate.evaluate_ship_gate({"数值真矛盾": 2, "身份真矛盾": 2}, loose) == []   # 4<5
    strict = {**D, "seam_residual_max": 0}
    assert len(gate.evaluate_ship_gate({"残缝": 1}, strict)) == 1


def test_multi_signal_accumulates():
    issues = gate.evaluate_ship_gate(
        {"过短章数": 3, "残缝": 9, "事件重演": 2, "数值真矛盾": 2, "承重审计崩溃": True}, D)
    assert len(issues) == 5
