"""上传 → 落盘 → 后台触发 hiki run。任务状态存内存（重启即丢，见设计 §7）。

真实花钱（DeepSeek API）。缺 DEEPSEEK_API_KEY 时任务直接 failed，不崩后端。
"""
from __future__ import annotations

import asyncio
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import paths

# src/ 上 sys.path，才能 import hiki
_SRC = str(paths.ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# 内存任务表：slug -> {status, stage, log[], error, report}
JOBS: dict[str, dict] = {}
# 任务对应的书目 stub（并入 /api/books）
JOB_BOOKS: dict[str, dict] = {}


def _slugify(s: str) -> str:
    return re.sub(r"[\s·.\-/\\:|，,。、《》<>()（）\"'’]+", "", str(s or "")).strip()


def make_slug(old: str, new: str) -> str:
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{_slugify(old)}_{_slugify(new)}_{date}"


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w一-鿿.\-]+", "_", name).strip("_") or "upload"


def job_books() -> list[dict]:
    return list(JOB_BOOKS.values())


def job_status(slug: str) -> dict | None:
    j = JOBS.get(slug)
    if not j:
        return None
    return {"slug": slug, "status": j["status"], "stage": j.get("stage", 0),
            "log": j.get("log", [])[-12:], "error": j.get("error")}


async def _run_job(slug: str, src_path: Path) -> None:
    job = JOBS[slug]
    job["status"] = "running"
    job["log"].append(f"start · {src_path.name}")
    out_dir = paths.OUTPUT / f"{slug}_full"
    try:
        import hiki.produce as produce  # 延迟导入：缺依赖/key 在此暴露
        report = await produce.run(src_path, out_dir=out_dir)
        job["report"] = report
        if report.get("rejected") or report.get("deliverable") is False:
            job["status"] = "rejected"
            job["log"].append("done · rejected/不可交付")
        else:
            job["status"] = "done"
            job["log"].append("done · 可交付")
    except Exception as e:  # 失败隔离：不崩后端
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
    """落 fictions_source/，建 job + stub，后台跑 produce.run。返回 stub。"""
    paths.SOURCES.mkdir(parents=True, exist_ok=True)
    slug = make_slug(orig_name, new_name or orig_name)
    src_path = paths.SOURCES / f"{_safe_name(new_name or orig_name)}.txt"
    src_path.write_bytes(content)

    JOBS[slug] = {"status": "queued", "stage": 0, "log": [], "error": None}
    stub = {"id": f"{slug}_full", "title": new_name or orig_name, "src": orig_name,
            "slug": slug, "genre": "待识别", "grade": "—", "comp": "—", "stage": 0,
            "status": "running", "mode": 0, "human": None, "cost": 0, "uploaded": True}
    JOB_BOOKS[stub["id"]] = stub

    asyncio.create_task(_run_job(slug, src_path))
    return {"book": stub, "job_slug": slug}
