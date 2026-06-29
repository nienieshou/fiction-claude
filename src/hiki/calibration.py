"""E3 Slice1: HFL 校准数据审计 + 对齐 harness(纯函数, 0 LLM/0 网络/只读)。

见 docs/superpowers/specs/2026-06-29-e3-calibration-audit-harness-design.md。
只读 assets/hfl.jsonl + assets/gold_regression,产兼容性报告/假阳性透镜/溯源分歧审计。
不碰 pipeline/门/web/hfl 写入。门永不消费本模块(程序级影子)。
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TRUTH_SPACE = {"网文编辑": "editor", "fable": "proxy", "运营评委1": "ops", "总编辑": "chief_editor"}
GROUND_TRUTH = "editor"
STANDARD4 = frozenset({"拉力", "笔力", "人", "承重"})
STORY4 = frozenset({"故事性", "笔力", "人", "承重"})
CHENGZHONG_FLOOR = 50
# hfl 旧 auto_signals 键 → 冻结向量键(仅用于溯源分歧比对, 非建模)
LEGACY_TO_FROZEN = {
    "代入感分": "opening_immersion", "控制面重演": "reenact_hits",
    "章缝检出": "seam_detected", "deliverable": "deliverable",
    "暗黑比": "dark_ratio", "final_consistent": "final_consistent",
    "过短章数": "too_short_chapters", "章内双版本": "intra_repeat_chapters",
}


@dataclass(frozen=True)
class HflRow:
    line_no: int
    scorer: str
    title: str | None
    source: str | None
    truth_space: str          # editor/proxy/ops/chief_editor/unknown
    dims: dict
    dims_schema: str          # standard4 / story4 / other
    total: float | None
    slug: str | None
    version: str | None
    auto_signals: dict
    signal_compat: str        # frozen / legacy / none
    deliverable: bool | None


def _truth_space(scorer):
    return TRUTH_SPACE.get(scorer or "", "unknown")


def _dims_schema(dims):
    keys = frozenset((dims or {}).keys())
    if keys == STANDARD4:
        return "standard4"
    if keys == STORY4:
        return "story4"
    return "other"


def _signal_compat(auto):
    if not isinstance(auto, dict) or not auto:
        return "none"
    if "schema_version" in auto:
        return "frozen"
    if any(k in LEGACY_TO_FROZEN for k in auto):   # 有可映射旧键 → 可参与溯源比对
        return "legacy"
    return "none"                                  # 仅文字(note/era)或纯一次性键 → 建模无用


def load_hfl(path):
    """逐行解析 jsonl(跳空行)。畸形(非法JSON/非dict)行 fail-closed → errors, 不进 rows。
    每行派生 truth_space/dims_schema/signal_compat/deliverable。"""
    rows, errors = [], []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            raw = json.loads(s)
        except json.JSONDecodeError as e:
            errors.append({"line_no": i, "error": str(e), "raw": s[:200]})
            continue
        if not isinstance(raw, dict):
            errors.append({"line_no": i, "error": "not a JSON object", "raw": s[:200]})
            continue
        auto = raw.get("auto_signals")
        auto = auto if isinstance(auto, dict) else {}
        dims = raw.get("dims") if isinstance(raw.get("dims"), dict) else {}
        scorer = raw.get("scorer")
        total = raw.get("total")
        deliv = auto.get("deliverable")
        rows.append(HflRow(
            line_no=i, scorer=scorer or "",
            title=raw.get("title"), source=raw.get("source"),
            truth_space=_truth_space(scorer), dims=dims, dims_schema=_dims_schema(dims),
            total=total if isinstance(total, (int, float)) and not isinstance(total, bool) else None,
            slug=raw.get("slug"), version=raw.get("version"),
            auto_signals=auto, signal_compat=_signal_compat(auto),
            deliverable=deliv if isinstance(deliv, bool) else None,
        ))
    return rows, errors


def false_accept_lens(rows, floor=CHENGZHONG_FLOOR):
    """ground-truth(editor)行中 deliverable==True ∧ 承重<floor → 假阳性候选。
    仅看 hfl 行自身 deliverable, 不依赖 gold。"""
    editors = [r for r in rows if r.truth_space == GROUND_TRUTH and r.deliverable is not None]
    flagged = []
    for r in editors:
        cz = r.dims.get("承重")
        if r.deliverable is True and isinstance(cz, (int, float)) and not isinstance(cz, bool) and cz < floor:
            flagged.append({"slug": r.slug, "title": r.title, "承重": cz,
                            "total": r.total, "version": r.version, "auto_signals": r.auto_signals})
    n = len(editors)
    return {"flagged": flagged, "n_editor_with_deliverable": n,
            "rate": (len(flagged) / n) if n else 0.0, "floor": floor}


def compat_report(rows, errors):
    """兼容性报告: 按 (truth_space, dims_schema, signal_compat, version) 分桶计数。纯聚合。"""
    buckets = Counter((r.truth_space, r.dims_schema, r.signal_compat, r.version) for r in rows)
    return {
        "n_rows": len(rows),
        "n_errors": len(errors),
        "n_ground_truth": sum(1 for r in rows if r.truth_space == GROUND_TRUTH),
        "by_truth_space": dict(Counter(r.truth_space for r in rows)),
        "buckets": {
            f"{ts}|{ds}|{sc}|{ver}": n
            for (ts, ds, sc, ver), n in sorted(buckets.items(), key=lambda kv: (-kv[1], str(kv[0])))
        },
    }


def load_gold_signal_vectors(gold_dir):
    """slug -> fixture['signals'](冻结向量)。只读 <gold_dir>/<slug>/fixture.json。"""
    out = {}
    for fx in sorted(Path(gold_dir).glob("*/fixture.json")):
        data = json.loads(fx.read_text(encoding="utf-8"))
        sigs = data.get("signals")
        if isinstance(sigs, dict):
            out[fx.parent.name] = sigs
    return out


def _comparable(a, b):
    """两值是否类型可比: bool 仅与 bool 比; 数值(非bool)互比; 其余不可比。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool)
    return isinstance(a, (int, float)) and isinstance(b, (int, float))


def provenance_divergence(rows, gold_vectors):
    """editor∩slug∩gold 的书: hfl auto_signals 经 LEGACY_TO_FROZEN 映射后逐可比较共享键比 gold。
    divergent=任一键不等(证不同次跑); inconclusive=全等但 gold 无溯源字段(不算 matched)。
    n_provenance_matched 结构性恒 0(gold 无溯源元数据, 绝不由 legacy 巧合相等推断)。"""
    books, n_div, n_inc = [], 0, 0
    for r in rows:
        if r.truth_space != GROUND_TRUTH or not r.slug or r.slug not in gold_vectors:
            continue
        gv = gold_vectors[r.slug]
        mapped = {LEGACY_TO_FROZEN[k]: v for k, v in r.auto_signals.items() if k in LEGACY_TO_FROZEN}
        shared = [k for k in sorted(set(mapped) & set(gv)) if _comparable(mapped[k], gv[k])]
        diffs = {k: [mapped[k], gv[k]] for k in shared if mapped[k] != gv[k]}
        status = "divergent" if diffs else "inconclusive"
        n_div += status == "divergent"
        n_inc += status == "inconclusive"
        books.append({"slug": r.slug, "shared_keys": shared, "diffs": diffs, "status": status})
    return {"books": books, "n_overlap": len(books), "n_divergent": n_div,
            "n_inconclusive": n_inc, "n_provenance_matched": 0}
