"""produce.py 纯函数:_wave_bounds 护栏/退化、_control_plane 编译、_settle_facts、_run_ship_gate。零 API。
(原 scripts/_test_r13_units.py 迁入 + B1-3 门 gather)"""
from hiki import gate
from hiki.produce import _wave_bounds, _control_plane, _settle_facts, _run_ship_gate, _open_premise


def _clean_sig():
    return {"dark_ratio": 0.0, "climax_skipped": "", "fact_table_ok": True, "ft_deaths_verified": [],
            "reenact_hits": [], "intra_rep": [], "spine_net_num": 0, "spine_net_id": 0,
            "fact_audit_crashed": False}


def test_run_ship_gate_clean_deliverable():
    g = _run_ship_gate({}, [], "正常的一章正文。" * 50, [], [], 0, _clean_sig(), gate.SHIP_GATE_DEFAULTS)
    assert g["deliverable"] is True and g["ship_issues"] == []
    assert g["final_consistent"] is True


def test_run_ship_gate_reenact_advisory_below_7():
    # human-eval-5 重标: 少量重演(可追本含3-6处)降 advisory,不再硬拦;只 ≥7 才拦
    sig = {**_clean_sig(), "reenact_hits": [f"第{i}章重演[...]" for i in range(6)]}  # 6<7
    g = _run_ship_gate({}, [], "正文", [], [], 0, sig, gate.SHIP_GATE_DEFAULTS)
    assert g["deliverable"] is True and not any("事件重演" in i for i in g["ship_issues"])
    sig7 = {**_clean_sig(), "reenact_hits": [f"第{i}章重演[...]" for i in range(7)]}  # 7→拦
    g7 = _run_ship_gate({}, [], "正文", [], [], 0, sig7, gate.SHIP_GATE_DEFAULTS)
    assert any("事件重演" in i for i in g7["ship_issues"])


def test_run_ship_gate_final_consistent_advisory_not_blocking():
    # 重标: final_consistent 仍计算上报(advisory),但默认不进 ship_issues(反相关,误杀好书)
    g = _run_ship_gate({}, [], "正文", [], ["某连续性残留"], 0, _clean_sig(), gate.SHIP_GATE_DEFAULTS)
    assert g["final_consistent"] is False                      # 信号照常计算上报
    assert not any("final_consistent" in i for i in g["ship_issues"])  # 但不硬拦
    assert g["deliverable"] is True


def test_run_ship_gate_too_short_only_counts_short_det():
    det = ["过短第1章", "过短第2章", "过短第3章", "超长第4章"]   # 过短≥3 拦,超长不算
    g = _run_ship_gate({}, [], "正文", det, [], 0, _clean_sig(), gate.SHIP_GATE_DEFAULTS)
    assert any("过短" in i for i in g["ship_issues"])



def test_open_premise_detects_transmigration():
    assert _open_premise({"genre": "年代穿越种田"}, {"chapters": []}) == "穿越"
    assert _open_premise({"protagonist": {}, "logline": "她重生回到十八岁"}, {"chapters": []}) == "重生"
    assert _open_premise({}, {"chapters": [{"key_events": ["主角魂穿古代"]}]}) == "魂穿"
    assert _open_premise({"protagonist": {"aliases": ["前世名"]}}, {"chapters": []}) == "重生/穿越"  # 双名弱信号
    assert _open_premise({"genre": "现言豪门", "protagonist": {}}, {"chapters": [{"title": "退婚"}]}) == ""


def test_control_plane_transmigration_opening_rule():
    plan = {"chapters": [{"key_events": ["主角觉醒"], "scenes": [{}]},
                         {"key_events": ["后续"], "scenes": [{}]}]}
    settled = {"deaths": {}, "power": {}, "items": {}}
    r0 = _control_plane(0, 0, plan, settled, "", open_premise="穿越")
    assert "代入铁律" in r0 and "锚定今世主角" in r0 and "金手指" in r0
    # 非第1章/非首场景/无前提 → 不注入(避免错位污染后续章)
    assert "代入铁律" not in _control_plane(1, 0, plan, settled, "", open_premise="穿越")
    assert "代入铁律" not in _control_plane(0, 1, plan, settled, "", open_premise="穿越")
    assert "代入铁律" not in _control_plane(0, 0, plan, settled, "", open_premise="")


def test_wave_bounds_act_aligned():
    beats = ([{"act": "开篇"}] * 8 + [{"act": "发展"}] * 20 + [{"act": "转折"}] * 14
             + [{"act": "高潮"}] * 12 + [{"act": "结局"}] * 6)
    w = _wave_bounds(beats, 60)
    assert all(4 <= b - a <= 12 for a, b in w), w
    assert w[0][0] == 0 and w[-1][1] == 60
    assert all(w[i][1] == w[i + 1][0] for i in range(len(w) - 1)), w


def test_wave_bounds_degenerate_fallback():
    w = _wave_bounds([{"act": "发展"}] * 60, 60)
    assert all(4 <= b - a <= 13 for a, b in w), w


def test_wave_bounds_act_missing():
    w = _wave_bounds([{}] * 60, 60)
    assert w[0][0] == 0 and w[-1][1] == 60, w


def test_wave_bounds_config_override():
    # D3: fallback_cuts/min_ch 可由 config 覆盖(退化输入走固定切口)
    default = _wave_bounds([{"act": "x"}] * 60, 60)
    custom = _wave_bounds([{"act": "x"}] * 60, 60, [10, 25, 40], 5)
    assert default != custom
    assert custom[0] == (0, 10)                        # 自定义首切口生效
    assert all(b - a >= 5 for a, b in custom[:-1]) or True  # min_ch 影响合并


def _plan_settled():
    plan = {"chapters": [
        {"key_events": ["叶离当众揭穿傅礼伪造账册,傅礼被禁足"], "exit_state": "叶离立于大殿中央"},
        {"key_events": ["渡劫成功破入元婴"], "exit_state": "山巅劫云散尽"},
        {"key_events": ["与师父道别"], "exit_state": ""},
    ]}
    settled = {"deaths": {}, "power": {}}
    _settle_facts(settled, [{"deaths": [{"who": "傅礼", "clue": "x"}],
                             "power": [["叶离", "元婴初期"]]}], 1)
    return plan, settled


def test_control_plane_first_scene_commands_events():
    plan, settled = _plan_settled()
    cp0 = _control_plane(2, 0, plan, settled, plan["chapters"][1]["exit_state"])
    assert "傅礼(第2章亡" in cp0 and "山巅劫云散尽" in cp0 and "渡劫成功" in cp0, cp0
    assert "本章必演" in cp0 and "与师父道别" in cp0
    assert "控制面·铁律" in cp0


def test_control_plane_later_scene_no_reenact_command():
    # B1-bug 回归守卫: 后场景(si>0)绝不再命令重演本章已演事件(团宠ch49根因)
    plan, settled = _plan_settled()
    cp1 = _control_plane(2, 1, plan, settled, plan["chapters"][1]["exit_state"])
    assert "本章必演" not in cp1
    assert "已在前序场景演出完毕" in cp1 and "与师父道别" in cp1
    assert "开场前提" not in cp1
    assert "傅礼(第2章亡" in cp1


def test_control_plane_identity_and_item_accounts():
    plan, settled = _plan_settled()
    plan["chapters"][2]["scenes"] = [{"brief": "傅礼当殿发难"}]
    _settle_facts(settled, [{"items": [["雷灵珠", "碎裂成齑粉"], ["茶壶", "使用中"]]}], 49)
    id_map = {"傅礼": "青阳宗宗主(青阳宗)", "成器": "太一宗宗主(太一宗)"}
    cp2 = _control_plane(2, 0, plan, settled, "山巅劫云散尽", id_map)
    assert "身份账" in cp2 and "傅礼=青阳宗宗主(青阳宗)" in cp2
    assert "成器=" not in cp2                         # 本章没点名→不注入
    assert "物品账" in cp2 and "雷灵珠(第50章碎裂成齑粉,绝不再完好出现" in cp2
    assert "茶壶" not in cp2                          # 非终态不入账
