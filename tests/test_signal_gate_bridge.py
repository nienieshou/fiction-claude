from hiki import gate, signals


def _clean_vector(**over):
    sv = signals.build_signal_vector(
        deliverable=True, grade="A", immersion_score=85, reenact_hits=4,
        seam_detected=13, seam_residual=1, dark_ratio=0.03,
        spine_num_contra=3, spine_id_contra=0, ft_revival_residual=0,
        too_short_chapters=0, final_consistent=True, intra_repeat_chapters=0)
    sv.update(over)
    return sv


def test_bridge_clean_vector_ships():
    gi = gate.signal_vector_to_gate_input(_clean_vector())
    assert gate.evaluate_ship_gate(gi) == []          # 干净本 → 无 ship_issue


def test_bridge_too_short_rejects():
    gi = gate.signal_vector_to_gate_input(_clean_vector(too_short_chapters=4))
    issues = gate.evaluate_ship_gate(gi)
    assert any("过短" in i for i in issues)


def test_bridge_revival_residual_rejects():
    gi = gate.signal_vector_to_gate_input(_clean_vector(ft_revival_residual=1))
    issues = gate.evaluate_ship_gate(gi)
    assert any("死人复活" in i for i in issues)


def test_bridge_seam_boundary_8_passes():
    # 残缝阈值 seam_residual_max=8，>8 才拦；=8 必须放
    gi = gate.signal_vector_to_gate_input(_clean_vector(seam_residual=8))
    assert not any("残缝" in i for i in gate.evaluate_ship_gate(gi))


def test_bridge_extra_injects_nonvector_field():
    gi = gate.signal_vector_to_gate_input(_clean_vector(), extra={"阵营串线": 2})
    assert any("阵营串线" in i for i in gate.evaluate_ship_gate(gi))
