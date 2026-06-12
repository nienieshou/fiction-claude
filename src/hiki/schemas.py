"""数据契约（A6 阶段间契约=schema）。所有阶段读写这些结构。"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class IngestMeta:
    """P0 Ingest 产物元数据。"""
    source_path: str
    encoding: str
    raw_chars: int
    clean_chars: int
    approx_wan_zi: float
    chapter_count: int
    removed_junk_lines: int
    garbage_chars: int
    short_chapters: int
    suspected_splice: bool
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


@dataclass
class ChapterSummary:
    """逐章摘要 + 结构标签（Extract 产出；结构指标 metrics 的输入）。

    数据自洽要求：这些标签须忠实反映正文（摘要↔正文一致性校验，防刷分）。
    """
    index: int                       # 输出章号 1..60
    volume: int                      # 卷号
    char_count: int
    payoffs: list[str] = field(default_factory=list)        # 爽点
    hooks: list[str] = field(default_factory=list)          # 悬念/钩子
    ability_unlocks: list[str] = field(default_factory=list)  # 金手指能力解锁
    foreshadow_plants: list[str] = field(default_factory=list)
    foreshadow_payoffs: list[str] = field(default_factory=list)
    event_density: float = 0.0       # 0-1，本章有效事件密度

    @property
    def is_water(self) -> bool:
        """水段：事件/爽点/钩子三低。"""
        return self.event_density < 0.3 and not self.payoffs and not self.hooks
