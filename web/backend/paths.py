"""项目路径定位：output 子目录、漏斗/批量报告、源目录、预算 cap。

后端从 web/backend/ 向上两级到项目根（E:\\...\\claude）。可用环境变量 HIKI_ROOT 覆盖。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("HIKI_ROOT") or Path(__file__).resolve().parents[2])
OUTPUT = ROOT / "output"
SOURCES = ROOT / "fictions_source"
CONFIG = ROOT / "config"

# 单本产物文件名（与 produce.py 落盘一致）
ARTIFACT_FILES = ("report.json", "bible.json", "grade.json", "scenes.json",
                  "plan.json", "macro.json", "fact_table.json", "final.md")


def output_dirs() -> list[Path]:
    """output/ 下含产物的子目录（每本一个，名如 <slug>_full 或 <out>/<slug>）。"""
    if not OUTPUT.is_dir():
        return []
    dirs = []
    for p in sorted(OUTPUT.iterdir()):
        if p.name in ("_deliverable", "_rejected"):
            continue                                  # 交付汇聚/拒收隔离目录,非书目(normalize 产物)
        if p.is_dir() and (p / "source").exists() or any((p / f).exists() for f in ARTIFACT_FILES):
            dirs.append(p)
        elif p.is_dir():
            # 批量父目录：其子目录才是本
            for c in sorted(p.iterdir()):
                if c.is_dir() and any((c / f).exists() for f in ARTIFACT_FILES + ("source",)):
                    dirs.append(c)
    return dirs


def load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def funnel_report() -> dict | None:
    r = load_json(OUTPUT / "funnel_report.json")
    return r if isinstance(r, dict) else None


def batch_summary() -> dict | None:
    r = load_json(OUTPUT / "batch_summary.json")
    return r if isinstance(r, dict) else None


def budget_cap_cny() -> float:
    """单本预算上限：config/pipeline.yaml > production.budget_cny_cap，缺则 50。"""
    try:
        import yaml  # type: ignore
        cfg = yaml.safe_load((CONFIG / "pipeline.yaml").read_text(encoding="utf-8")) or {}
        prod = cfg.get("production") or {}
        for k in ("budget_cny_cap", "budget_cap_cny", "max_cost_cny"):
            if k in prod:
                return float(prod[k])
    except Exception:
        pass
    return 50.0
