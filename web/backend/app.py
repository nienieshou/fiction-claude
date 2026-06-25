"""HIKI 产线监视台 · FastAPI 后端。

启动：
    cd <项目根>
    .venv\\Scripts\\python.exe -m uvicorn web.backend.app:app --reload
默认 http://127.0.0.1:8000  （/ 直接服务前端 index.html）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

# Windows 下服务进程默认 GBK stdout，produce.py finalize 会 print emoji(⛔⚠)→UnicodeEncodeError 崩溃。
# 与 CLI 入口一致改 UTF-8，避免改写任务在 finalize 崩。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from . import adapters, fixtures, paths, runner
from .contract import Book, Stats

async def _auto_resume_stalled() -> None:
    """启动时自动续跑被中断(stalled)的任务，避免重启把在跑的改写永久搁浅。
    仅 stalled(已开产无活跃任务)；idle(仅清洗)不自动起，免意外烧钱。HIKI_WEB_AUTORESUME=0 关闭。"""
    if os.environ.get("HIKI_WEB_AUTORESUME", "1") == "0":
        return
    try:
        stalled = [b for b in _books() if b.get("status") == "stalled" and b.get("real")]
    except Exception:
        return
    for b in stalled:
        try:
            await runner.resume(b["slug"])
            print(f"[autoresume] 续跑 {b['slug']}")
        except Exception as e:
            print(f"[autoresume] 跳过 {b.get('slug')}: {type(e).__name__}: {e}")


def _normalize_books() -> None:
    """启动时把旧命名成书归一到新规范(<源ID><新书名>.txt → _deliverable/)。幂等。HIKI_WEB_NORMALIZE=0 关闭。"""
    if os.environ.get("HIKI_WEB_NORMALIZE", "1") == "0":
        return
    try:
        from hiki import normalize
        results = normalize.normalize_tree(paths.OUTPUT)
        n = sum(1 for r in results if r.get("status") == "normalized")
        if n:
            print(f"[normalize] 归一 {n} 本旧命名成书 → _deliverable/")
    except Exception as e:
        print(f"[normalize] 跳过: {type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _normalize_books()
    await _auto_resume_stalled()
    yield


app = FastAPI(title="HIKI 产线监视台", version="0.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def _books() -> list[dict]:
    """书目列表：真实产物 + 任务 stub + 活跃任务集（区分 running vs idle）。"""
    return adapters.list_books(runner.job_books(), runner.active_slugs())


# ---------- 数据端点 ----------
@app.get("/api/stages", response_model=list[dict])
def get_stages() -> list[dict]:
    return fixtures.STAGES


@app.get("/api/stats", response_model=Stats)
def get_stats() -> dict:
    return adapters.stats(_books())


@app.get("/api/books", response_model=list[Book])
def get_books() -> list[dict]:
    return _books()


@app.get("/api/books/{book_id}")
def get_book(book_id: str) -> dict:
    books = _books()
    sel = next((b for b in books if b["id"] == book_id), None)
    if sel is None:
        raise HTTPException(404, f"unknown book: {book_id}")
    return {"sel": sel, "detail": adapters.book_detail(book_id, runner.job_books()),
            "modeText": fixtures.MODE.get(sel.get("mode", 0), "—"),
            "modeNote": fixtures.MODE_NOTE.get(sel.get("mode", 0), "")}


@app.get("/api/calibration")
def get_calibration() -> dict:
    return adapters.calibration()


# ---------- 上传 + 后台改写 ----------
@app.post("/api/uploads")
async def upload(file: UploadFile, new_name: str | None = None) -> dict:
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(400, "仅接受 .txt 源")
    content = await file.read()
    orig = Path(file.filename).stem
    return await runner.enqueue(orig, new_name or orig, content)


@app.get("/api/jobs/{slug}")
def get_job(slug: str) -> dict:
    st = runner.job_status(slug)
    if st is None:
        raise HTTPException(404, f"unknown job: {slug}")
    return st


@app.post("/api/books/{book_id}/resume")
async def resume_book(book_id: str) -> dict:
    """续跑被中断/待产的任务（从已有产物继续，真实花钱）。"""
    sel = next((b for b in _books() if b["id"] == book_id), None)
    if sel is None:
        raise HTTPException(404, f"unknown book: {book_id}")
    slug = sel["slug"]
    if slug in runner.active_slugs():
        return {"job_slug": slug, "already_running": True}
    if sel["status"] not in ("stalled", "idle"):
        raise HTTPException(400, f"仅可续跑 stalled/idle 任务，当前：{sel['status']}")
    try:
        return await runner.resume(slug)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))


@app.delete("/api/books/{book_id}")
def delete_book(book_id: str) -> dict:
    """删除任务：取消后台改写(若在跑) + 删 output/<id>/ + 删上传源 .txt。"""
    sel = next((b for b in _books() if b["id"] == book_id), None)
    if sel is None:
        raise HTTPException(404, f"unknown book: {book_id}")
    slug = sel["slug"]
    src = runner.job_src_path(slug)                 # 上传源(若由本应用上传,先取再清表)
    job_cancelled = runner.cancel_and_forget(slug)

    # 删产出目录（防越权：必须直属 output/）
    out = (paths.OUTPUT / book_id).resolve()
    output_removed = False
    if out.is_dir() and paths.OUTPUT.resolve() in out.parents:
        shutil.rmtree(out, ignore_errors=True)
        output_removed = not out.exists()

    # 删源文件：仅限上传暂存区 _uploads/（绝不删已跟踪库内源；去重复用的原文件不动）
    source_removed = None
    upload_dir = runner.UPLOAD_DIR.resolve()
    if src and src.exists() and upload_dir in src.resolve().parents:
        try:
            src.unlink()
            source_removed = src.name
        except OSError:
            pass

    return {"id": book_id, "output_removed": output_removed,
            "source_removed": source_removed, "job_cancelled": job_cancelled}


# ---------- 产物下载 ----------
def _content_disposition(filename: str) -> str:
    """RFC 6266 attachment 头，容忍中文 slug。
    HTTP 头只能 latin-1；中文文件名直接塞进 filename= 会让 starlette latin-1 编码崩(500，
    见 download_artifact 手搓 Response 头路径)。给 ASCII 回退 + RFC 5987 filename*=utf-8''<百分号编码>，
    与 starlette FileResponse 对非 ASCII 名的处理一致。"""
    ascii_fb = filename.encode("ascii", "ignore").decode("ascii") or "download"
    return f"attachment; filename=\"{ascii_fb}\"; filename*=utf-8''{quote(filename)}"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _gen_final(sel: dict, detail: dict) -> str:
    s = f"# {sel['title']}\n\n> 产线编号: {sel.get('slug') or sel['id']}\n"
    s += f"> 源稿: 《{sel.get('src') or '—'}》  →  《{sel['title']}》\n"
    s += f"> 题材: {sel.get('genre')}  ·  准入: {sel.get('grade')}\n"
    s += f"> 认证: {'已认证出货' if sel.get('status') == 'certified' else '未认证'}  ·  人工成品分: {sel.get('human') if sel.get('human') is not None else '—'} / 95\n"
    s += "> 规格: 固定 60 章 · ~21 万字 · 原创换皮重写（保故事内核 · 禁逐字照搬）\n"
    s += f"> 生成: HIKI fiction-rewrite v5.1 · {_today()}\n\n---\n\n"
    sc = (detail.get("scenes") or {})
    for x in (sc.get("list") or []):
        kind = "（戏剧化场景）" if x.get("type") == "DRAMATIZE" else "（概述过渡）"
        s += f"### 第 {x.get('n')} 章 · {x.get('beat')}\n_{kind}_\n\n（正文略 …）\n\n"
    s += "\n> 完整 60 章正文由 Assemble 阶段拼装输出，此处为交付结构摘要。\n"
    return s


def _gen_acceptance(sel: dict, detail: dict) -> str:
    obj = {
        "slug": sel.get("slug") or sel["id"], "title": sel["title"],
        "source_name": sel.get("src"), "genre": sel.get("genre"),
        "admission": {"grade": sel.get("grade"), "compressible": sel.get("comp")},
        "certified": sel.get("status") == "certified", "verdict": sel.get("status"),
        "human_score": sel.get("human"), "target": 95, "ship_line": 75,
        "cost_cny": sel.get("cost"), "budget_cap_cny": paths.budget_cap_cny(),
        "dimensions": {x["k"]: x["v"] for x in (detail.get("dims") or [])} or None,
        "review": (detail.get("review") or None),
        "source": "real" if sel.get("real") else "fixture",
        "generated": "HIKI fiction-rewrite v5.1", "date": _today(),
    }
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _gen_ledger(sel: dict, detail: dict) -> str:
    rows = detail.get("cost") or []
    total_usd = round(sum(c.get("usd", 0) for c in rows), 2)
    obj = {"slug": sel.get("slug") or sel["id"], "budget_cap_cny": paths.budget_cap_cny(),
           "total_usd": total_usd, "total_cny": round(total_usd / 0.14),
           "rows": [{"stage": c.get("k"), "usd": c.get("usd"), "note": c.get("note")} for c in rows]}
    return json.dumps(obj, ensure_ascii=False, indent=2)


_GEN = {"acceptance.json": (_gen_acceptance, "application/json"),
        "diagnostic.json": (_gen_acceptance, "application/json"),
        "cost_ledger.json": (_gen_ledger, "application/json"),
        "final.md": (_gen_final, "text/markdown; charset=utf-8")}


@app.get("/api/books/{book_id}/artifacts/{name}")
def download_artifact(book_id: str, name: str) -> Response:
    books = _books()
    sel = next((b for b in books if b["id"] == book_id), None)
    if sel is None:
        raise HTTPException(404, f"unknown book: {book_id}")
    # 真实文件优先（final.md）
    if sel.get("real"):
        real = paths.OUTPUT / book_id / name
        if real.exists():
            return FileResponse(real, filename=f"{sel.get('slug')}.{name}")
    gen = _GEN.get(name)
    if not gen:
        raise HTTPException(404, f"unknown artifact: {name}")
    fn, mime = gen
    text = fn(sel, adapters.book_detail(book_id, runner.job_books()))
    return Response(content=text, media_type=mime,
                    headers={"Content-Disposition": _content_disposition(f"{sel.get('slug')}.{name}")})


# ---------- 前端静态 ----------
@app.get("/")
def index() -> FileResponse:
    # no-cache：避免浏览器缓存旧前端（历史上 stale JS 导致按钮无响应）
    return FileResponse(FRONTEND / "index.html",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/health")
def health() -> dict:
    return {"ok": True, "output_dirs": len(paths.output_dirs()),
            "stdout_encoding": (sys.stdout.encoding or "").lower()}
