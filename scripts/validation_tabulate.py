# scripts/validation_tabulate.py
"""E3 验证块 tabulator: 纯读盘出 5 表 + C 门 go/no-go。不调 API。
用法: python scripts/validation_tabulate.py <validation_dir> [--labels labels.yaml] [--rung C]
见 docs/superpowers/specs/2026-06-30-e3-validation-ladder-design.md。"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

JUDGES = ("opus", "gpt55")
CARRY_THRESHOLD = 50.0          # 承重<50 = 假阳信号(预登记)
MIN_POWER = 4                   # 门放行 P<4 → 低功效
OVERLAP_STOP = 2                # 重叠假阳≥2 → 全局停升
STORY4_W = {"故事性": 0.30, "笔力": 0.25, "人": 0.25, "承重": 0.20}

FAILURE_CATEGORIES = (
    "境界乱序", "修为倒退", "性别错", "混名/认亲矛盾", "死人复活",
    "章节复制/注水", "DNA/身世互斥", "人设崩", "现代腔出戏",
)


@dataclass
class BookRecord:
    slug: str
    deliverable: bool
    jury: dict                      # judge -> {故事性,笔力,人,承重,total,deliver,reject_reason,comments}
    upstream: dict = field(default_factory=dict)   # judge -> [预测类目]
    observed: list = field(default_factory=list)   # 人工标注实测硬伤类目
    severity: float | None = None   # 各 judge 承重最小值(越低越严)


def _story4_total(d: dict) -> float:
    return round(sum(float(d[k]) * w for k, w in STORY4_W.items()), 2)


def load_records(vdir, labels: dict | None = None) -> list[BookRecord]:
    vdir = Path(vdir); labels = labels or {}
    recs = []
    jury_dir = vdir / "jury"
    slugs = sorted({p.name.split("__")[0] for p in jury_dir.glob("*__*.json")}) if jury_dir.is_dir() else []
    for slug in slugs:
        rep = vdir / slug / "report.json"
        deliverable = False
        if rep.exists():
            sig = (json.loads(rep.read_text(encoding="utf-8")).get("signals") or {})
            deliverable = bool(sig.get("deliverable"))
        jury = {}
        for j in JUDGES:
            p = jury_dir / f"{slug}__{j}.json"
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                d.setdefault("total", _story4_total(d))
                jury[j] = d
        upstream = {}
        for j in JUDGES:
            p = vdir / "upstream" / f"{slug}__{j}.json"
            if p.exists():
                upstream[j] = list(json.loads(p.read_text(encoding="utf-8")).get("predicted", []))
        carries = [jury[j]["承重"] for j in jury if "承重" in jury[j]]
        recs.append(BookRecord(slug=slug, deliverable=deliverable, jury=jury,
                               upstream=upstream, observed=list(labels.get(slug, [])),
                               severity=min(carries) if carries else None))
    return recs
