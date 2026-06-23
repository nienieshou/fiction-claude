"""标准信号向量(冻结 schema)。零 API。
止血点:human-eval-5/editor-eval-1/-2 各记不同信号,跨批无法合池标定质量代理(相0 标定实证)。"""
from hiki import signals


def test_schema_has_frozen_version():
    v = signals.build_signal_vector(
        deliverable=True, grade="A", immersion_score=88, reenact_hits=3,
        seam_detected=21, seam_residual=0, dark_ratio=0.05,
        spine_num_contra=0, spine_id_contra=0, ft_revival_residual=0,
        too_short_chapters=0, final_consistent=True, intra_repeat_chapters=0)
    assert v["schema_version"] == signals.SIGNAL_SCHEMA_VERSION
    assert isinstance(signals.SIGNAL_SCHEMA_VERSION, int)


def test_all_frozen_keys_present():
    v = signals.build_signal_vector(
        deliverable=False, grade="X", immersion_score=None, reenact_hits=0,
        seam_detected=0, seam_residual=0, dark_ratio=0.0,
        spine_num_contra=0, spine_id_contra=0, ft_revival_residual=0,
        too_short_chapters=0, final_consistent=False, intra_repeat_chapters=0)
    # 冻结键集——新增信号只许追加,不许改名/删,否则破合池
    assert set(v) == {
        "schema_version", "deliverable", "grade", "opening_immersion",
        "reenact_hits", "seam_detected", "seam_residual", "dark_ratio",
        "spine_num_contra", "spine_id_contra", "ft_revival_residual",
        "too_short_chapters", "final_consistent", "intra_repeat_chapters",
        "early_repeat", "opening_overload"}


def test_values_passthrough_and_coercion():
    v = signals.build_signal_vector(
        deliverable=1, grade="A", immersion_score=30, reenact_hits=2,
        seam_detected=19, seam_residual=4, dark_ratio=0.1,
        spine_num_contra=1, spine_id_contra=2, ft_revival_residual=1,
        too_short_chapters=3, final_consistent=0, intra_repeat_chapters=1)
    assert v["deliverable"] is True and v["final_consistent"] is False   # 强制 bool
    assert v["opening_immersion"] == 30 and v["seam_detected"] == 19
    assert v["spine_id_contra"] == 2 and v["ft_revival_residual"] == 1


def test_unbuilt_detectors_default_none():
    # 待建检测器(早段重复/开篇过载)先占位 None,建好再填——schema 前向稳定
    v = signals.build_signal_vector(
        deliverable=True, grade="A", immersion_score=90, reenact_hits=4,
        seam_detected=25, seam_residual=2, dark_ratio=0.0,
        spine_num_contra=0, spine_id_contra=0, ft_revival_residual=0,
        too_short_chapters=0, final_consistent=True, intra_repeat_chapters=0)
    assert v["early_repeat"] is None and v["opening_overload"] is None
    # 可显式填充
    v2 = signals.build_signal_vector(
        deliverable=True, grade="A", immersion_score=90, reenact_hits=4,
        seam_detected=25, seam_residual=2, dark_ratio=0.0,
        spine_num_contra=0, spine_id_contra=0, ft_revival_residual=0,
        too_short_chapters=0, final_consistent=True, intra_repeat_chapters=0,
        early_repeat=1, opening_overload=True)
    assert v2["early_repeat"] == 1 and v2["opening_overload"] is True
