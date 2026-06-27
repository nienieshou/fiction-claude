"""RevivalLedger 纯函数 characterization(C1)。零 API。"""
from hiki.char_ledger import RevivalLedger, RevivalRecord


def test_death_then_later_appearance_is_revival():
    lg = RevivalLedger()
    lg.record_death("纪老夫人", 15, clue="火化", source="facts")
    lg.record_appearance("纪老夫人", 47, source="facts")
    revs = lg.revivals()
    assert len(revs) == 1
    r = revs[0]
    assert r.who == "纪老夫人" and r.death_ch == 15 and r.revive_ch == 47
    assert r.clue == "火化" and "facts" in r.sources


def test_appearance_before_death_not_revival():
    lg = RevivalLedger()
    lg.record_appearance("张三", 3, source="facts")
    lg.record_death("张三", 10, clue="", source="facts")
    assert lg.revivals() == []


def test_earliest_death_earliest_later_appearance():
    lg = RevivalLedger()
    lg.record_death("李四", 20, clue="坠崖", source="facts")
    lg.record_appearance("李四", 25, source="facts")
    lg.record_appearance("李四", 30, source="facts")
    r = lg.revivals()[0]
    assert r.death_ch == 20 and r.revive_ch == 25   # 死后最早出场


def test_multi_source_merges_sources():
    lg = RevivalLedger()
    lg.record_death("王五", 10, clue="病故", source="facts")
    lg.record_appearance("王五", 12, source="facts")
    lg.record_death("王五", 10, clue="", source="plan")
    lg.record_appearance("王五", 12, source="plan")
    revs = lg.revivals()
    assert len(revs) == 1
    assert revs[0].sources == frozenset({"facts", "plan"})


def test_resolve_gating_source_precedence():
    # facts 权威进门; 仅 roster 来源不进门(仅修复)
    facts_rev = RevivalRecord("A", 5, 8, "", frozenset({"facts"}), "高")
    roster_only = RevivalRecord("B", 5, 8, "", frozenset({"roster"}), "高")
    plan_only = RevivalRecord("C", 5, 8, "", frozenset({"plan"}), "高")
    lg = RevivalLedger()
    gated = lg.resolve_gating([facts_rev, roster_only, plan_only])
    whos = {r.who for r in gated}
    assert "A" in whos          # facts 权威
    assert "B" not in whos      # 仅 roster = 仅修复, 不进门
    assert "C" in whos          # plan 回退也算门级来源


def test_clue_uses_first_death_even_if_empty():
    """首个死亡 clue 为空时, 即便后续死亡有 clue, revivals 应取首个(空)。严格对齐旧 cross_check。"""
    lg = RevivalLedger()
    lg.record_death("赵六", 5, clue="", source="facts")          # 首死 clue 为空
    lg.record_death("赵六", 8, clue="明确线索", source="facts")   # 后死 clue 非空
    lg.record_appearance("赵六", 15, source="facts")
    r = lg.revivals()[0]
    assert r.clue == ""    # 首死 clue 为空, 严格取首死 — 即便后死有非空 clue


def test_revivals_ordered_by_death_ch_not_alpha():
    """两条复活按 death_ch 升序输出(非按角色名字母序)。"""
    lg = RevivalLedger()
    # "A_char" 字母序靠前, 但死于 ch=20; "Z_char" 字母序靠后, 死于 ch=3
    lg.record_death("A_char", 20, clue="", source="facts")
    lg.record_appearance("A_char", 25, source="facts")
    lg.record_death("Z_char", 3, clue="", source="facts")
    lg.record_appearance("Z_char", 10, source="facts")
    revs = lg.revivals()
    assert len(revs) == 2
    assert revs[0].who == "Z_char" and revs[0].death_ch == 3    # 早死先出, 虽字母序靠后
    assert revs[1].who == "A_char" and revs[1].death_ch == 20


# ============ post_death_appearances ============

def test_post_death_appearances_single():
    """一个 who 死后出场一次 → 返回一条 (who, death_ch, appearance_ch)。"""
    lg = RevivalLedger()
    lg.record_death("张三", 5, source="plan")
    lg.record_appearance("张三", 8, source="plan")
    result = lg.post_death_appearances()
    assert result == [("张三", 5, 8)]


def test_post_death_appearances_multiple_for_same_who():
    """同一 who 死后出场多次 → 每次各出一条, 按 appearance_ch 排序。"""
    lg = RevivalLedger()
    lg.record_death("李四", 2, source="plan")
    lg.record_appearance("李四", 5, source="plan")
    lg.record_appearance("李四", 9, source="plan")
    lg.record_appearance("李四", 7, source="plan")
    result = lg.post_death_appearances()
    assert len(result) == 3
    # 按 appearance_ch 升序
    assert [t[2] for t in result] == [5, 7, 9]
    assert all(t[0] == "李四" and t[1] == 2 for t in result)


def test_post_death_appearances_same_scene_not_included():
    """出场场景 == 最早死亡场景 → 不算死后出场。"""
    lg = RevivalLedger()
    lg.record_death("王五", 3, source="plan")
    lg.record_appearance("王五", 3, source="plan")  # 同场景, 不算
    result = lg.post_death_appearances()
    assert result == []


def test_post_death_appearances_uses_earliest_death():
    """同一 who 两次死亡, 以最早 death_ch 为基准。"""
    lg = RevivalLedger()
    lg.record_death("赵六", 10, source="plan")
    lg.record_death("赵六", 3, source="plan")   # 更早的死亡
    lg.record_appearance("赵六", 5, source="plan")   # 在 ch=3 死后, ch=10 前 → 应算入
    result = lg.post_death_appearances()
    assert len(result) == 1
    assert result[0] == ("赵六", 3, 5)


def test_post_death_appearances_ordered_by_appearance_then_who():
    """多人在同一 appearance_ch 出场 → 按 who 字母升序作 tiebreak。"""
    lg = RevivalLedger()
    lg.record_death("乙", 1, source="plan")
    lg.record_death("甲", 1, source="plan")
    lg.record_appearance("乙", 5, source="plan")
    lg.record_appearance("甲", 5, source="plan")
    result = lg.post_death_appearances()
    assert len(result) == 2
    # 同一 appearance_ch=5, 按 who 升序: "乙" vs "甲" (字符排序)
    whos = [t[0] for t in result]
    assert whos == sorted(whos)
