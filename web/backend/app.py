"""HIKI 产线监视台 · FastAPI 后端。

启动：
    cd <项目根>
    .venv\\Scripts\\python.exe -m uvicorn web.backend.app:app --reload
默认 http://127.0.0.1:8000  （/ 直接服务前端 index.html）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from . import adapters, fixtures, paths, runner
from .contract import Book, Stats

app = FastAPI(title="HIKI 产线监视台", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


# ---------- 数据端点 ----------
@app.get("/api/stages", response_model=list[dict])
def get_stages() -> list[dict]:
    return fixtures.STAGES


@app.get("/api/stats", response_model=Stats)
def get_stats() -> dict:
    return adapters.stats(adapters.list_books(runner.job_books()))


@app.get("/api/books", response_model=list[Book])
def get_books() -> list[dict]:
    return adapters.list_books(runner.job_books())


@app.get("/api/books/{book_id}")
def get_book(book_id: str) -> dict:
    books = adapters.list_books(runner.job_books())
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


# ---------- 产物下载 ----------
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
    books = adapters.list_books(runner.job_books())
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
                    headers={"Content-Disposition": f'attachment; filename="{sel.get("slug")}.{name}"'})


# ---------- 前端静态 ----------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "output_dirs": len(paths.output_dirs())}
