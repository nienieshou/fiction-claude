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


# ==================== A3: LLM 输出契约校验 ====================
def validate(raw, required, types: dict | None = None) -> bool:
    """轻量契约校验: raw 是 dict 且 required 键全在 + (可选)类型匹配。"""
    if not isinstance(raw, dict):
        return False
    for k in required:
        if k not in raw:
            return False
    for k, t in (types or {}).items():
        if k in raw and not isinstance(raw[k], t):
            return False
    return True


# 标杆 schema(键取自现状契约)
REVIVAL_VERIFY = {"required": ("is_revival",), "types": {"is_revival": bool}}
EXTRACT_CHUNK = {"required": (), "types": {"scene_cards": list}}   # 数据契约: 任意解析成功的 dict 有效(partial 保数据); scene_cards 若在须为 list(防 null 崩); 仅 None/非dict=解析失败→重试浮现
