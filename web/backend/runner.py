"""上传 → 落盘 → 后台触发 hiki run。任务状态存内存（重启即丢，见设计 §7）。

真实花钱（DeepSeek API）。缺 DEEPSEEK_API_KEY 时任务直接 failed，不崩后端。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import paths

# 上传暂存区：新源落这里(gitignored)，绝不污染已跟踪的 fictions_source/ 库
UPLOAD_DIR = paths.SOURCES / "_uploads"

# src/ 上 sys.path，才能 import hiki
_SRC = str(paths.ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# 行之有效·质量优先配置（讨论沉淀, 见 docs/design/web_console.md §9 / fact_spine.md M2）：
# Fact Spine 全套(+18.8 承重)、精修 3 轮(2-3 即够,多轮震荡)、每场景候选 3、交付门+可拒收。
# best-of-3 已启(交付门拒→重掷,env HIKI_WEB_BEST_OF;源头致命不重)。质量 > 成本。
QUALITY = {"spine": True, "refine_rounds": 3, "n_cand": 3}

# job 并发闸:web 上传无外层 --parallel,多本齐发会撞 DeepSeek 限流→APITimeout 崩;闸到 N(默认2)排队。
_JOB_CONCURRENCY = max(1, int(os.environ.get("HIKI_WEB_CONCURRENCY", "2")))
_JOB_SEM = asyncio.Semaphore(_JOB_CONCURRENCY)

# 内存任务表：slug -> {status, stage, log[], error, report}
JOBS: dict[str, dict] = {}
# 任务对应的书目 stub（并入 /api/books）
JOB_BOOKS: dict[str, dict] = {}


def _slugify(s: str) -> str:
    return re.sub(r"[\s·.\-/\\:|，,。、《》<>()（）\"'’]+", "", str(s or "")).strip()


def make_slug(old: str, new: str) -> str:
    """命名 源名_新名_date；未改名（新==源或空）则收敛为 源名_date，不重复。"""
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    so, sn = _slugify(old), _slugify(new)
    if not sn or sn == so:
        return f"{so}_{date}"
    return f"{so}_{sn}_{date}"


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w一-鿿.\-]+", "_", name).strip("_") or "upload"


def _find_existing_source(content: bytes) -> Path | None:
    """内容命中已跟踪库内源(顶层 .txt) → 返回其路径(去重,复用原文件)。大小先筛再 hash。"""
    n = len(content)
    h = None
    for p in paths.SOURCES.glob("*.txt"):          # 非递归:不含 _uploads/ 子目录
        try:
            if p.stat().st_size != n:
                continue
            if h is None:
                h = hashlib.sha256(content).hexdigest()
            if hashlib.sha256(p.read_bytes()).hexdigest() == h:
                return p
        except OSError:
            continue
    return None


def _resolve_src(orig_name: str, new_name: str, content: bytes) -> Path:
    """去重优先:命中库内源→复用;否则落 gitignored 暂存区(绝不写/覆盖已跟踪库)。"""
    existing = _find_existing_source(content)
    if existing is not None:
        return existing
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    p = UPLOAD_DIR / f"{_safe_name(new_name or orig_name)}.txt"
    p.write_bytes(content)
    return p


def job_books() -> list[dict]:
    return list(JOB_BOOKS.values())


def active_slugs() -> frozenset[str]:
    """正在排队/运行的任务 slug（用于区分真在跑 vs 仅 ingest 的闲置目录）。"""
    return frozenset(s for s, j in JOBS.items() if j.get("status") in ("queued", "running"))


def job_src_path(slug: str) -> Path | None:
    """该任务上传时落盘的源 .txt（用于删除时一并清理）。"""
    sp = JOBS.get(slug, {}).get("src_path")
    return Path(sp) if sp else None


def cancel_and_forget(slug: str) -> bool:
    """取消该 slug 的后台改写任务（若在跑）并从内存表移除。返回是否真取消了运行中的任务。"""
    j = JOBS.pop(slug, None)
    cancelled = False
    if j:
        t = j.get("task")
        if t is not None and not t.done():
            t.cancel()
            cancelled = True
    JOB_BOOKS.pop(f"{slug}_full", None)
    return cancelled


def job_status(slug: str) -> dict | None:
    j = JOBS.get(slug)
    if not j:
        return None
    return {"slug": slug, "status": j["status"], "stage": j.get("stage", 0),
            "log": j.get("log", [])[-12:], "error": j.get("error"), "throws": j.get("throws", 1)}


def _classify_bestof(history: list[dict]) -> str:
    """best-of-N 结果分类(供诊断):T1直接交付 / 重掷救回 / 系统性拒 / 源头致命 / none。"""
    if not history:
        return "none"
    final = history[-1]
    if final.get("deliverable"):
        return "T1直接交付" if len(history) == 1 else "重掷救回"
    if any(h.get("rejected") for h in history):
        return "源头致命"
    return "系统性拒(全稿交付门拒)"


async def _run_job(slug: str, src_path: Path, run_fn=None) -> None:
    job = JOBS[slug]
    out_dir = paths.OUTPUT / f"{slug}_full"
    best_of = max(1, int(os.environ.get("HIKI_WEB_BEST_OF", "3")))
    async with _JOB_SEM:                                  # 并发闸:多本上传排队,不齐发(防APITimeout崩)
        job["status"] = "running"
        job["log"].append(f"start · {src_path.name} · best-of-{best_of} · 质量优先(Spine开,精修{QUALITY['refine_rounds']}轮,候选{QUALITY['n_cand']})")
        try:
            if QUALITY["spine"]:
                os.environ["HIKI_SPINE"] = "1"
            if run_fn is None:
                import hiki.produce as produce          # 延迟导入:缺依赖/key 在此暴露
                run_fn = produce.run
            from hiki.batch import _should_retry
            history, report = [], None
            for attempt in range(1, best_of + 1):
                report = await run_fn(src_path, out_dir=out_dir, n_cand=QUALITY["n_cand"],
                                      refine_rounds=QUALITY["refine_rounds"], force=(attempt > 1))
                reason = report.get("reject_why") or "；".join(report.get("交付门") or [])
                history.append({"throw": attempt, "deliverable": report.get("deliverable"),
                                "rejected": bool(report.get("rejected")), "reason": reason[:100],
                                "cost_cny": report.get("cost_cny")})
                job["log"].append(f"throw{attempt}/{best_of}: "
                                  + ("可交付" if report.get("deliverable")
                                     else ("源拒" if report.get("rejected") else "交付门拒→重掷")))
                if not _should_retry(report):
                    break
            job["report"] = report
            job["throws"] = len(history)
            cls = _classify_bestof(history)
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "_bestof.json").write_text(json.dumps(
                    {"best_of": best_of, "throws": len(history), "classification": cls,
                     "history": history}, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            if report.get("rejected") or report.get("deliverable") is False:
                job["status"] = "rejected"
                job["log"].append(f"done · rejected · {cls}")
            else:
                job["status"] = "done"
                job["log"].append(f"done · 可交付 · {cls}")
        except Exception as e:                            # 失败隔离:不崩后端
            job["status"] = "failed"
            job["error"] = f"{type(e).__name__}: {e}"[:300]
            job["log"].append(f"failed · {job['error']}")
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "_crash.txt").write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass
    # 标记 stub 终态（list_books 若已发现真实目录会用真实值覆盖）
    stub = JOB_BOOKS.get(f"{slug}_full")
    if stub:
        stub["status"] = {"done": "certified", "rejected": "rejected",
                          "failed": "rejected"}.get(job["status"], "running")
        stub["stage"] = 5 if job["status"] in ("done", "rejected") else stub.get("stage", 0)
        if job.get("report", {}).get("cost_cny"):
            stub["cost"] = round(job["report"]["cost_cny"])


async def enqueue(orig_name: str, new_name: str, content: bytes) -> dict:
    """去重落盘(命中库内源则复用,否则落暂存区)，建 job + stub，后台跑 produce.run。返回 stub。"""
    paths.SOURCES.mkdir(parents=True, exist_ok=True)
    slug = make_slug(orig_name, new_name or orig_name)
    src_path = _resolve_src(orig_name, new_name, content)

    JOBS[slug] = {"status": "queued", "stage": 0, "log": [], "error": None,
                  "src_path": str(src_path)}
    stub = {"id": f"{slug}_full", "title": new_name or orig_name, "src": orig_name,
            "slug": slug, "genre": "待识别", "grade": "—", "comp": "—", "stage": 0,
            "status": "running", "mode": 0, "human": None, "cost": 0, "uploaded": True}
    JOB_BOOKS[stub["id"]] = stub

    JOBS[slug]["task"] = asyncio.create_task(_run_job(slug, src_path))
    return {"book": stub, "job_slug": slug}


async def resume(slug: str) -> dict:
    """续跑被中断的任务：用 out_dir 已有的 clean 源重跑 produce(B2 续跑,跳过已完成阶段)。"""
    out_dir = paths.OUTPUT / f"{slug}_full"
    src = out_dir / "source" / "clean.txt"
    if not src.exists():
        cand = sorted((out_dir / "source").glob("*.txt")) if (out_dir / "source").is_dir() else []
        src = cand[0] if cand else None
    if src is None:
        raise FileNotFoundError(f"无可续跑的源(缺 source/clean.txt): {slug}")
    JOBS[slug] = {"status": "queued", "stage": 0, "log": [f"resume · {src.name}"],
                  "error": None, "src_path": str(src)}
    JOBS[slug]["task"] = asyncio.create_task(_run_job(slug, src))
    return {"job_slug": slug, "resumed": True}
