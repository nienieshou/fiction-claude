"""B1 wave2: run() 清晰块外提的纯 helper 单测(零 API)。"""
from hiki import produce


def test_collect_valid_names_splits_dedups_and_filters():
    p = {"name": "张三/张三丰", "aliases": ["老张、小张"]}
    bible = {"characters": [{"name": " 李四 ", "aliases": ["四爷", 123, ""]}]}
    assert produce._collect_valid_names(p, bible) == {"张三", "张三丰", "老张", "小张", "李四", "四爷"}


def test_collect_valid_names_empty_inputs():
    assert produce._collect_valid_names({}, {}) == set()


def test_intra_repeat_short_text_returns_zero():
    assert produce._intra_repeat("甲" * 799) == 0.0          # <800 字短路


def test_intra_repeat_identical_halves_high():
    half = "甲乙丙丁戊己庚辛壬癸" * 50                          # 500 字
    assert produce._intra_repeat(half + half) > 0.5           # 两半同 → 高重合


def test_intra_repeat_distinct_halves_zero():
    a = "甲乙丙丁戊己庚辛壬癸" * 50
    b = "子丑寅卯辰巳午未申酉" * 50
    assert produce._intra_repeat(a + b) == 0.0                # 两半无共 12-gram


def test_detect_intra_repeats_filters_by_threshold():
    half = "甲乙丙丁戊己庚辛壬癸" * 50
    clean = "甲乙丙丁戊己庚辛壬癸" * 50 + "子丑寅卯辰巳午未申酉" * 50
    out = produce._detect_intra_repeats([clean, half + half], 0.08)
    assert [i for i, _ in out] == [1]                          # 仅第2章超阈
    assert out[0][1] > 0.08
