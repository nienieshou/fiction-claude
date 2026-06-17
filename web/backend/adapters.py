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
# 真实 grade.json.mode 是中文串(mining._GRADE_MODE) → 原型 mode int(fixtures.MODE)
_MODE_STR_TO_INT = {"保真压缩": 1, "强化改写": 2, "类型化重构": 3, "概念级重启": 4}


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


def _status_from_report(report: dict) -> str:
    if report.get("rejected") or report.get("deliverable") is False:
        return "rejected"
    if report.get("deliverable") is True:
        return "certified"
    return "running"


# produce 阶段产物（source/ 之外）= 已进入 Extract 及以后，生产真的开始过
_PRODUCE_ARTIFACTS = ("bible.json", "grade.json", "plan.json", "macro.json", "final.md")


def _produce_started(d: Path) -> bool:
    return any((d / f).exists() for f in _PRODUCE_ARTIFACTS)


def _grade_obj(d: Path) -> dict:
    g = paths.load_json(d / "grade.json")
    return g if isinstance(g, dict) else {}


def dir_to_book(d: Path, hidx: dict[str, float], active: frozenset[str] = frozenset()) -> dict:
    report = paths.load_json(d / "report.json")
    report = report if isinstance(report, dict) else None
    grade = _grade_obj(d)
    bid = d.name
    slug = bid[:-5] if bid.endswith("_full") else bid
    # 状态：有 report→认证/拒收；活跃任务→running；已开产但无活跃任务无报告→stalled(中断,可续跑)；仅 source/→idle
    if report is not None:
        status = _status_from_report(report)
    elif slug in active:
        status = "running"
    elif _produce_started(d):
        status = "stalled"
    else:
        status = "idle"
    reject_reason = None
    if status == "rejected" and report:
        gate = report.get("交付门")
        if isinstance(gate, list) and gate and gate != ["通过"]:
            reject_reason = "；".join(str(x) for x in gate)
        reject_reason = reject_reason or report.get("reject_why")
    title = (report or {}).get("title") or (report or {}).get("书名") or slug
    g = grade.get("grade") if grade.get("grade") in _GRADE_SET else \
        ((report or {}).get("grade", {}) or {}).get("grade")
    mode_raw = grade.get("mode")
    mode = mode_raw if isinstance(mode_raw, int) else _MODE_STR_TO_INT.get(mode_raw, 0)
    human = hidx.get(slug) or hidx.get((report or {}).get("source", "").rsplit(".", 1)[0]) \
        or hidx.get(Path((report or {}).get("source", "")).stem)
    return {
        "id": bid, "title": title, "src": (report or {}).get("source") or slug,
        "slug": slug, "genre": grade.get("genre") or (report or {}).get("central_conflict", "") or "待识别",
        "grade": g or "—", "comp": grade.get("compressible") or grade.get("comp") or "—",
        "stage": _stage_from_artifacts(d, report),
        "status": status,
        "mode": mode, "human": human,
        "cost": round((report or {}).get("cost_cny") or 0),
        "real": True, "reject_reason": reject_reason,
        "seconds": (report or {}).get("seconds"), "calls": (report or {}).get("calls"),
    }


# ---------- 列表 / 详情 / 统计 ----------
def list_books(job_books: list[dict] | None = None,
               active: frozenset[str] | None = None) -> list[dict]:
    """真实 output 子目录 → 摘要（无真实产物则返回空，不再回退 demo）。并入后台任务 stub。
    active = 活跃任务 slug 集合（区分真在跑 vs 仅 ingest 的闲置目录）。"""
    active = active or frozenset()
    hidx = human_index()
    dirs = sorted(paths.output_dirs(), key=_mtime, reverse=True)          # 最新活动在最上
    books = [dir_to_book(d, hidx, active) for d in dirs]                  # 无真实产物 → 空(不再回退 demo)
    if job_books:
        have = {b["id"] for b in books}
        stubs = [jb for jb in job_books if jb["id"] not in have]
        books = stubs + books                                            # 刚上传(尚无目录)的任务置顶
    return books


def _mtime(d: Path) -> float:
    try:
        return d.stat().st_mtime
    except OSError:
        return 0.0


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


def _bible_to_spine(d: Path) -> list[dict] | None:
    """Fact Spine 冻结罗斯特来自 bible.json（人物/地点/势力/世界观体系），
    冲突来自 fact_table.json.findings(高置信)。"""
    bib = paths.load_json(d / "bible.json")
    if not isinstance(bib, dict):
        return None
    groups: list[dict] = []
    chars = []
    prot = bib.get("protagonist") or {}
    if prot.get("name"):
        chars.append({"name": prot["name"],
                      "attr": str(prot.get("identity") or prot.get("goal") or "主角")[:48], "lock": True})
    for c in (bib.get("characters") or [])[:12]:
        if isinstance(c, dict) and c.get("name"):
            chars.append({"name": c["name"],
                          "attr": str(c.get("role") or c.get("identity") or c.get("relation_arc") or "")[:48],
                          "lock": True})
    if chars:
        groups.append({"group": "人物登记", "items": chars})

    places = bib.get("places")
    if isinstance(places, list) and places:
        items = []
        for p in places[:8]:
            nm = p.get("name") if isinstance(p, dict) else str(p)
            al = "、".join(p.get("aliases") or []) if isinstance(p, dict) else ""
            if nm:
                items.append({"name": nm, "attr": al or "地点", "lock": True})
        if items:
            groups.append({"group": "地点登记", "items": items})

    ps = bib.get("power_system")
    factions = bib.get("factions")
    world = []
    if ps:
        world.append({"name": "战力体系", "attr": str(ps)[:80], "lock": True})
    if isinstance(factions, list):
        for f in factions[:4]:
            nm = f.get("name") if isinstance(f, dict) else str(f)
            if nm:
                world.append({"name": nm, "attr": "势力", "lock": True})
    if world:
        groups.append({"group": "世界观设定", "items": world})

    # 薄网检出的高置信冲突
    ft = paths.load_json(d / "fact_table.json")
    if isinstance(ft, dict):
        hi = [f for f in (ft.get("findings") or [])
              if isinstance(f, dict) and f.get("conf") == "高"][:6]
        if hi:
            groups.append({"group": "Spine 薄网·检出冲突", "items": [
                {"name": f"{f.get('who', '?')} · {f.get('cat', '')}", "attr": str(f.get("why") or "")[:60],
                 "lock": False} for f in hi]})
    return groups or None


def _plan_to_scenes(d: Path) -> dict | None:
    """场景 = plan.json.chapters(逐章 + 场景 mode) ⋈ macro.json.chapters(节拍/幕)。"""
    plan = paths.load_json(d / "plan.json")
    chs = plan.get("chapters") if isinstance(plan, dict) else None
    if not isinstance(chs, list) or not chs:
        return None
    macro = paths.load_json(d / "macro.json")
    mbeats = {m.get("i"): m for m in (macro.get("chapters") if isinstance(macro, dict) else [])
              if isinstance(m, dict)}
    drafted_all = (d / "final.md").exists()
    lst = []
    for ch in chs:
        if not isinstance(ch, dict):
            continue
        i = ch.get("index")
        scenes = ch.get("scenes") or []
        has_dram = any(isinstance(s, dict) and s.get("mode") == "DRAMATIZE" for s in scenes)
        typ = "DRAMATIZE" if has_dram else ("SUMMARIZE" if scenes else "—")
        m = mbeats.get(i, {})
        lst.append({"n": i, "type": typ,
                    "beat": str(m.get("beat") or ch.get("title") or "")[:60],
                    "status": "pass" if drafted_all else "pending",
                    "cand": "", "pk": m.get("act") or ""})
    # 无可靠的单章"高点"信号(高潮幕跨多章) → 不臆造 peaks，UI 显示"—"
    return {"total": len(chs), "drafted": len(chs) if drafted_all else 0,
            "peaks": [], "list": lst}


def _report_to_gate(report: dict) -> dict | None:
    """真实 report 的确定性硬检 → gate.book/mech（PK 无真值，留给 fixture）。"""
    book = []
    # 交付门拦截项（拒收主因）置顶为失败条目
    gate = report.get("交付门")
    if report.get("deliverable") is False and isinstance(gate, list) and gate and gate != ["通过"]:
        for issue in gate:
            book.append({"k": "交付门拦截", "pass": False, "note": str(issue)})
    fc = report.get("final_consistent")
    if fc is not None:
        book.append({"k": "全书连续性审计", "pass": bool(fc), "note": "✓" if fc else "不一致"})
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
        spine = _bible_to_spine(d)
        if spine:
            base["spine"] = spine
        scenes = _plan_to_scenes(d)
        if scenes:
            base["scenes"] = scenes
        # gate：有 report 用确定性硬检；否则用 fact_table 薄网兜底（真矛盾计数）
        if not report:
            ft = paths.load_json(d / "fact_table.json")
            sn = ft.get("spine_net") if isinstance(ft, dict) else None
            if isinstance(sn, dict):
                base["gate"] = {"mech": [], "pk": (base.get("gate") or {}).get("pk") or [], "book": [
                    {"k": "Spine 薄网·数值真矛盾", "pass": (sn.get("数值真矛盾", 0) == 0),
                     "note": f"{sn.get('数值真矛盾', 0)} 条"},
                    {"k": "Spine 薄网·身份真矛盾", "pass": (sn.get("身份真矛盾", 0) == 0),
                     "note": f"{sn.get('身份真矛盾', 0)} 条"}]}
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
