"""ledger.py characterization(Phase1:此前 0% 覆盖,为 C1 死亡账统一重构钉死当前行为)。零 API。"""
from hiki import ledger


def test_validate_timeline_duplicate_event():
    scenes = [{"event_id": "E1"}, {"event_id": "E1"}]
    issues = ledger.validate_timeline(scenes)
    assert any("事件重复" in i and "E1" in i for i in issues)


def test_validate_timeline_duplicate_first_appearance():
    scenes = [{"first_appearances": ["甲"]}, {"first_appearances": ["甲"]}]
    issues = ledger.validate_timeline(scenes)
    assert any("重复初次登场" in i and "甲" in i for i in issues)


def test_validate_timeline_duplicate_relationship():
    scenes = [{"relationships_formed": [["甲", "乙"]]}, {"relationships_formed": [["乙", "甲"]]}]
    issues = ledger.validate_timeline(scenes)
    assert any("重复初遇" in i or "重复结识" in i for i in issues)


def test_dedup_first_meetings_mutates_and_counts():
    scenes = [{"first_appearances": ["甲", "乙"]}, {"first_appearances": ["甲"]}]
    removed = ledger.dedup_first_meetings(scenes)
    assert removed == 1
    assert scenes[1]["first_appearances"] == []        # 后场景的重复"甲"被清掉


def test_state_before_accumulates():
    scenes = [
        {"first_appearances": ["甲"], "deaths": ["乙"], "power_after": [["甲", "金丹"]],
         "event_id": "E1", "time_marker": "三日后"},
        {"first_appearances": ["丙"]},
    ]
    snap = ledger.state_before(scenes, 2)
    assert "甲" in snap["appeared"] and "丙" in snap["appeared"]
    assert "乙" in snap["dead"]
    assert snap["power"]["甲"] == "金丹"
    assert "E1" in snap["events"] and snap["time"] == "三日后"


def test_state_before_excludes_idx_onward():
    scenes = [{"first_appearances": ["甲"]}, {"first_appearances": ["乙"]}]
    snap = ledger.state_before(scenes, 1)               # 只含 scenes[:1]
    assert "甲" in snap["appeared"] and "乙" not in snap["appeared"]


def test_format_context_renders_accounts():
    snap = {"appeared": ["甲"], "relationships": ["甲↔乙"], "events": ["E1"],
            "dead": ["丙"], "power": {"甲": "金丹"}, "time": "三日后"}
    s = ledger.format_context(snap)
    assert "已死亡" in s and "丙" in s
    assert "当前修为" in s and "甲=金丹" in s
    assert "已发生事件" in s


def test_format_context_empty_when_no_events():
    assert ledger.format_context({"appeared": [], "relationships": [], "events": [],
                                  "dead": [], "power": {}, "time": ""}) == "（本场景为开篇，无前情）"


def test_check_foreshadow_orphan_payoff():
    scenes = [{"foreshadow_payoff": ["神秘玉佩的来历揭晓"]}]   # 全书无对应 plant
    issues = ledger.check_foreshadow(scenes)
    assert any("无铺垫" in i or "孤儿" in i for i in issues)
