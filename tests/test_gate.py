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


def test_reenact_advisory_by_default():
    # 2026-06-26 降级: reenact 信号噪(同书 polluted5→clean9)+非判别(eval5 最可追本含最多重演)
    # +会误拦认证本(CPBGX00031 clean9)→ 默认 advisory 不拦(同 climax/final 家族); 可配 block_on_reenact 回硬拦。
    assert gate.evaluate_ship_gate({"事件重演": 9}, D) == []            # 默认不拦, 即便高位
    blk = {**D, "block_on_reenact": True}
    assert len(gate.evaluate_ship_gate({"事件重演": 7}, blk)) == 1      # 可配回硬拦(reenact_min=7)
    assert gate.evaluate_ship_gate({"事件重演": 6}, blk) == []          # 配回后仍 6<7 不拦


def test_spine_net_min_6_human_calibrated():
    # human-eval-5: 可追本含4条spine矛盾→不拦;阈值6留头寸
    assert gate.evaluate_ship_gate({"数值真矛盾": 4, "身份真矛盾": 1}, D) == []      # 5<6
    assert len(gate.evaluate_ship_gate({"数值真矛盾": 3, "身份真矛盾": 3}, D)) == 1  # 合计6


def test_climax_skip_advisory_by_default():
    # human-eval-5: 预告跳过仅命中可追本(星厨)→默认 advisory 不拦
    assert gate.evaluate_ship_gate({"预告跳过": "十五号攻打封独"}, D) == []
    blk = {**D, "block_on_climax_skip": True}
    assert len(gate.evaluate_ship_gate({"预告跳过": "x"}, blk)) == 1  # 可配回硬拦


def test_death_authority_fact_table_over_plan_dim14():
    assert gate.evaluate_ship_gate({"plan维14复活": 2, "事实表跑过": True}, D) == []
    assert len(gate.evaluate_ship_gate({"plan维14复活": 2, "事实表跑过": False}, D)) == 1


def test_final_consistent_advisory_by_default():
    # human-eval-5: final_consistent=否 反相关(只命中可追本)→默认 advisory 不拦
    assert gate.evaluate_ship_gate({}, D) == []
    assert gate.evaluate_ship_gate({"final_consistent": False}, D) == []
    blk = {**D, "block_on_final_inconsistent": True}
    assert len(gate.evaluate_ship_gate({"final_consistent": False}, blk)) == 1  # 可配回硬拦


def test_audit_crash_blocks():
    assert len(gate.evaluate_ship_gate({"承重审计崩溃": True}, D)) == 1


def test_opening_immersion_floor_gate():
    # editor-eval-2(2026-06-22): 买来 代入感30→人承重40(最低档,"第二章重复了")该拦;
    # 其余 9 本代入感≥65→人承重≥50 安全。<40 = 读者无法代入的灾难地板,best-of-N 重掷救济。
    assert gate.evaluate_ship_gate({}, D) == []                          # signal 缺失→默认不拦
    assert gate.evaluate_ship_gate({"开篇代入感": None}, D) == []          # 审计解析失败→不拦
    assert gate.evaluate_ship_gate({"开篇代入感": 40}, D) == []            # =40 不拦(< 才拦)
    assert gate.evaluate_ship_gate({"开篇代入感": 65}, D) == []            # 安全本
    assert len(gate.evaluate_ship_gate({"开篇代入感": 39}, D)) == 1        # <40 拦
    assert len(gate.evaluate_ship_gate({"开篇代入感": 30}, D)) == 1        # 买来电平 拦
    blk = {**D, "opening_immersion_min": 0}
    assert gate.evaluate_ship_gate({"开篇代入感": 30}, blk) == []          # 可配回关闭(min=0)


def test_config_thresholds_override():
    loose = {**D, "spine_net_min": 5}
    assert gate.evaluate_ship_gate({"数值真矛盾": 2, "身份真矛盾": 2}, loose) == []   # 4<5
    strict = {**D, "seam_residual_max": 0}
    assert len(gate.evaluate_ship_gate({"残缝": 1}, strict)) == 1


def test_multi_signal_accumulates():
    # 默认真正会拦的电平: 过短3✓ 残缝9✓ spine6✓ 审计崩溃✓(重演已降 advisory 默认不拦)
    issues = gate.evaluate_ship_gate(
        {"过短章数": 3, "残缝": 9, "数值真矛盾": 3, "身份真矛盾": 3,
         "承重审计崩溃": True}, D)
    assert len(issues) == 4


def test_human_calibrated_advisory_levels_pass():
    # human-eval-5 的 5 本在重标后,其承重微观电平不再硬拦(降 advisory):
    # 隐婚 重演6/spine3/final否 · 团宠 重演4/spine4/final否 · 星厨 重演3/spine3/预告跳过
    # + CPBGX00031 clean 重演9(认证本,2026-06-26 reenact 降级实证): 高位重演亦不拦
    for sig in ({"事件重演": 6, "数值真矛盾": 3, "final_consistent": False},
                {"事件重演": 4, "数值真矛盾": 4, "final_consistent": False},
                {"事件重演": 3, "身份真矛盾": 3, "预告跳过": "x"},
                {"事件重演": 9}):
        assert gate.evaluate_ship_gate(sig, D) == []


def test_early_repeat_caps_immersion():
    # CPBGX00031: detector 误给 opening_immersion=90,但 ch1/ch2 同一"许安初访"重述。
    # early_repeat>0 → 封顶到 cap(30) → 触发 opening_immersion_min(40)硬门。
    assert gate.evaluate_ship_gate({"开篇代入感": 90}, D) == []                  # 无早段重复→90 安全
    assert len(gate.evaluate_ship_gate({"开篇代入感": 90, "早段重复": 1}, D)) == 1  # 有→封顶30→拦
    assert gate.evaluate_ship_gate({"开篇代入感": 90, "早段重复": 0}, D) == []     # =0 不封顶
    # 封顶值高于 min 时不拦(cap 可配)
    loose = {**D, "early_repeat_immersion_cap": 50}
    assert gate.evaluate_ship_gate({"开篇代入感": 90, "早段重复": 2}, loose) == []  # 封顶50≥40
    # 早段重复但 immersion 缺失/None → 不崩、不拦(保守)
    assert gate.evaluate_ship_gate({"早段重复": 1}, D) == []
    assert gate.evaluate_ship_gate({"开篇代入感": None, "早段重复": 1}, D) == []
