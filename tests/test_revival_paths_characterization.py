"""P1 check_revival / P3 find_revivals 迁移前行为钉死(C1)。零 API。
迁移到 RevivalLedger 后这些断言必须逐位不变 = 等价证明。

实际行为（读源码确认）:
  check_revival  → list[str], 每条格式: "场景{i}: 「{who}」已在场景{j}死亡/退场，却再次出场(死人复活)"
                   "在场"来源: first_appearances / power_after[0] / entourage[0] / relationships_formed双端
                   在场检查在死亡登记之前 → 同场景 first_appearances+deaths 不算复活
  find_revivals  → list[dict], 每条键: who / clue / death_win / revive_ch
                   阈值 count(who, ch_text) >= 2; ch(1-based)有值→after=ch, 无→after=(win+1)*win
                   每人只报首个满足章(break after first); 同名多死只取第一条(seen dedup)
"""
from hiki.audit import check_revival
from hiki.prose_continuity import find_revivals


# ============ P1: check_revival ============

def test_check_revival_detects_via_first_appearances():
    """死亡后通过 first_appearances 再出场 → 检出1条 issue。"""
    scenes = [
        {"deaths": ["纪老夫人"]},
        {},
        {"first_appearances": ["纪老夫人"]},
    ]
    issues = check_revival(scenes)
    assert len(issues) == 1
    assert "纪老夫人" in issues[0]
    assert "死人复活" in issues[0]


def test_check_revival_issue_string_exact_format():
    """issue 字符串精确格式: '场景{i}: 「{who}」已在场景{j}死亡/退场，却再次出场(死人复活)'。"""
    scenes = [
        {"deaths": ["张三"]},
        {"first_appearances": ["张三"]},
    ]
    issues = check_revival(scenes)
    assert issues == ["场景1: 「张三」已在场景0死亡/退场，却再次出场(死人复活)"]


def test_check_revival_clean_when_no_reappearance():
    """死亡人物未再出场，其他人出场 → 空列表。"""
    scenes = [{"deaths": ["张三"]}, {"first_appearances": ["李四"]}]
    assert check_revival(scenes) == []


def test_check_revival_empty_scenes():
    """空场景列表 → 空列表。"""
    assert check_revival([]) == []


def test_check_revival_detects_via_power_after():
    """死亡后通过 power_after 对的第一元素再出场 → 检出。"""
    scenes = [
        {"deaths": ["王五"]},
        {"power_after": [["王五", "宗师"]]},
    ]
    issues = check_revival(scenes)
    assert len(issues) == 1
    assert "王五" in issues[0]
    assert "死人复活" in issues[0]


def test_check_revival_detects_via_entourage():
    """死亡后通过 entourage 对的第一元素再出场 → 检出。"""
    scenes = [
        {"deaths": ["赵六"]},
        {"entourage": [["赵六", "护卫"]]},
    ]
    issues = check_revival(scenes)
    assert len(issues) == 1
    assert "赵六" in issues[0]
    assert "死人复活" in issues[0]


def test_check_revival_detects_via_relationships_formed():
    """死亡后通过 relationships_formed 对中任一人名再出场 → 检出。"""
    scenes = [
        {"deaths": ["钱七"]},
        {"relationships_formed": [["钱七", "孙八"]]},
    ]
    issues = check_revival(scenes)
    assert len(issues) == 1
    assert "钱七" in issues[0]
    assert "死人复活" in issues[0]


def test_check_revival_same_scene_not_flagged():
    """同场景 first_appearances 与 deaths 含同一人 → 不算复活
    (在场检查在死亡登记之前: 尚未死就不在 dead 表里)。"""
    scenes = [
        {"deaths": ["林九"], "first_appearances": ["林九"]},
    ]
    assert check_revival(scenes) == []


def test_check_revival_multiple_deaths_multiple_revivals():
    """两人先后死亡并在同一场景各自复活 → 各一条 issue。"""
    scenes = [
        {"deaths": ["甲"]},
        {"deaths": ["乙"]},
        {"first_appearances": ["甲", "乙"]},
    ]
    issues = check_revival(scenes)
    assert len(issues) == 2
    names = {iss.split("「")[1].split("」")[0] for iss in issues}
    assert names == {"甲", "乙"}


def test_check_revival_strips_whitespace_in_names():
    """deaths/first_appearances 里带前后空格的名字 → strip 后仍能匹配检出。"""
    scenes = [
        {"deaths": [" 周十 "]},
        {"first_appearances": ["周十"]},
    ]
    issues = check_revival(scenes)
    assert len(issues) == 1
    assert "周十" in issues[0]


# ============ P3: find_revivals ============

def _roster(deaths: list[dict], win: int = 8) -> dict:
    """组装 roster dict 供 find_revivals 使用（仅含函数实际访问的键）。"""
    return {"win": win, "deaths": deaths, "persons": set(), "n_win": 1}


def test_find_revivals_detects_count_ge_2():
    """死亡后某章出现 >=2 次 → 候选复活（brief 原始例，ch=1 1-based）。"""
    roster = _roster([{"who": "王五", "clue": "坠崖", "ch": 1, "win": 0}], win=1)
    ch_texts = ["王五坠崖。", "无关内容。", "王五回来了, 王五还活着。"]
    revs = find_revivals(roster, ch_texts)
    assert any(r["who"] == "王五" for r in revs)


def test_find_revivals_output_keys():
    """输出 dict 必须含且仅含 who / clue / death_win / revive_ch 四键。"""
    roster = _roster([{"who": "甲", "clue": "中毒身亡", "ch": 1, "win": 0}], win=1)
    ch_texts = ["甲中毒身亡。", "甲归来了，甲站在门口。"]
    revs = find_revivals(roster, ch_texts)
    assert len(revs) == 1
    assert set(revs[0].keys()) == {"who", "clue", "death_win", "revive_ch"}


def test_find_revivals_revive_ch_and_death_win_values():
    """revive_ch = 0-based 章索引；death_win = deaths[*].win 字段原值。"""
    roster = _roster([{"who": "乙", "clue": "被杀", "ch": 2, "win": 0}], win=8)
    ch_texts = [".", "乙被杀。", "乙出现，乙说话。"]
    revs = find_revivals(roster, ch_texts)
    assert len(revs) == 1
    assert revs[0]["revive_ch"] == 2
    assert revs[0]["death_win"] == 0


def test_find_revivals_below_threshold_not_detected():
    """某章只出现 1 次 → 不触发（阈值 >=2，严格计数）。"""
    roster = _roster([{"who": "丙", "clue": "溺水", "ch": 1, "win": 0}], win=1)
    ch_texts = ["丙溺水。", "丙出现了。"]   # ch_texts[1]: count("丙")=1
    revs = find_revivals(roster, ch_texts)
    assert revs == []


def test_find_revivals_ch_none_uses_window_fallback():
    """death.ch=None → after=(win_idx+1)*win，从下一窗起查（治已知边界条件）。"""
    win = 3
    roster = _roster([{"who": "丁", "clue": "消失", "ch": None, "win": 0}], win=win)
    # after = (0+1)*3 = 3; index<3 的章即使满足也不算（窗内）
    ch_texts = [
        "丁消失。",          # index 0
        "丁丁出现。",        # index 1 (count=2 but before after=3 → 不查)
        "无关。",            # index 2
        "丁归来，丁活着。",  # index 3 ≥ after → 检出
        "其他。",
    ]
    revs = find_revivals(roster, ch_texts)
    assert len(revs) == 1
    assert revs[0]["revive_ch"] == 3


def test_find_revivals_deduplication_same_person_two_death_entries():
    """同一人物在 deaths 里出现两次 → seen 去重，只上报一次。"""
    roster = _roster([
        {"who": "戊", "clue": "第一次", "ch": 1, "win": 0},
        {"who": "戊", "clue": "第二次", "ch": 2, "win": 0},
    ], win=8)
    ch_texts = ["戊死。", "戊再死。", "戊戊戊归来了。"]
    revs = find_revivals(roster, ch_texts)
    whos = [r["who"] for r in revs if r["who"] == "戊"]
    assert len(whos) == 1


def test_find_revivals_no_match_returns_empty():
    """死亡后各章均不满足 >=2 → 返回空列表。"""
    roster = _roster([{"who": "己", "clue": "牺牲", "ch": 1, "win": 0}], win=1)
    ch_texts = ["己牺牲。", "无人知晓。", "故事结束。"]
    revs = find_revivals(roster, ch_texts)
    assert revs == []


def test_find_revivals_first_qualifying_chapter_reported():
    """两章均满足 >=2，只上报最早那章（break after first match）。"""
    roster = _roster([{"who": "庚", "clue": "死战", "ch": 1, "win": 1}], win=1)
    ch_texts = ["庚死战。", "庚出现，庚说话。", "庚再次，庚再次。"]
    revs = find_revivals(roster, ch_texts)
    assert len(revs) == 1
    assert revs[0]["revive_ch"] == 1   # 首个满足的章 (index 1)


def test_find_revivals_clue_preserved_in_output():
    """输出的 clue 字段原样保留死亡条目中的值。"""
    roster = _roster([{"who": "辛", "clue": "被火烧死", "ch": 1, "win": 0}], win=1)
    ch_texts = ["辛被火烧死。", "辛归来，辛说话。"]
    revs = find_revivals(roster, ch_texts)
    assert len(revs) == 1
    assert revs[0]["clue"] == "被火烧死"


# ============ P1 multi-death byte-identity lock (Fix 1 / I1) ============

def test_check_revival_multi_death_cites_latest_death_before_reappearance():
    """P1 锁定: 同一人死两次(场景0和2), 再现在场景1和3 →
    场景1再现引用最近死亡=场景0; 场景3再现引用最近死亡=场景2。
    验证 post_death_appearances() 修复后 issue 字符串与旧 dead[who]=i 覆写语义逐位对齐。"""
    scenes = [
        {"deaths": ["人物甲"]},               # 场景0: 第一次死亡
        {"first_appearances": ["人物甲"]},    # 场景1: 再出场 (死后)
        {"deaths": ["人物甲"]},               # 场景2: 第二次死亡
        {"first_appearances": ["人物甲"]},    # 场景3: 再出场 (死后)
    ]
    issues = check_revival(scenes)
    assert issues == [
        "场景1: 「人物甲」已在场景0死亡/退场，却再次出场(死人复活)",
        "场景3: 「人物甲」已在场景2死亡/退场，却再次出场(死人复活)",
    ]


# ============ P3 dedup edge — ACCEPTED DEVIATION ============

def test_find_revivals_p3_dedup_first_entry_miss_second_skipped():
    """P3 dedup 边缘(已接受偏差): 首条死亡 ch=None → after=(win+1)*win=8, 无章 index≥8;
    次条死亡 ch=2 → after=2, ch[2] 满足 count≥2。post-migration: 首条 first_meta dedup 后次条被跳过 → []。
    ACCEPTED DEVIATION: 迁移前 seen 仅在命中时更新, 次条可补命中; P3 仅叙事修复, 零门影响。"""
    win = 8
    roster = {
        "win": win,
        "deaths": [
            {"who": "壬", "clue": "消失", "ch": None, "win": 0},  # after=(0+1)*8=8; 无 ch≥8
            {"who": "壬", "clue": "死亡", "ch": 2, "win": 0},     # after=2; ch[2] count≥2, 但被 dedup 跳过
        ],
        "persons": set(),
        "n_win": 1,
    }
    # 只有5章(索引0-4), 无章 index≥8; ch[2]="壬壬壬归来了" count≥2 但首条 death after=8 遮蔽
    ch_texts = ["壬在第一章。", "壬消失了。", "壬壬壬归来了。", "其他。", "其他。"]
    revs = find_revivals(roster, ch_texts)
    # post-migration: 首条 None-ch 占位 first_meta, after=8 无章命中; 次条被跳过 → 无复活
    assert revs == []  # ACCEPTED DEVIATION from pre-migration (see prose_continuity.py dedup guard comment)
