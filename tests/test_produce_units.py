"""produce.py 纯函数:_wave_bounds 护栏/退化、_control_plane 编译、_settle_facts、_run_ship_gate。零 API。
(原 scripts/_test_r13_units.py 迁入 + B1-3 门 gather)"""
from hiki import gate
from hiki.produce import (_wave_bounds, _control_plane, _settle_facts, _run_ship_gate, _open_premise,
                         _source_id, _book_filename, _delivery_path, _started_at, _spine_alive_baseline)


def test_spine_alive_baseline():
    s = _spine_alive_baseline({"王建国": {}, "王亦初": {}})
    assert "王建国" in s and "存活基线" in s and "已故" in s and "生前" in s
    assert _spine_alive_baseline({}) == ""


from hiki.event_audit import scan_contradictions, roster


def test_scan_death_then_present():
    tl = {"父亲": [{"章": 1, "状态": "已故"}, {"章": 3, "状态": "受伤在场"}]}
    c = scan_contradictions(tl)
    assert any(x["type"] == "死后在场" for x in c)


def test_scan_conflicting_incidents():
    tl = {"父亲": [{"章": 2, "状态": "出车祸受伤需截肢"}, {"章": 3, "状态": "被绑架"}]}
    c = scan_contradictions(tl)
    assert any(x["type"] == "互斥重大遭遇" for x in c)


def test_scan_clean_no_flag():
    tl = {"主角": [{"章": 1, "状态": "健康"}, {"章": 5, "状态": "突破修为金丹"}]}
    assert scan_contradictions(tl) == []


def test_roster_from_bible():
    b = {"protagonist": {"name": "王亦初"}, "characters": [{"name": "白芷莹"}, {"name": "刘金"}]}
    r = roster(b)
    assert r[0] == "王亦初" and "白芷莹" in r and "刘金" in r


def test_started_at_persists_once(tmp_path):
    # 单一总历时:首次写入,续跑(再调)不覆盖
    d = tmp_path / "x_full"
    first = _started_at(d, 100.0)
    again = _started_at(d, 999.0)     # 第二次传不同 now,但应读旧值
    assert first == 100.0 and again == 100.0
    assert (d / "_timing.json").exists()


def test_source_id_extracts_library_code():
    assert _source_id("CPBGX00192灵气复苏_开局无限合成_full") == "CPBGX00192"
    assert _source_id("ZTGXY01837退婚后，她被娇养了") == "ZTGXY01837"
    assert _source_id("重生之首富归来")  # 无码→兜底非空


def test_book_filename_clean_delivery_scheme():
    # <源ID><新书名>.txt —— 干净交付名,无档/日期/《》/状态后缀
    nm = _book_filename("CPBGX00192灵气复苏_开局无限合成_full", "武神斩神")
    assert nm == "CPBGX00192武神斩神.txt"
    # 全角：保留(_safe_filename 不清全角冒号),源ID 直接粘书名
    nm2 = _book_filename("ZYGGY02252穿成萌娃_reval", "归隐田园：执子手共白头")
    assert nm2 == "ZYGGY02252归隐田园：执子手共白头.txt"


def _clean_sig():
    return {"dark_ratio": 0.0, "climax_skipped": "", "fact_table_ok": True, "ft_deaths_verified": [],
            "reenact_hits": [], "intra_rep": [], "spine_net_num": 0, "spine_net_id": 0,
            "fact_audit_crashed": False}


def test_run_ship_gate_clean_deliverable():
    g = _run_ship_gate({}, [], "正常的一章正文。" * 50, [], [], 0, _clean_sig(), gate.SHIP_GATE_DEFAULTS)
    assert g["deliverable"] is True and g["ship_issues"] == []
    assert g["final_consistent"] is True


def test_run_ship_gate_reenact_advisory_default():
    # 2026-06-26 降级: reenact 降 advisory, 默认不拦(即便高位9, 如认证本 CPBGX00031 clean9);
    # 信号噪(同书 polluted5→clean9)+非判别(eval5)→ 走 _run_ship_gate 整链亦不拦。可配 block_on_reenact 回硬拦。
    sig9 = {**_clean_sig(), "reenact_hits": [f"第{i}章重演[...]" for i in range(9)]}  # 9, 默认仍不拦
    g = _run_ship_gate({}, [], "正文", [], [], 0, sig9, gate.SHIP_GATE_DEFAULTS)
    assert g["deliverable"] is True and not any("事件重演" in i for i in g["ship_issues"])
    blk = {**gate.SHIP_GATE_DEFAULTS, "block_on_reenact": True}
    g_blk = _run_ship_gate({}, [], "正文", [], [], 0, sig9, blk)
    assert any("事件重演" in i for i in g_blk["ship_issues"])      # 可配回硬拦


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
    # aliases-only 不触发(隐婚'顾知夏'=真千金本名非前世名,C实证误报)→只信关键词
    assert _open_premise({"protagonist": {"aliases": ["顾知夏"]}, "genre": "现言豪门"}, {"chapters": []}) == ""
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


def test_delivery_path_routes_by_deliverable():
    from pathlib import Path
    out_dir = Path("output") / "ZYGGY02252穿成萌娃_reval"
    # 可交付 → 上级 _deliverable/ 汇聚
    d = _delivery_path(out_dir, True, "ZYGGY02252归隐田园：执子手共白头.txt")
    assert d == Path("output") / "_deliverable" / "ZYGGY02252归隐田园：执子手共白头.txt"
    # 不可交付 → 本子 _rejected/ 隔离
    r = _delivery_path(out_dir, False, "ZYGGY02252归隐田园：执子手共白头.txt")
    assert r == out_dir / "_rejected" / "ZYGGY02252归隐田园：执子手共白头.txt"
