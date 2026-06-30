"""修为 2 引擎迁移前行为钉死(C2)。零 API。迁移后必须逐位不变。

覆盖:
  check_power_monotonic — flags-descend, clean-ascend, issue 精确格式,
                          equal-rank-no-issue, unparseable-skip, alias-canonical
  fix_power_monotonic   — pins-back+mutates-scene, fixed 精确格式,
                          keeps-ascend-untouched, equal-rank-noop,
                          unparseable-passthrough, unparseable-does-not-reset-cur,
                          alias-preserves-input-name-in-mutation,
                          multi-char-scene, preserves-other-fields,
                          empty-scenes, malformed-pair-passthrough

cross_check power 数值回退分支已由 test_cross_check_corpus.py 充分覆盖
(test_power_regression_monotonic_no_finding / test_power_regression_threshold_exact)
及 test_prose_facts.py (test_cross_check_power_regression_conf_medium) — 不重复。
"""
from __future__ import annotations
from hiki.audit import check_power_monotonic, fix_power_monotonic


# ─── 共用夹具 ──────────────────────────────────────────────────────────────────

def _bible(ladder: str = "练气→筑基→金丹→元婴，赌注升级") -> dict:
    """≥3 级 → power_order_from_bible 返回本书梯(['练气','筑基','金丹','元婴'])。"""
    return {"power_system": ladder}


def _bible_with_alias() -> dict:
    """含别名 bible: 小叶 → 叶凡(验证 _alias_map 路径)。"""
    return {
        "power_system": "练气→筑基→金丹→元婴，赌注升级",
        "protagonist": {"name": "叶凡", "aliases": ["小叶"]},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# check_power_monotonic
# ═══════════════════════════════════════════════════════════════════════════════

def test_check_power_monotonic_flags_descend():
    """金丹→筑基 = 回退 → 1 条 issue，含角色名与'战力崩坏'。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "筑基"]]},
    ]
    issues = check_power_monotonic(_bible(), scenes)
    assert len(issues) == 1
    assert "叶凡" in issues[0]
    assert "战力崩坏" in issues[0]


def test_check_power_monotonic_issue_format_exact():
    """钉死 issue 字符串精确格式(含场景号/全角书名号/括号)。
    src/hiki/audit.py:299  f'场景{i}: 「{who}」修为回退到{pw}(战力崩坏)'"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "筑基"]]},
    ]
    issues = check_power_monotonic(_bible(), scenes)
    assert issues == ["场景1: 「叶凡」修为回退到筑基(战力崩坏)"]


def test_check_power_monotonic_clean_on_ascend():
    """练气→金丹 = 上升 → 无 issue。"""
    scenes = [
        {"power_after": [["叶凡", "练气"]]},
        {"power_after": [["叶凡", "金丹"]]},
    ]
    assert check_power_monotonic(_bible(), scenes) == []


def test_check_power_monotonic_equal_rank_no_issue():
    """同级重复出现不算回退(r < cur 是严格小于)。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "金丹"]]},
    ]
    assert check_power_monotonic(_bible(), scenes) == []


def test_check_power_monotonic_rank_unparseable_skip():
    """rank=-1(未识别境界) → 跳过该对, cur 不更新, 后续真实回退仍能被捕获。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "未知境界"]]},   # 不在梯中 → rank=-1 → 跳过
        {"power_after": [["叶凡", "筑基"]]},        # 低于金丹 → 仍报(cur 未被 '未知' 覆盖)
    ]
    issues = check_power_monotonic(_bible(), scenes)
    assert len(issues) == 1
    assert "叶凡" in issues[0]
    assert "战力崩坏" in issues[0]


def test_check_power_monotonic_alias_resolves_canonical_name():
    """别名 '小叶' 经 _alias_map → '叶凡'; issue 用 canonical 名。"""
    scenes = [
        {"power_after": [["小叶", "金丹"]]},
        {"power_after": [["小叶", "筑基"]]},
    ]
    issues = check_power_monotonic(_bible_with_alias(), scenes)
    assert len(issues) == 1
    assert "叶凡" in issues[0]          # canonical name in issue, not alias
    assert "战力崩坏" in issues[0]


def test_check_power_monotonic_default_ladder_when_bible_too_short():
    """bible 梯 <3 级 → power_order_from_bible 返回 None → 退默认 _POWER_ORDER, 仍能检测。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "筑基"]]},
    ]
    # 只有 2 级 → power_order_from_bible 返回 None
    issues = check_power_monotonic({"power_system": "练气→筑基，其他"}, scenes)
    assert len(issues) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# fix_power_monotonic — 核心: scene 就地 mutation
# ═══════════════════════════════════════════════════════════════════════════════

def test_fix_power_monotonic_pins_back_and_mutates_scene():
    """核心: 回退时返回 fixed 列表, 且就地改写 scenes[i]['power_after']。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "筑基"]]},
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert len(fixed) == 1
    assert "叶凡" in fixed[0]
    # scene 1 的 power_after 被钉回 金丹
    assert scenes[1]["power_after"] == [["叶凡", "金丹"]]
    # scene 0 不受影响
    assert scenes[0]["power_after"] == [["叶凡", "金丹"]]


def test_fix_power_monotonic_fixed_message_format_exact():
    """钉死 fixed 消息精确格式(无空格冒号/箭头格式)。
    src/hiki/audit.py:275  f'场景{i}:{who} {p}→{cs}'"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "筑基"]]},
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert fixed == ["场景1:叶凡 筑基→金丹"]


def test_fix_power_monotonic_keeps_ascend_untouched():
    """上升路径: 返回空列表, scene 不被改写。"""
    scenes = [
        {"power_after": [["叶凡", "练气"]]},
        {"power_after": [["叶凡", "金丹"]]},
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert fixed == []
    assert scenes[1]["power_after"] == [["叶凡", "金丹"]]


def test_fix_power_monotonic_equal_rank_not_treated_as_regression():
    """同级: r == cr, 不触发钉回(only r < cr 才算回退), scene 不变。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "金丹"]]},
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert fixed == []
    assert scenes[1]["power_after"] == [["叶凡", "金丹"]]


def test_fix_power_monotonic_rank_unparseable_passthrough():
    """rank=-1(未识别境界): pair 原样透传, cur 不更新, fixed 为空。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "未知境界"]]},   # rank=-1 → passthrough
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert fixed == []
    # 原 pair 透传,不被改写
    assert scenes[1]["power_after"] == [["叶凡", "未知境界"]]


def test_fix_power_monotonic_rank_unparseable_does_not_reset_cur():
    """rank=-1 pair 不更新 cur → 后续真实回退仍能被捕获(cur['叶凡'] 保持'金丹')。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [["叶凡", "未知境界"]]},   # rank=-1 → cur['叶凡'] 仍为 (金丹,2)
        {"power_after": [["叶凡", "筑基"]]},        # 低于金丹 → 仍触发钉回
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert len(fixed) == 1
    assert "叶凡" in fixed[0]
    assert scenes[2]["power_after"] == [["叶凡", "金丹"]]


def test_fix_power_monotonic_alias_preserves_input_name_in_mutation():
    """别名路径: alias 用于 cur 键(canonical'叶凡'), 但 scene mutation 保留原始输入名 sp[0]='小叶'。
    钉死 src/hiki/audit.py:274: new.append([sp[0], cs])  — sp[0] 非 who(canonical)。"""
    scenes = [
        {"power_after": [["小叶", "金丹"]]},    # alias '小叶' → canonical '叶凡'
        {"power_after": [["小叶", "筑基"]]},    # regression → 钉回
    ]
    fixed = fix_power_monotonic(_bible_with_alias(), scenes)
    assert len(fixed) == 1
    # fixed 消息用 canonical 名
    assert "叶凡" in fixed[0]
    # scene mutation 保留原始输入名 '小叶'(sp[0]), 非 canonical '叶凡'
    assert scenes[1]["power_after"] == [["小叶", "金丹"]]


def test_fix_power_monotonic_multi_char_independent_tracking():
    """多角色场景: 各自独立追踪, 不互相影响。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"], ["李梅", "练气"]]},
        {"power_after": [["叶凡", "筑基"], ["李梅", "元婴"]]},
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    # 叶凡回退 → 钉回金丹; 李梅上升 → 不改
    assert len(fixed) == 1
    assert "叶凡" in fixed[0]
    assert scenes[1]["power_after"] == [["叶凡", "金丹"], ["李梅", "元婴"]]


def test_fix_power_monotonic_preserves_other_scene_fields():
    """fix 只改写 power_after, scene 其他字段(location/event)不丢失。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]], "event": "突破"},
        {"power_after": [["叶凡", "筑基"]], "location": "大王村"},
    ]
    fix_power_monotonic(_bible(), scenes)
    assert scenes[1]["location"] == "大王村"    # 其他字段保留
    assert scenes[1]["power_after"] == [["叶凡", "金丹"]]
    assert scenes[0]["event"] == "突破"         # 场景0 也不受影响


def test_fix_power_monotonic_empty_scenes():
    """空场景列表: 返回空 fixed 列表, 不崩。"""
    assert fix_power_monotonic(_bible(), []) == []


def test_fix_power_monotonic_malformed_pair_passthrough():
    """_str_pair 返回 None 的异型对(3元组/字符串)原样透传, 不崩审计。"""
    scenes = [
        {"power_after": [["叶凡", "金丹"]]},
        {"power_after": [
            ["叶凡", "筑基", "extra_field"],  # 3元组 → _str_pair None → 透传
            "not_a_pair",                     # 字符串 → _str_pair None → 透传
        ]},
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    # 异型对不被解析, 故无 regression 检测, fixed 为空
    assert fixed == []
    # 异型对原样透传
    assert ["叶凡", "筑基", "extra_field"] in scenes[1]["power_after"]
    assert "not_a_pair" in scenes[1]["power_after"]


# ═══════════════════════════════════════════════════════════════════════════════
# 终审 I-1: equal-rank 不同字符串 — 钉回后出现者(C2 final-review fix)
# ═══════════════════════════════════════════════════════════════════════════════

def test_fix_power_monotonic_equal_rank_distinct_strings_pin_back():
    """I-1终审: 同rank但字符串不同 → 钉回必须是后出现的字符串。
    金丹初期/金丹大圆满 均含'金丹'子串 → _power_rank 返回同一 rank。
    旧 cur[who]=(r,p) 非回退时每次更新(含等rank);
    修复后 record best 条件 >= 复现此语义: 后出现的等rank串成为 best_raw。
    场景0:金丹初期 → 场景1:金丹大圆满(等rank,best_raw更新) → 场景2:练气(回退,钉回金丹大圆满)。"""
    scenes = [
        {"power_after": [["叶凡", "金丹初期"]]},
        {"power_after": [["叶凡", "金丹大圆满"]]},   # 同 rank, best_raw 应更新到此
        {"power_after": [["叶凡", "练气"]]},          # 真回退 → 钉回 金丹大圆满
    ]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert len(fixed) == 1
    # 钉回字符串必须是后出现的等rank串 金丹大圆满, 非首次的 金丹初期
    assert fixed == ["场景2:叶凡 练气→金丹大圆满"]
    assert scenes[2]["power_after"] == [["叶凡", "金丹大圆满"]]
    assert scenes[0]["power_after"] == [["叶凡", "金丹初期"]]   # 场景0 未被改写
    assert scenes[1]["power_after"] == [["叶凡", "金丹大圆满"]]  # 场景1 未被改写
