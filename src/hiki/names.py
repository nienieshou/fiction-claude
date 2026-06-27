"""人名/物品名长度谓词单源(C5)。纯, 零依赖。

收口散落 7 处的 `2 <= len(name) <= N` 判定。谓词只做长度;调用方保留各自的
isinstance/strip/truthiness 前检与后置条件(确保行为逐位等价)。
各站点显式传 max_len(现状 4/5/6 人名 / 8 物品)——界统一(修 provenance 缺口)留 follow-up。
"""
from __future__ import annotations


def is_person_name(nm: str, max_len: int) -> bool:
    """人名长度谓词。nm 须为已 str 化字符串。下界 2(最短中文名),上界 max_len。"""
    return 2 <= len(nm) <= max_len


def is_item_name(nm: str) -> bool:
    """物品/法器名谓词(可较长的复合名, 如 '天雷血玉珠')。界 2-8。"""
    return 2 <= len(nm) <= 8
