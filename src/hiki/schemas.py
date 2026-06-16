"""数据契约（A6）。当前仅 Ingest 阶段用 IngestMeta;其余阶段仍走裸 dict(见 tech-debt A3:LLM 输出未 schema 化)。"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
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
