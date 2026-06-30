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


def is_false_accept(rec: BookRecord, judge: str, carry_threshold: float = CARRY_THRESHOLD) -> bool:
    """假阳 = 门放行(deliverable) 但该 judge 判 deliver==no 或 承重<阈。门未放行的书不算假阳。"""
    if not rec.deliverable:
        return False
    j = rec.jury.get(judge)
    if not j:
        return False
    return str(j.get("deliver")).lower() == "no" or float(j.get("承重", 100)) < carry_threshold


def false_accept_table(records, carry_threshold: float = CARRY_THRESHOLD) -> dict:
    passed = [r for r in records if r.deliverable]
    per_judge = {}
    for jdg in JUDGES:
        fp = [r.slug for r in passed if is_false_accept(r, jdg, carry_threshold)]
        per_judge[jdg] = {"fp_slugs": fp, "n": len(fp)}
    fp_sets = [set(per_judge[j]["fp_slugs"]) for j in JUDGES]
    overlap = sorted(set.intersection(*fp_sets)) if fp_sets else []
    rows = [{"slug": r.slug, "judge": j, "承重": r.jury[j]["承重"],
             "total": r.jury[j]["total"], "reject_reason": r.jury[j].get("reject_reason", "")}
            for r in passed for j in JUDGES if is_false_accept(r, j, carry_threshold)]
    return {"n_passed": len(passed), "per_judge": per_judge,
            "overlap_slugs": overlap, "n_overlap": len(overlap), "rows": rows}


def gate_decision(records, carry_threshold: float = CARRY_THRESHOLD,
                  min_power: int = MIN_POWER, overlap_stop: int = OVERLAP_STOP) -> dict:
    t = false_accept_table(records, carry_threshold)
    P = t["n_passed"]
    per_judge_fp = {j: t["per_judge"][j]["n"] for j in JUDGES}
    n_overlap = t["n_overlap"]
    notes = []
    if P < min_power:
        verdict = "low_power_inconclusive"
        notes.append(f"门放行 P={P}<{min_power}: 假阳检验功效不足, 不当'安全'自动升档; 另评门拒收书测过度拒收; 门放行率过低本身=发现(门可能过严)")
    elif n_overlap >= overlap_stop:
        verdict = "unsafe_consensus"
        notes.append(f"重叠假阳 {n_overlap}>={overlap_stop}(双族共识): 门非交付安全 → 停升, 转修门/上游")
    elif any(per_judge_fp[j] >= overlap_stop for j in JUDGES):
        verdict = "single_judge_investigate"
        hi = [j for j in JUDGES if per_judge_fp[j] >= overlap_stop]
        notes.append(f"单 judge 假阳≥{overlap_stop}({','.join(hi)}) 但重叠<{overlap_stop}: 不全局停; 标该 judge 视角不安全 + 触发调查(judge 偏严 vs 真硬伤), 本档=待查, 可带 flag 升档")
    else:
        verdict = "safe_advance"
    return {"P": P, "per_judge_fp": per_judge_fp, "n_overlap": n_overlap,
            "verdict": verdict, "notes": notes}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def separation(records) -> dict:
    out = {}
    for jdg in JUDGES:
        pas = [r.jury[jdg]["total"] for r in records if r.deliverable and jdg in r.jury]
        rej = [r.jury[jdg]["total"] for r in records if not r.deliverable and jdg in r.jury]
        pm, rm = _mean(pas), _mean(rej)
        out[jdg] = {"pass_mean": pm, "reject_mean": rm,
                    "delta": round(pm - rm, 2) if pm is not None and rm is not None else None}
    return out


def judge_reliability(records) -> dict:
    spread, bias, agree = {}, [], []
    for r in records:
        if "opus" in r.jury and "gpt55" in r.jury:
            o, g = r.jury["opus"], r.jury["gpt55"]
            spread[r.slug] = round(abs(o["total"] - g["total"]), 2)
            bias.append(o["total"] - g["total"])
            agree.append(str(o.get("deliver")).lower() == str(g.get("deliver")).lower())
    return {"per_book_spread": spread,
            "divergent_slugs": sorted([s for s, sp in spread.items() if sp > 15]),
            "mean_bias": round(sum(bias) / len(bias), 2) if bias else None,
            "deliver_agreement_rate": round(sum(agree) / len(agree), 4) if agree else None}


def failure_mode_table(records) -> dict:
    N = len(records) or 1
    out = {}
    for cat in FAILURE_CATEGORIES:
        books = [r for r in records if cat in r.observed]
        if not books:
            continue
        sev = _mean([r.severity for r in books])
        out[cat] = {"n_books": len(books), "freq": len(books) / N,
                    "avg_severity": sev,
                    "gate_caught": sum(1 for r in books if not r.deliverable)}
    return out


def upstream_interception(records) -> dict:
    per_book, tot_int, tot_obs = {}, 0, 0
    by_cat = {}
    for r in records:
        obs = set(r.observed)
        pred = set().union(*[set(r.upstream.get(j, [])) for j in JUDGES]) if r.upstream else set()
        inter = obs & pred
        rate = (len(inter) / len(obs)) if obs else None
        per_book[r.slug] = {"observed": sorted(obs), "predicted": sorted(pred),
                            "intercepted": sorted(inter), "rate": rate}
        if obs:
            tot_int += len(inter); tot_obs += len(obs)
        for c in obs:
            by_cat.setdefault(c, {"observed": 0, "predicted_upstream": 0})["observed"] += 1
        for c in (pred & obs):
            by_cat.setdefault(c, {"observed": 0, "predicted_upstream": 0})["predicted_upstream"] += 1
    return {"per_book": per_book,
            "overall_rate": (tot_int / tot_obs) if tot_obs else None,
            "by_category": by_cat}
