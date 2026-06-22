"""web runner: best-of-N 分类 + 重掷循环。零 API(注入 fake run_fn)。"""
import asyncio
from web.backend import runner


def test_classify_t1_delivered():
    assert runner._classify_bestof([{"deliverable": True}]) == "T1直接交付"


def test_classify_rescued():
    h = [{"deliverable": False}, {"deliverable": True}]
    assert runner._classify_bestof(h) == "重掷救回"


def test_classify_systematic_reject():
    h = [{"deliverable": False}, {"deliverable": False}, {"deliverable": False}]
    assert runner._classify_bestof(h) == "系统性拒(全稿交付门拒)"


def test_classify_source_fatal():
    assert runner._classify_bestof([{"rejected": True, "deliverable": False}]) == "源头致命"


def test_classify_empty():
    assert runner._classify_bestof([]) == "none"


import json
from pathlib import Path
from web.backend import paths


def _setup(tmp_path, monkeypatch, slug="t"):
    monkeypatch.setattr(paths, "OUTPUT", tmp_path)
    monkeypatch.setitem(runner.JOBS, slug, {"status": "queued", "stage": 0, "log": [], "error": None})
    monkeypatch.setitem(runner.JOB_BOOKS, f"{slug}_full", {"id": f"{slug}_full", "status": "running", "stage": 0})
    return slug


def test_run_job_retries_until_deliverable(tmp_path, monkeypatch):
    slug = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("HIKI_WEB_BEST_OF", "3")
    reps = [{"deliverable": False, "交付门": ["死人复活"]}, {"deliverable": True, "cost_cny": 8}]
    forces = []
    async def fake_run(src, **k):
        forces.append(k.get("force")); return reps[len(forces) - 1]
    asyncio.run(runner._run_job(slug, tmp_path / "s.txt", run_fn=fake_run))
    assert runner.JOBS[slug]["status"] == "done"
    assert runner.JOBS[slug]["throws"] == 2
    assert forces == [False, True]
    bj = json.loads((tmp_path / f"{slug}_full" / "_bestof.json").read_text(encoding="utf-8"))
    assert bj["throws"] == 2 and bj["classification"] == "重掷救回"


def test_run_job_systematic_reject(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "sys")
    monkeypatch.setenv("HIKI_WEB_BEST_OF", "3")
    async def fake_run(src, **k): return {"deliverable": False, "交付门": ["死人复活"]}
    asyncio.run(runner._run_job("sys", tmp_path / "s.txt", run_fn=fake_run))
    assert runner.JOBS["sys"]["status"] == "rejected"
    assert runner.JOBS["sys"]["throws"] == 3
    bj = json.loads((tmp_path / "sys_full" / "_bestof.json").read_text(encoding="utf-8"))
    assert bj["classification"] == "系统性拒(全稿交付门拒)"


def test_run_job_no_retry_source_fatal(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "q")
    monkeypatch.setenv("HIKI_WEB_BEST_OF", "3")
    calls = []
    async def fake_run(src, **k): calls.append(1); return {"rejected": True, "reject_why": "暗黑"}
    asyncio.run(runner._run_job("q", tmp_path / "s.txt", run_fn=fake_run))
    assert len(calls) == 1
    assert runner.JOBS["q"]["status"] == "rejected"
