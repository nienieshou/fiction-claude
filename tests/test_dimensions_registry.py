"""C6 子项目①: DIMENSIONS 可信单源 + 一致性守卫(目录 gating 集 = 门实际硬拦)。
零 API; 纯函数驱动 evaluate_ship_gate。"""
from hiki import audit, gate


def _benign_sig() -> dict:
    """全良性基线: evaluate_ship_gate(默认 thr) 应零 issue。"""
    return {
        "阵营串线": 0, "过短章数": 0, "暗黑比": 0.0, "预告跳过": None,
        "plan维14复活": 0, "事实表跑过": True, "事实表复活残留": 0,
        "残缝": 0, "final_consistent": True, "事件重演": 0, "章内双版本": None,
        "数值真矛盾": 0, "身份真矛盾": 0, "承重审计崩溃": False,
        "开篇代入感": 100, "早段重复": 0,
    }


# 每个 gating signal → (触发值, 需附带的其他键覆盖)
_TRIGGER = {
    "阵营串线": (1, {}),
    "数值真矛盾": (6, {}),
    "身份真矛盾": (6, {}),
    "plan维14复活": (1, {"事实表跑过": False}),
    "事实表复活残留": (1, {}),
}


def test_benign_baseline_no_issues():
    assert gate.evaluate_ship_gate(_benign_sig()) == []


def test_gating_dims_actually_gate():
    """每个 gating=True 维的每个 signal 触发 → 门必产 issue。"""
    for d in audit.DIMENSIONS:
        if not d.gating:
            continue
        assert d.signals, f"维{d.id} gating=True 但无 signals"
        for s in d.signals:
            val, extra = _TRIGGER[s]
            sig = _benign_sig()
            sig[s] = val
            sig.update(extra)
            assert gate.evaluate_ship_gate(sig), f"维{d.id} signal {s} 触发应产 issue"


def test_advisory_signals_do_not_gate_under_default_config():
    """降级信号(block_on_*=False)触发 → 默认 config 不产 issue。"""
    for s, val in (("事件重演", 99), ("预告跳过", "x"), ("final_consistent", False)):
        sig = _benign_sig()
        sig[s] = val
        assert gate.evaluate_ship_gate(sig) == [], f"{s} 默认应 advisory 不拦"


def test_gating_dim_id_set_pinned():
    """分类钉死: gating 维集漂移即断。"""
    assert {d.id for d in audit.DIMENSIONS if d.gating} == {2, 6, 12, 14}


def test_gating_signal_names_valid():
    """每个 gating 维引用的 signal 键 ∈ 门桥接输出键(防 typo/死信号名)。"""
    valid = set(gate.signal_vector_to_gate_input({}).keys())
    for d in audit.DIMENSIONS:
        for s in d.signals:
            assert s in valid, f"维{d.id} signal {s} 不在门输入键"


def test_non_dim_floors_disjoint_from_dim_signals():
    """非维地板与 gating 维 signal 不相交(地板本就非维)。"""
    dim_sigs = {s for d in audit.DIMENSIONS for s in d.signals}
    assert not (set(audit.NON_DIM_GATE_FLOORS) & dim_sigs)
