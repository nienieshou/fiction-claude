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
# 6 == gate SHIP_GATE_DEFAULTS["spine_net_min"]; 维6与12共享该"数值+身份求和"阈值(非独立硬门), 阈值若调此处需同步
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


# 完整性守卫(opus 终审 Important): 枚举门所有输入键, 逐个置触发值, 断言"凡默认 config 下能产 issue
# 的键, 必在 (gating维 signals ∪ NON_DIM_GATE_FLOORS) 内"。这是 test_gating_dim_id_set_pinned 的反向
# (门→注册表)覆盖: 未来新增 gating 分支 / 翻 block_on_* / 加 dim 信号忘标注册表 → 此测失败报漂移。
_TRIP_ALL = {
    "阵营串线": 1, "过短章数": 99, "暗黑比": 1.0, "预告跳过": "x",
    "plan维14复活": 1, "事实表跑过": False, "事实表复活残留": 1, "残缝": 99,
    "final_consistent": False, "事件重演": 99, "章内双版本": 1,
    "数值真矛盾": 99, "身份真矛盾": 99, "承重审计崩溃": True,
    "开篇代入感": 0, "早段重复": 1,
}


def test_gate_branches_fully_covered_by_registry():
    allowed = {s for d in audit.DIMENSIONS for s in d.signals} | set(audit.NON_DIM_GATE_FLOORS)
    for key in gate.signal_vector_to_gate_input({}):
        sig = _benign_sig()
        sig[key] = _TRIP_ALL[key]
        if gate.evaluate_ship_gate(sig):          # 该键单独触发能产硬拦
            assert key in allowed, f"门键 {key} 默认硬拦但未在注册表 gating signals/非维地板 → 漂移!"
