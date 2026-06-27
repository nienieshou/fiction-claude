"""prose_facts 纯函数 characterization(Phase1:钉死当前行为,供后续重构证等价)。零 API。
覆盖 split_chapters/verify_finding(原 _test_prose_facts)+ cross_check 四类 + _cn_to_num/_num_of。"""
from hiki.prose_facts import (split_chapters, verify_finding, cross_check,
                              _cn_to_num, _num_of)


# ---------- split_chapters / verify_finding(原迁入)----------
def test_split_chapters_drops_preamble():
    chs = split_chapters("# 《书》\n\n# 第1章 x\n纪老夫人喝了参汤。\n\n# 第2章 y\n纪老夫人已经下葬三年。")
    assert len(chs) == 2


def test_verify_finding_quote_grounding():
    chs = split_chapters("# 《书》\n\n# 第1章 x\n纪老夫人喝了参汤。\n\n# 第2章 y\n纪老夫人已经下葬三年。")
    f = {"cat": "生死", "ch_a": 1, "quote_a": "纪老夫人喝了参汤",
         "ch_b": 2, "quote_b": "纪老夫人已经下葬三年"}
    assert verify_finding(f, chs)
    assert not verify_finding(dict(f, quote_b="没出现过的引文内容啊"), chs)


# ---------- 中文数字解析(#1 修复 + 已知 bug 史)----------
def test_cn_to_num_compounds():
    assert _cn_to_num("四十") == 40            # 治"四十被读成4"
    assert _cn_to_num("二十三") == 23
    assert _cn_to_num("三十万") == 300000
    assert _cn_to_num("一万八千") == 18000
    assert _cn_to_num("十五") == 15
    assert _cn_to_num("无数字") is None


def test_num_of_arabic_unit_magnitude():
    # #1: '30万' 经量纲提升,与 '三十万' 一致
    assert _num_of("30万") == _num_of("三十万") == 300000
    assert _num_of("15万") == _num_of("十五万") == 150000
    assert _num_of("失散17年") == 17
    assert _num_of("四十分钟") == 40


# ---------- cross_check 四类 characterization ----------
def test_cross_check_death_then_present():
    facts = [{"deaths": [{"who": "纪老夫人", "clue": "下葬"}]}, {}, {"present": ["纪老夫人"]}]
    f = cross_check(facts)
    deaths = [x for x in f if x["cat"] == "生死"]
    assert len(deaths) == 1 and deaths[0]["who"] == "纪老夫人" and deaths[0]["conf"] == "高"


def test_cross_check_number_real_vs_synonym_vs_mutable():
    # 真漂移(彩礼 30万 vs 60万)报;30万==三十万 不报(#1);可变量(余额)不报
    assert [x for x in cross_check([{"numbers": [["彩礼", "30万"]]},
                                    {"numbers": [["彩礼", "六十万"]]}]) if x["cat"] == "数值"]
    assert not [x for x in cross_check([{"numbers": [["彩礼", "30万"]]},
                                        {"numbers": [["彩礼", "三十万"]]}]) if x["cat"] == "数值"]
    assert not [x for x in cross_check([{"numbers": [["银行卡余额", "1万"]]},
                                        {"numbers": [["银行卡余额", "3千"]]}]) if x["cat"] == "数值"]


def test_cross_check_power_regression_conf_medium():
    facts = [{"power": [["叶离", "气血100卡"]]}, {"power": [["叶离", "气血50卡"]]}]
    f = [x for x in cross_check(facts) if x["cat"] == "数值" and x["conf"] == "中"]
    assert f and "倒退" in f[0]["why"]


def test_cross_check_identity_multivalue_low_conf():
    facts = [{"identity": [["周柏森", "律师"]]}, {"identity": [["周柏森", "人力总监"]]}]
    f = [x for x in cross_check(facts) if x["cat"] == "身份"]
    assert f and f[0]["conf"] == "低" and f[0].get("va") and f[0].get("vb")


def test_cross_check_identity_substring_not_reported():
    # 互为子串=同义写法,不报
    assert not [x for x in cross_check([{"identity": [["陆擎泽", "总裁"]]},
                                        {"identity": [["陆擎泽", "帝景总裁"]]}]) if x["cat"] == "身份"]


def test_cross_check_per_entity_cap_by_cat():
    # #5: 同名实体的数值 findings 不被身份 findings 吃光(cap 键含 cat)
    facts = [{"identity": [["安宁", v]]} for v in ["设计师", "护工", "学生", "老师", "医生"]]
    facts += [{"numbers": [["安宁", "22岁"]]}, {"numbers": [["安宁", "24岁"]]}]
    f = cross_check(facts)
    assert [x for x in f if x["cat"] == "数值" and x["who"] == "安宁"]


# ---------- 终审 I-2: 同章降序重复不报(复现旧掩盖, byte-identical) ----------

def test_cross_check_intra_chapter_descending_dup_yields_no_finding():
    """I-2终审: 同章降序(100→50)不报 — 旧 per-bucket (ch,v) sort 升序处理, 掩盖惯量下降。
    新实现须在章内按解析值升序处理,复现此掩盖语义(byte-identical 承诺)。"""
    facts = [{"power": [["X", "气血100卡"], ["X", "气血50卡"]]}]  # 同章, 降序
    findings = cross_check(facts)
    power_f = [f for f in findings if f.get("cat") == "数值" and f.get("who") == "X"]
    assert power_f == []  # 旧行为: 升序处理 → 50先进, 100为新高, 无回退


def test_cross_check_cross_chapter_drop_still_finds():
    """I-2 sanity: 真跨章回退(ch1=100, ch2=50, >5%跌)仍报 — I-2修复不改跨章检测。"""
    facts = [
        {"power": [["X", "气血100卡"]]},
        {"power": [["X", "气血50卡"]]},   # 跨章: 50 < 100*0.95=95 → 报
    ]
    findings = cross_check(facts)
    power_f = [f for f in findings if f.get("cat") == "数值" and f.get("who") == "X"]
    assert len(power_f) == 1
    assert "倒退" in power_f[0]["why"]
