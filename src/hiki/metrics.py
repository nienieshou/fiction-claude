"""5 个可量化结构指标（PRD §6，0-LLM 确定性，从逐章摘要计算）。

raw 量客观；0-100 score 为 **pre-calibration 占位**——正式曲线须按题材用
40 本标杆(90)+金标(95)校准（A5/§7），切勿硬编码当真值。
"""
from __future__ import annotations
from dataclasses import dataclass
from .schemas import ChapterSummary


@dataclass
class StructuralMetrics:
    payoff_mean_gap: float       # 平均爽点间隔（章）
    payoff_max_gap: int          # 最大憋屈跨度（章）— 弃书杀手
    hook_mean_gap: float
    unlock_chapters: list[int]   # 金手指解锁章号（条件指标）
    volume_balance_cv: float     # 各卷章数变异系数（越小越均衡）
    water_ratio: float           # 水段占比
    foreshadow_closure: float    # 伏笔闭环率 0-1
    ending_rush: float           # 末段仓促度 0-1（越大越仓促）


def _gaps(flags: list[bool]) -> tuple[float, int]:
    """相邻 True 间隔的均值与最大值（含首尾到边界）。"""
    idx = [i for i, f in enumerate(flags) if f]
    if not idx:
        return float(len(flags)), len(flags)
    points = [-1] + idx + [len(flags)]
    gaps = [points[i + 1] - points[i] for i in range(len(points) - 1)]
    return round(sum(gaps) / len(gaps), 2), max(gaps)


def compute(chapters: list[ChapterSummary]) -> StructuralMetrics:
    n = len(chapters)
    payoff_mean, payoff_max = _gaps([bool(c.payoffs) for c in chapters])
    hook_mean, _ = _gaps([bool(c.hooks) for c in chapters])
    unlocks = [c.index for c in chapters if c.ability_unlocks]

    # 卷章数均衡：变异系数 std/mean
    vols: dict[int, int] = {}
    for c in chapters:
        vols[c.volume] = vols.get(c.volume, 0) + 1
    counts = list(vols.values())
    mean = sum(counts) / len(counts) if counts else 0
    var = sum((x - mean) ** 2 for x in counts) / len(counts) if counts else 0
    cv = round((var ** 0.5 / mean), 3) if mean else 0.0

    water = round(sum(1 for c in chapters if c.is_water) / n, 3) if n else 0.0

    plants = sum(len(c.foreshadow_plants) for c in chapters)
    payoffs = sum(len(c.foreshadow_payoffs) for c in chapters)
    closure = round(min(1.0, payoffs / plants), 3) if plants else 1.0

    # 仓促度：末 10% 章的伏笔回收占比 vs 其章数占比，超出越多越仓促
    tail = max(1, n // 10)
    tail_payoffs = sum(len(c.foreshadow_payoffs) for c in chapters[-tail:])
    rush = 0.0
    if payoffs:
        rush = round(max(0.0, (tail_payoffs / payoffs) - (tail / n)), 3)

    return StructuralMetrics(
        payoff_mean_gap=payoff_mean, payoff_max_gap=payoff_max,
        hook_mean_gap=hook_mean, unlock_chapters=unlocks,
        volume_balance_cv=cv, water_ratio=water,
        foreshadow_closure=closure, ending_rush=rush,
    )
