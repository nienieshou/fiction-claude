"""PowerLedger + 比较器纯函数 characterization(C2)。零 API/audit/prose 依赖。"""
from hiki.char_ledger import PowerLedger, ordinal_comparator, numeric_comparator


# 序数: 简单 rank_fn 注入(模拟 _power_rank, -1→None)
_RANK = {"练气": 1, "筑基": 2, "金丹": 3, "元婴": 4}
def _rank_fn(raw):
    r = _RANK.get(raw, -1)
    return float(r) if r >= 0 else None


def test_ordinal_no_regression_on_ascend():
    lg = PowerLedger(ordinal_comparator(_rank_fn))
    assert lg.record("叶凡", "练气", 1) is False
    assert lg.record("叶凡", "金丹", 2) is False     # 升


def test_ordinal_regression_on_descend():
    lg = PowerLedger(ordinal_comparator(_rank_fn))
    lg.record("叶凡", "金丹", 1)
    assert lg.record("叶凡", "筑基", 2) is True       # 金丹(3)→筑基(2) 退
    regs = lg.regressions()
    assert len(regs) == 1 and regs[0].who == "叶凡" and regs[0].raw_value == "筑基"
    assert regs[0].best_raw == "金丹" and regs[0].mode == "ordinal"


def test_ordinal_unparseable_skipped():
    lg = PowerLedger(ordinal_comparator(_rank_fn))
    lg.record("叶凡", "金丹", 1)
    assert lg.record("叶凡", "无法识别的境界", 2) is False   # parse None → 跳过, 不报不更新
    assert lg.current_best("叶凡") == "金丹"


def test_ordinal_current_best_tracks_max():
    lg = PowerLedger(ordinal_comparator(_rank_fn))
    lg.record("叶凡", "练气", 1)
    lg.record("叶凡", "元婴", 2)
    lg.record("叶凡", "筑基", 3)                       # 退, best 不变
    assert lg.current_best("叶凡") == "元婴"


# 数值: value_fn + unit_fn 注入
def _value_fn(raw):
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(m.group(1)) if m else None
def _unit_fn(raw):
    import re
    return re.sub(r"(\d+(?:\.\d+)?)", "#", raw).strip()


def test_numeric_5pct_threshold_boundary():
    lg = PowerLedger(numeric_comparator(_value_fn, _unit_fn))
    lg.record("叶凡", "气血100卡", 1)
    assert lg.record("叶凡", "气血95卡", 2) is False    # 100→95 恰 95%, 不算退(<95*0.95? 95<95.0 False)
    assert lg.record("叶凡", "气血94卡", 3) is True     # 94 < 100*0.95=95.0 → 退


def test_numeric_keyed_by_unit():
    lg = PowerLedger(numeric_comparator(_value_fn, _unit_fn))
    lg.record("叶凡", "气血100卡", 1)
    assert lg.record("叶凡", "灵力10级", 2) is False    # 不同 unit, 独立桶, 不比


# 终审 I-1: equal-rank 不同字符串 — >= 更新让 best_raw 升到后出现者
def test_ordinal_equal_rank_distinct_strings_updates_best_raw():
    """C2终审I-1: 同rank不同字符串 → >= 条件使 best_raw 更新到后出现字符串。
    旧 cur[who]=(r,p) 每次非回退都更新; 修复后 record 在 v>=best[0] 时更新 best_raw。"""
    # A_low 与 A_high 映射到相同 rank=1.0; B=0.0 更低(触发回退)
    _RANK2 = {"A_low": 1, "A_high": 1, "B": 0}
    def _rank2(raw):
        r = _RANK2.get(raw, -1)
        return float(r) if r >= 0 else None

    lg = PowerLedger(ordinal_comparator(_rank2))
    assert lg.record("X", "A_low", 1) is False     # 首次, 无回退
    assert lg.record("X", "A_high", 2) is False    # 同 rank, 无回退; best_raw 应更新到 A_high
    assert lg.current_best("X") == "A_high"        # >= 条件: 后出现的等rank串成为 best_raw
    regressed = lg.record("X", "B", 3)
    assert regressed is True
    regs = lg.regressions()
    assert len(regs) == 1
    assert regs[0].best_raw == "A_high"            # 钉回目标是后出现的等rank串, 非 A_low
