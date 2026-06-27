"""textnum 单源 characterization(C4)。零 API。"""
import re
from hiki import textnum


def test_cn_to_num_compounds():
    assert textnum.cn_to_num("四十") == 40
    assert textnum.cn_to_num("二十三") == 23
    assert textnum.cn_to_num("三十万") == 300000
    assert textnum.cn_to_num("一万八千") == 18000
    assert textnum.cn_to_num("十五") == 15
    assert textnum.cn_to_num("无数字") is None


def test_num_of_arabic_unit_magnitude():
    assert textnum.num_of("30万") == textnum.num_of("三十万") == 300000
    assert textnum.num_of("15万") == textnum.num_of("十五万") == 150000
    assert textnum.num_of("失散17年") == 17
    assert textnum.num_of("四十分钟") == 40


def test_source_ch_re_includes_volume():
    # C4 修复: 源章正则必须认「卷」(mining/slice 旧版漏卷的分叉)
    assert textnum.SOURCE_CH_RE.search("第一卷 序章")
    assert textnum.SOURCE_CH_RE.search("第3章 风云")
    assert textnum.SOURCE_CH_RE.search("第十回 ")


def test_md_ch_re_splits_generated():
    parts = textnum.MD_CH_RE.split("# 《书》\n\n# 第1章 x\n正文a\n\n# 第2章 y\n正文b")
    assert len([p for p in parts[1:]]) == 2


def test_ch_num_and_inline_extract():
    assert textnum.CH_NUM_RE.search("#  第 3 章").group(1) == "3"
    assert textnum.INLINE_CH_NUM_RE.search("第31章:死人复活").group(1) == "31"
