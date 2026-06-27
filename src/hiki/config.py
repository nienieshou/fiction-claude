"""配置加载（A6 配置驱动）。优先 config/*.yaml，缺 PyYAML 时回退内置默认。"""
from __future__ import annotations
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]   # claude/
_CONFIG_DIR = _ROOT / "config"

_DEFAULTS: dict[str, Any] = {
    "output": {"target_chapters": 60, "chars_per_chapter": 3500},
    "budget": {"per_book_cny_cap": 50.0},
    # ship_gate 阈值不在此手抄(曾 stale 过): 规范源唯一为 gate.SHIP_GATE_DEFAULTS,
    # 运营覆盖在 config/pipeline.yaml。无 yaml 时消费点 .get("ship_gate") or gate.SHIP_GATE_DEFAULTS 自动落规范源。
    "production": {                              # 量产结构/成本旋钮(D3)
        "scene_per_chapter": 1.4, "peak_divisor": 12, "n_peak_bonus": 5,
        "wave_fallback_cuts": [8, 20, 33, 46], "wave_min_chapters": 4,
    },
    "ingest": {
        "encodings": ["utf-8", "gbk", "gb18030"],
        "chapter_regex": r"^\s*第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章节卷回]",
        "junk_line_patterns": [
            r"作者[的有]?话", r"求(订阅|月票|推荐票|打赏|收藏)",
            r"(起点中文网|晋江文学城|笔趣阁|纵横中文网|番茄小说)",
            r"https?://|www\.", r"本(章|书)(未完|完)?，?(请|点击)",
            r"防盗|盗版|正版订阅", r"(PS|ps)[:：]",
        ],
        "garbage_char": "�", "min_chapter_chars": 200,
    },
}


def load(name: str) -> dict[str, Any]:
    """加载 config/<name>.yaml；无 PyYAML 或文件缺失则用内置默认。"""
    path = _CONFIG_DIR / f"{name}.yaml"
    try:
        import yaml  # type: ignore
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        pass
    return _DEFAULTS if name == "pipeline" else {}
