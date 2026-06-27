"""cross_check 全分支语料钉(C1 CharacterStateLedger 等价基线)。零 API。"""
from hiki.prose_facts import cross_check


# ── 1. 生死 finding 完整结构 ────────────────────────────────────────────────
def test_death_conf_high_structure():
    """生死 finding 的全字段结构必须精确匹配 (cat/conf/who/ch_a/ch_b/why)。"""
    facts = [
        {"deaths": [{"who": "纪老夫人", "clue": "下葬三年"}]},
        {},
        {"present": ["纪老夫人"]},
    ]
    findings = cross_check(facts)
    deaths = [x for x in findings if x["cat"] == "生死"]
    assert len(deaths) == 1
    d = deaths[0]
    assert d["cat"] == "生死"
    assert d["conf"] == "高"
    assert d["who"] == "纪老夫人"
    assert d["ch_a"] == 1
    assert d["ch_b"] == 3
    assert "纪老夫人" in d["why"]
    assert "下葬" in d["why"]


# ── 2. 死亡无后续在场 → 不报 ─────────────────────────────────────────────────
def test_death_not_reported_if_no_later_presence():
    """death 记录有但随后无 present 章节 → 不产生生死 finding。"""
    facts = [{"deaths": [{"who": "张三", "clue": "死亡"}]}, {}, {}]
    findings = cross_check(facts)
    assert not [x for x in findings if x["cat"] == "生死"]


# ── 3. who 名字长度过滤 [2,6] ──────────────────────────────────────────────
def test_death_who_length_filter():
    """名字长度不在 [2,6] 字之间的 who 不追踪死亡事件。"""
    # 1 字 → 过短,不追踪
    facts_short = [
        {"deaths": [{"who": "我", "clue": "死"}]},
        {},
        {"present": ["我"]},
    ]
    assert not [x for x in cross_check(facts_short) if x["cat"] == "生死"]

    # 10 字 → 过长,不追踪
    facts_long = [
        {"deaths": [{"who": "名字超过六个字的人物", "clue": "死"}]},
        {},
        {"present": ["名字超过六个字的人物"]},
    ]
    assert not [x for x in cross_check(facts_long) if x["cat"] == "生死"]

    # 2 字 → 恰好合法,追踪并报告
    facts_valid = [
        {"deaths": [{"who": "叶离", "clue": "死"}]},
        {},
        {"present": ["叶离"]},
    ]
    assert len([x for x in cross_check(facts_valid) if x["cat"] == "生死"]) == 1


# ── 4. 数值只升不降 → 无倒退 finding ─────────────────────────────────────────
def test_power_regression_monotonic_no_finding():
    """气血值单调递增时不产生任何数值倒退(conf=中)finding。"""
    facts = [
        {"power": [["叶离", "气血100卡"]]},
        {"power": [["叶离", "气血150卡"]]},
        {"power": [["叶离", "气血200卡"]]},
    ]
    findings = cross_check(facts)
    regressions = [x for x in findings if x["cat"] == "数值" and x["conf"] == "中" and x["who"] == "叶离"]
    assert not regressions


# ── 5. 倒退阈值精确边界 >5% ──────────────────────────────────────────────────
def test_power_regression_threshold_exact():
    """条件是 v < hi*0.95(严格小于),95 不 < 95.0 故不报;94 < 95.0 故报。"""
    # 恰好 5% → 不报
    facts_borderline = [
        {"power": [["叶离", "气血100卡"]]},
        {"power": [["叶离", "气血95卡"]]},
    ]
    assert not [x for x in cross_check(facts_borderline) if x["cat"] == "数值" and x["conf"] == "中"]

    # 超过 5% → 报
    facts_over = [
        {"power": [["叶离", "气血100卡"]]},
        {"power": [["叶离", "气血94卡"]]},
    ]
    assert [x for x in cross_check(facts_over) if x["cat"] == "数值" and x["conf"] == "中"]


# ── 6. numbers 漂移 finding 完整结构 ─────────────────────────────────────────
def test_numbers_drift_low_conf_structure():
    """numbers 路径产生的数值 finding 必须是 conf=低,含 va/vb/who/cat/why。"""
    facts = [
        {"numbers": [["彩礼", "30万"]]},
        {"numbers": [["彩礼", "六十万"]]},
    ]
    findings = cross_check(facts)
    drifts = [x for x in findings if x["cat"] == "数值" and x["conf"] == "低"]
    assert len(drifts) >= 1
    d = drifts[0]
    assert d["cat"] == "数值"
    assert d["conf"] == "低"
    assert d["who"] == "彩礼"
    assert d.get("va")
    assert d.get("vb")
    assert "彩礼" in d["why"]


# ── 7. 语义可变量跳过 ─────────────────────────────────────────────────────────
def test_numbers_mutable_skip():
    """_MUTABLE 正则匹配的 key 即使数值不同也不报(语义上合法变动)。"""
    for key in ["余额", "存款", "合同", "报价"]:
        facts = [
            {"numbers": [[key, "1万"]]},
            {"numbers": [[key, "3千"]]},
        ]
        result = cross_check(facts)
        assert not [x for x in result if x["cat"] == "数值"], \
            f"可变量 '{key}' 不应产生数值 finding,但得到了 {result}"


# ── 8. 身份漂移 finding 完整结构 ─────────────────────────────────────────────
def test_identity_drift_full_structure():
    """identity 路径产生的身份 finding 必须含完整字段并且 va≠vb。"""
    facts = [
        {"identity": [["周柏森", "律师"]]},
        {"identity": [["周柏森", "人力总监"]]},
    ]
    findings = cross_check(facts)
    id_findings = [x for x in findings if x["cat"] == "身份"]
    assert len(id_findings) == 1
    d = id_findings[0]
    assert d["cat"] == "身份"
    assert d["conf"] == "低"
    assert d["who"] == "周柏森"
    assert d.get("va") in {"律师", "人力总监"}
    assert d.get("vb") in {"律师", "人力总监"}
    assert d["va"] != d["vb"]


# ── 9. numbers cap 2 条/实体 ─────────────────────────────────────────────────
def test_numbers_cap_2_per_entity():
    """同一实体的 numbers 漂移 finding 最多输出 2 条(C(5,2)=10 对也截断)。"""
    facts = [
        {"numbers": [["彩礼", "10万"]]},
        {"numbers": [["彩礼", "20万"]]},
        {"numbers": [["彩礼", "30万"]]},
        {"numbers": [["彩礼", "50万"]]},
        {"numbers": [["彩礼", "80万"]]},
    ]
    findings = cross_check(facts)
    num_findings = [x for x in findings if x["cat"] == "数值" and x["who"] == "彩礼" and x["conf"] == "低"]
    assert len(num_findings) == 2


# ── 10. identity cap 4 条/实体 ────────────────────────────────────────────────
def test_identity_cap_4_per_entity():
    """同一实体的 identity finding 最多输出 4 条(6 个不同值 C(6,2)=15 对也截断)。"""
    facts = [{"identity": [["安宁", v]]} for v in ["医生", "律师", "教师", "工程师", "护士", "设计师"]]
    findings = cross_check(facts)
    id_findings = [x for x in findings if x["cat"] == "身份" and x["who"] == "安宁"]
    assert len(id_findings) == 4
