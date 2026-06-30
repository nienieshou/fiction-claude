"""Slice1c: 任务时间戳 —— Book 契约 + dir_to_book + runner JOBS。零 API。"""
from web.backend.contract import Book


def test_book_declares_timestamp_and_bestof_fields():
    b = Book(id="x_full", title="t", src="s", slug="x", genre="g", grade="A", comp="—",
             stage=5, status="certified", mode=0,
             started=1000.0, finished=1060.0, queued=999.0, bestof={"throws": 1})
    d = b.model_dump()
    for k in ("started", "finished", "queued", "bestof"):
        assert k in d, f"Book 未声明 {k} → response_model 会静默过滤"
    assert d["started"] == 1000.0 and d["finished"] == 1060.0
    assert d["queued"] == 999.0 and d["bestof"] == {"throws": 1}


import json
import pytest
from fastapi.testclient import TestClient
from web.backend import app as appmod, paths


def _mkbook(out, slug, *, report=None, timing=None, source=False, bestof=None):
    d = out / f"{slug}_full"
    d.mkdir(parents=True)
    if report is not None:
        (d / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    if timing is not None:
        (d / "_timing.json").write_text(json.dumps(timing), encoding="utf-8")
    if source:
        (d / "source").mkdir(); (d / "source" / "clean.txt").write_text("x", encoding="utf-8")
    if bestof is not None:
        (d / "_bestof.json").write_text(json.dumps(bestof, ensure_ascii=False), encoding="utf-8")
    return d


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT", tmp_path)   # OUTPUT 在 import 时定 → 必须 patch 属性
    return TestClient(appmod.app)


def _book(client, bid):
    return next(b for b in client.get("/api/books").json() if b["id"] == bid)


def test_certified_book_started_and_finished(client, tmp_path):
    _mkbook(tmp_path, "cert", report={"deliverable": True, "交付门": ["通过"], "seconds": 60},
            timing={"started_at": 1000.0}, bestof={"throws": 1, "classification": "T1直接交付"})
    b = _book(client, "cert_full")
    assert b["status"] == "certified"
    assert b["started"] == 1000.0 and b["finished"] == 1060.0
    assert b["bestof"] is not None and b["bestof"]["throws"] == 1   # 字段过 response_model


def test_nonterminal_has_started_no_finished(client, tmp_path):
    _mkbook(tmp_path, "idle", timing={"started_at": 2000.0}, source=True)  # 无 report → 非终态
    b = _book(client, "idle_full")
    assert b["started"] == 2000.0 and b["finished"] is None


def test_old_book_no_timing_graceful_none(client, tmp_path):
    _mkbook(tmp_path, "old", report={"deliverable": True, "交付门": ["通过"], "seconds": 30})  # 无 _timing
    b = _book(client, "old_full")
    assert b["started"] is None and b["finished"] is None


def test_explicit_finished_at_preferred(client, tmp_path):
    _mkbook(tmp_path, "exp", report={"deliverable": True, "交付门": ["通过"], "seconds": 60,
            "finished_at": 9999.0}, timing={"started_at": 1000.0})
    b = _book(client, "exp_full")
    assert b["finished"] == 9999.0   # 显式优先于 started+seconds(=1060)


import asyncio
from web.backend import runner


def test_job_status_returns_timestamps():
    runner.JOBS["js0"] = {"status": "running", "stage": 1, "log": [], "error": None,
                          "queued_at": 111.0, "started_at": 222.0}
    try:
        s = runner.job_status("js0")
        assert s["queued_at"] == 111.0 and s["started_at"] == 222.0
    finally:
        runner.JOBS.pop("js0", None)


def test_run_job_records_started_at(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.paths, "OUTPUT", tmp_path)
    slug = "rj0"
    runner.JOBS[slug] = {"status": "queued", "stage": 0, "log": [], "error": None, "queued_at": 5.0}
    runner.JOB_BOOKS[f"{slug}_full"] = {"id": f"{slug}_full", "status": "running", "stage": 0}

    async def fake_run(src, **kw):
        return {"deliverable": True, "交付门": ["通过"], "cost_cny": 1}
    try:
        asyncio.run(runner._run_job(slug, tmp_path / "s.txt", run_fn=fake_run))
        assert isinstance(runner.JOBS[slug].get("started_at"), float)
        assert isinstance(runner.JOB_BOOKS[f"{slug}_full"].get("started"), float)
    finally:
        runner.JOBS.pop(slug, None); runner.JOB_BOOKS.pop(f"{slug}_full", None)


def test_enqueue_records_queued_at(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.paths, "OUTPUT", tmp_path)
    monkeypatch.setattr(runner.paths, "SOURCES", tmp_path / "src")
    monkeypatch.setattr(runner, "UPLOAD_DIR", tmp_path / "src" / "_uploads")  # import 时定, 不patch会写真库
    async def noop(*a, **k):
        return None
    monkeypatch.setattr(runner, "_run_job", noop)   # 不真跑 produce
    try:
        res = asyncio.run(runner.enqueue("书.txt", "书", b"content"))
        slug = res["job_slug"]
        assert isinstance(runner.JOBS[slug].get("queued_at"), float)
        assert isinstance(runner.JOB_BOOKS[res["book"]["id"]].get("queued"), float)
    finally:
        for s in list(runner.JOBS): runner.JOBS.pop(s, None)
        for b in list(runner.JOB_BOOKS): runner.JOB_BOOKS.pop(b, None)
