"""Characterization tests: prose_continuity 3 个人名长度判定站点 (C5 迁移守卫)。

钉死现状行为, 迁移后须不变:
- _variant_scan: 2-4 字长度锚 (反相门: 非 2-4 跳过)
- len=2/len=4 正常产 pair; len=5 被门排除
"""
from hiki.prose_continuity import _variant_scan


# ───────── _variant_scan: 反相锚谓词 ─────────

def test_variant_scan_len2_anchor_finds_variant():
    """2字高频名作为锚, 发现1字之差的罕见变体 → 返回 pair."""
    counts = {"嬴墨": 50, "赢墨": 2}
    full = "嬴墨出场。" * 50 + "赢墨来了。赢墨再来。"
    pairs = _variant_scan(counts, full, floor=10)
    assert ("赢墨", "嬴墨") in pairs


def test_variant_scan_len4_anchor_finds_variant():
    """4字名(上界)作为锚, 正常扫描 → 返回 pair."""
    counts = {"司马修远": 50, "司马修遠": 2}
    full = "司马修远出场。" * 50 + "司马修遠来了。司马修遠再来。"
    pairs = _variant_scan(counts, full, floor=10)
    assert ("司马修遠", "司马修远") in pairs


def test_variant_scan_len5_anchor_skipped():
    """5字锚被反相门排除 (not (2<=len<=4)) → 不产 pair."""
    counts = {"欧阳娜娜丽": 50, "欧阳娜娜美": 2}
    full = "欧阳娜娜丽出场。" * 50 + "欧阳娜娜美来了。欧阳娜娜美再来。"
    pairs = _variant_scan(counts, full, floor=10)
    # len=5 锚被门跳过 → 无法产生 pair
    assert ("欧阳娜娜美", "欧阳娜娜丽") not in pairs


def test_variant_scan_low_freq_anchor_skipped():
    """cc < floor 的名不作锚 (cc<floor 门)."""
    counts = {"嬴墨": 5, "赢墨": 1}   # 5 < floor=10 → skip
    full = "嬴墨出场。" * 5 + "赢墨来了。"
    pairs = _variant_scan(counts, full, floor=10)
    assert ("赢墨", "嬴墨") not in pairs


def test_variant_scan_empty_counts():
    """空 counts → 空 pairs."""
    assert _variant_scan({}, "", floor=10) == set()
