"""真实产物 → 契约映射（核心）。缺失则回退 fixtures（见 docs/design/web_console.md §2）。

策略：fixture 为底，真实产物逐字段覆盖（overlay）。保证 UI 永远有数据，
真实可得处用真实值。无任何 output 子目录时，整体回退到原型 8 本。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from . import fixtures, paths

_GRADE_SET = {"S", "A", "B", "C", "D", "Q"}


# ---------- human-eval 索引（assets/hfl.jsonl）----------
def human_index() -> dict[str, float]:
    """slug / 源名 stem → 人工成品总分。"""
    idx: dict[str, float] = {}
    f = paths.ROOT / "assets" / "hfl.jsonl"
    if not f.exists():
        return idx
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        total = row.get("total")
        if total is None:
            continue
        if row.get("slug"):
            idx[str(row["slug"])] = total
        src = str(row.get("source") or "")
        if src:
            idx[Path(src).stem] = total
    return idx


# ---------- 单本目录 → 摘要 ----------
def _stage_from_artifacts(d: Path, report: dict | None) -> int:
    if report is not None:
        return 5
    if (d / "final.md").exists():
        return 4
    if (d / "plan.json").exists() or (d / "macro.json").exists():
        return 3
    if (d / "bible.json").exists() or (d / "grade.json").exists():
        return 2
    if (d / "source").exists():
        return 0
    return 1


def _status_from_report(report: dict | None) -> str:
    if report is None:
        return "running"
    if report.get("rejected") or report.get("deliverable") is False:
        return "rejected"
    if report.get("deliverable") is True:
        return "certified"
    return "running"


def _grade_obj(d: Path) -> dict:
    g = paths.load_json(d / "grade.json")
    return g if isinstance(g, dict) else {}


def dir_to_book(d: Path, hidx: dict[str, float]) -> dict:
    report = paths.load_json(d / "report.json")
    report = report if isinstance(report, dict) else None
    grade = _grade_obj(d)
    bid = d.name
    slug = bid[:-5] if bid.endswith("_full") else bid
    title = (report or {}).get("title") or (report or {}).get("书名") or slug
    g = grade.get("grade") if grade.get("grade") in _GRADE_SET else \
        ((report or {}).get("grade", {}) or {}).get("grade")
    mode_raw = grade.get("mode")
    mode = mode_raw if isinstance(mode_raw, int) else 0
    human = hidx.get(slug) or hidx.get((report or {}).get("source", "").rsplit(".", 1)[0]) \
        or hidx.get(Path((report or {}).get("source", "")).stem)
    return {
        "id": bid, "title": title, "src": (report or {}).get("source") or slug,
        "slug": slug, "genre": grade.get("genre") or (report or {}).get("central_conflict", "") or "待识别",
        "grade": g or "—", "comp": grade.get("compressible") or grade.get("comp") or "—",
        "stage": _stage_from_artifacts(d, report),
        "status": _status_from_report(report),
        "mode": mode, "human": human,
        "cost": round((report or {}).get("cost_cny") or 0),
        "real": True,
    }


# ---------- 列表 / 详情 / 统计 ----------
def list_books(job_books: list[dict] | None = None) -> list[dict]:
    """真实 output 子目录 → 摘要；无则回退原型 8 本。并入后台任务 stub。"""
    dirs = paths.output_dirs()
    if dirs:
        hidx = human_index()
        books = [dir_to_book(d, hidx) for d in dirs]
    else:
        books = [copy.deepcopy(b) for b in fixtures.BOOKS]
    if job_books:
        have = {b["id"] for b in books}
        for jb in job_books:
            if jb["id"] not in have:
                books.append(jb)
    return books


def _bible_to_dna(d: Path) -> list[dict] | None:
    b = paths.load_json(d / "bible.json")
    if not isinstance(b, dict):
        return None
    prot = b.get("protagonist") or {}
    dna = []
    if b.get("central_conflict"):
        dna.append({"label": "脊柱 spine", "v": str(b["central_conflict"])[:60], "note": ""})
    if prot.get("name"):
        dna.append({"label": "主角 arc", "v": f"{prot.get('name')} · {prot.get('arc') or prot.get('goal') or ''}", "note": ""})
    if b.get("genre"):
        dna.append({"label": "题材 genre", "v": str(b["genre"]), "note": ""})
    if b.get("voice"):
        dna.append({"label": "语域指纹 voice", "v": str(b["voice"])[:40], "note": "cosine 基线"})
    chars = b.get("characters")
    if isinstance(chars, list) and chars:
        dna.append({"label": "人名词典 names", "v": f"{len(chars)} 实体冻结", "note": "→ Fact Spine"})
    return dna or None


def _factspine(d: Path) -> list[dict] | None:
    ft = paths.load_json(d / "fact_table.json")
    if not isinstance(ft, dict):
        return None
    groups = []
    chars = ft.get("characters") or ft.get("人物")
    if isinstance(chars, list) and chars:
        items = [{"name": str(c.get("name") or c.get("名") or c), "attr": str(c.get("attr") or c.get("状态") or ""),
                  "lock": True} for c in chars[:8]]
        groups.append({"group": "人物登记", "items": items})
    return groups or None


def _report_to_gate(report: dict) -> dict | None:
    """真实 report 的确定性硬检 → gate.book/mech（PK 无真值，留给 fixture）。"""
    book = []
    fc = report.get("final_consistent")
    if fc is not None:
        book.append({"k": "全书连续性审计", "pass": bool(fc),
                     "note": "；".join(report.get("交付门") or []) if not fc else "✓"})
    audit = report.get("audit_承重_确定性硬检")
    if isinstance(audit, dict):
        book.append({"k": "承重确定性硬检", "pass": "全过" in audit, "note": str(list(audit)[:3])})
    mech = []
    if report.get("暗黑比") is not None:
        dr = report["暗黑比"]
        mech.append({"k": "暗黑比", "v": f"{dr}", "pass": dr <= 0.25, "note": "门 ≤0.25"})
    if report.get("avg_chapter_chars"):
        mech.append({"k": "结构合规", "v": f"{report.get('out_chapters')}章 · 均{report['avg_chapter_chars']}字",
                     "pass": True, "note": ""})
    if not book and not mech:
        return None
    return {"mech": mech, "book": book}


def book_detail(book_id: str, job_books: list[dict] | None = None) -> dict:
    """fixture 为底（按 id），真实产物 overlay。未知本 → 空骨架。"""
    base = copy.deepcopy(fixtures.DETAILS.get(book_id) or fixtures.empty_detail())

    # 真实目录 overlay
    dirs = {d.name: d for d in paths.output_dirs()}
    d = dirs.get(book_id)
    if d is not None:
        report = paths.load_json(d / "report.json")
        report = report if isinstance(report, dict) else None
        dna = _bible_to_dna(d)
        if dna:
            base["dna"] = dna
        spine = _factspine(d)
        if spine:
            base["spine"] = spine
        if report:
            gate = _report_to_gate(report)
            if gate:
                # 真实 mech/book 覆盖，PK 保留 fixture（无真值）
                base_gate = base.get("gate") or {}
                base["gate"] = {"mech": gate["mech"] or (base_gate.get("mech") or []),
                                "pk": base_gate.get("pk") or [],
                                "book": gate["book"] or (base_gate.get("book") or [])}
            if report.get("cost_cny"):
                base.setdefault("cost", [])
                # 真实只有总额：作为单行追加（per-stage 无真值）
                if not any(r.get("k") == "实测总成本" for r in base["cost"]):
                    base["cost"] = [{"k": "实测总成本", "usd": round(report["cost_cny"] * 0.14, 2),
                                     "note": f"¥{report['cost_cny']} 真实"}] + base["cost"]
    return base


def stats(books: list[dict]) -> dict:
    certified = sum(1 for b in books if b.get("status") == "certified")
    rejected = sum(1 for b in books if b.get("status") == "rejected")
    finished = max(1, certified + rejected)
    cert_costs = [b.get("cost") or 0 for b in books if b.get("status") == "certified"]
    avg = round(sum(cert_costs) / max(1, len(cert_costs)))
    out = {
        "total": len(books), "certified": certified,
        "rejectRate": f"{round(rejected / finished * 100)}%",
        "avgCost": avg, "budgetCap": paths.budget_cap_cny(),
    }
    fr = paths.funnel_report()
    if fr:
        out["funnel"] = {k: fr.get(k) for k in ("入池", "存活", "改写", "可交付", "拒收", "总成本_cny") if k in fr}
    bs = paths.batch_summary()
    if bs:
        out["batch"] = {k: bs.get(k) for k in ("任务数", "可交付", "总成本_cny", "均成本_cny") if k in bs}
    return out


def calibration() -> dict:
    return copy.deepcopy(fixtures.CALIB)
