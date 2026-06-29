"""C7 余切: prose_facts.revival_candidates 纯函数(生死→复活候选, 单源)。零 API。"""
from hiki import prose_facts


def _f(cat="生死", who="张三", ch_a=2, ch_b=5, why="死了"):
    return {"cat": cat, "who": who, "ch_a": ch_a, "ch_b": ch_b, "why": why}


def test_basic_revival_candidate():
    out = prose_facts.revival_candidates([_f()], 10)
    assert out == [{"who": "张三", "clue": "死了", "revive_ch": 4, "death_ch": 1}]


def test_non_revival_cats_excluded():
    out = prose_facts.revival_candidates([_f(cat="数值"), _f(cat="身份"), _f(cat="体系")], 10)
    assert out == []


def test_ch_b_out_of_bounds_or_non_int_excluded():
    assert prose_facts.revival_candidates([_f(ch_b=0)], 10) == []     # <1
    assert prose_facts.revival_candidates([_f(ch_b=11)], 10) == []    # >n_ch
    assert prose_facts.revival_candidates([_f(ch_b="x")], 10) == []   # 非 int(短路不崩)


def test_ch_a_non_int_yields_death_ch_none():
    out = prose_facts.revival_candidates([_f(ch_a=None)], 10)
    assert out[0]["death_ch"] is None
    assert out[0]["revive_ch"] == 4                                   # revive_ch 仍算


def test_clue_truncated_and_missing_why_empty():
    out = prose_facts.revival_candidates([_f(why="x" * 50)], 10)
    assert out[0]["clue"] == "x" * 30                                 # why[:30]
    f2 = _f()
    del f2["why"]
    assert prose_facts.revival_candidates([f2], 10)[0]["clue"] == ""  # 缺 why → ""


def test_ch_b_at_bounds_included():
    assert prose_facts.revival_candidates([_f(ch_b=1)], 10)[0]["revive_ch"] == 0    # 下界
    assert prose_facts.revival_candidates([_f(ch_b=10)], 10)[0]["revive_ch"] == 9   # 上界
