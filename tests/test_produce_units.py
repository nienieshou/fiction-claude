"""produce.py 纯函数:_wave_bounds 护栏/退化、_control_plane 编译、_settle_facts。零 API。
(原 scripts/_test_r13_units.py 迁入)"""
from hiki.produce import _wave_bounds, _control_plane, _settle_facts


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
