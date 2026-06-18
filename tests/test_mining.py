"""mining.py 纯函数:生死弧聚合。零 API。"""
from hiki.mining import collect_life_events


def test_collect_life_events_arc():
    # 窗序=时间序:死@w0 + 复活@w1(后窗) → dies_returns;只死 → dies_final
    cr = [
        {"life_events": [{"who": "桑念", "type": "死亡", "quote": "长剑刺进心口"}]},
        {"life_events": [{"who": "桑念", "type": "复活", "quote": "我又活过来了"}]},
        {"life_events": [{"who": "袁麟", "type": "死亡", "quote": "红缨枪结果了性命"}]},
    ]
    arcs = collect_life_events(cr)
    assert arcs["桑念"]["fate"] == "dies_returns"
    assert arcs["袁麟"]["fate"] == "dies_final"
    assert "心口" in arcs["桑念"]["death_q"]


def test_collect_life_events_ignores_revive_only_and_empty():
    # 只复活无死亡 → 不建弧(噪声);无 life_events → 空
    cr = [{"life_events": [{"who": "甲", "type": "复活", "quote": "x"}]},
          {"scene_cards": []}]
    assert collect_life_events(cr) == {}
