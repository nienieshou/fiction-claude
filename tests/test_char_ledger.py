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
