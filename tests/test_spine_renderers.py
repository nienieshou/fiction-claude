"""Fact Spine 注入渲染器 characterization(Phase1:为 C3 身份钉死统一/B1 拆 run 钉死当前行为)。零 API。
覆盖 _spine_map/_spine_block/_spine_facts/_spine_roster/_spine_world/_pin_block。"""
from hiki.produce import (_spine_map, _spine_block, _spine_facts, _spine_roster,
                          _spine_world, _pin_block)


def test_pin_block_empty_and_render():
    assert _pin_block("标签", [], "规则") == ""
    out = _pin_block("标签", ["a", "b"], "规则", cap=10)
    assert out.startswith("\n标签: ") and "a；b" in out and "铁律: 规则" in out


def test_pin_block_caps_rows():
    out = _pin_block("X", [f"r{i}" for i in range(20)], "规则", cap=3)
    assert "r0；r1；r2" in out and "r3" not in out


def test_spine_map_from_characters_and_protagonist():
    bible = {"characters": [{"name": "顾明骁", "role": "顾家大少", "aliases": ["大少爷"],
                             "key_relation": "安宁同父异母兄长"}],
             "protagonist": {"name": "安宁", "identity": "设计师", "aliases": []}}
    sm = _spine_map(bible)
    assert sm["顾明骁"]["role"] == "顾家大少" and "大少爷" in sm["顾明骁"]["aliases"]
    assert sm["安宁"]["rel"] == "主角" and sm["安宁"]["role"] == "设计师"


def test_spine_block_only_appearing_chars_with_alias_ban():
    sm = {"顾明骁": {"role": "顾家大少", "aliases": ["大少爷"], "rel": "兄长"},
          "陆擎泽": {"role": "总裁", "aliases": [], "rel": "丈夫"}}
    cur = {"key_events": ["顾明骁现身"], "scenes": [{"brief": "顾明骁来访"}]}
    out = _spine_block(cur, sm)
    assert "顾明骁" in out and "禁用异名:大少爷" in out
    assert "陆擎泽" not in out                          # 本章未点名→不注入
    assert "角色名钉死" in out and "铁律" in out


def test_spine_facts_freezes_values():
    out = _spine_facts({"facts": [{"item": "彩礼", "value": "15万"},
                                  {"item": "军衔", "value": "排长→团长", "rule": "单调↑"}]})
    assert "数值钉死" in out and "彩礼=15万" in out and "军衔=排长→团长〔单调↑〕" in out
    assert _spine_facts({}) == ""


def test_spine_roster_identity_table():
    out = _spine_roster({"顾明骁": {"role": "顾家大少", "rel": "兄长", "aliases": []}})
    assert out.startswith("\n角色身份钉死") and "顾明骁=顾家大少" in out
    assert "另起新名" in out                            # rule③ 防自造名复用


def test_spine_world_modern_vs_cultivation():
    modern = _spine_world({"places": [{"name": "云城"}], "factions": [{"name": "陆氏"}],
                           "power_system": "无"})
    assert "地点钉死" in modern and "云城" in modern and "战力/体系钉死" not in modern
    cult = _spine_world({"places": [{"name": "霖洲"}], "power_system": "炼气→筑基→金丹→元婴→化神"})
    assert "战力/体系钉死" in cult and "炼气" in cult


def test_spine_world_genre_gate_robust():
    # #6: 体系门用前缀+长度,不靠两个魔法字面值;'无明确战力体系'应被挡
    assert "战力/体系钉死" not in _spine_world({"power_system": "无明确战力体系，以商战为主"})
    assert "战力/体系钉死" not in _spine_world({"power_system": "现实世界"})
