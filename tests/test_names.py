"""name 长度谓词单源(C5)。零 API。"""
from hiki.names import is_person_name, is_item_name


def test_is_person_name_bounds_max6():
    assert is_person_name("叶凡", 6) is True       # len2 下界
    assert is_person_name("欧阳上官修远", 6) is True  # len6 上界
    assert is_person_name("叶", 6) is False         # len1 < 下界
    assert is_person_name("欧阳上官修远长", 6) is False  # len7 > 上界


def test_is_person_name_bounds_max5_and_max4():
    assert is_person_name("欧阳娜娜", 5) is True    # len4 ≤ 5
    assert is_person_name("欧阳上官修", 5) is True   # len5 上界
    assert is_person_name("欧阳上官修远", 5) is False  # len6 > 5
    assert is_person_name("司马懿", 4) is True       # len3 ≤ 4
    assert is_person_name("欧阳上官修", 4) is False   # len5 > 4


def test_is_item_name_bounds():
    assert is_item_name("玉佩") is True             # len2 下界
    assert is_item_name("天雷血玉珠混元伞") is True   # len8 上界
    assert is_item_name("刀") is False              # len1 < 下界
    assert is_item_name("天雷血玉珠混元伞甲") is False  # len9 > 上界
