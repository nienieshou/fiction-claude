"""hiki run 批量引擎:tasks.yaml 解析 + out 映射 + 校验 + best-of-N 重掷。零 API(用 fake run_fn)。"""
import asyncio
import pytest
from pathlib import Path
from hiki import batch
from hiki.batch import load_tasks, Task, write_summary

_D = {"out": None, "chapters": 60, "chunks": 12, "candidates": 3,
      "refine_rounds": 5, "min_grade": None, "force": False}


def _write(tmp_path, text):
    f = tmp_path / "tasks.yaml"
    f.write_text(text, encoding="utf-8")
    return f


def test_load_tasks_out_slug_mapping(tmp_path):
    f = _write(tmp_path, "tasks:\n"
               "  - {slug: a, source: x/a.txt, out: output/new}\n"
               "  - {slug: b, source: x/b.txt, out: output/new}\n")
    ts = load_tasks(f, _D)
    assert [t.slug for t in ts] == ["a", "b"]
    assert ts[0].out_dir == Path("output/new/a") and ts[1].out_dir == Path("output/new/b")  # 同out不覆盖


def test_load_tasks_per_task_overrides(tmp_path):
    f = _write(tmp_path, "tasks:\n  - {slug: a, source: x.txt, out: o, candidates: 1, min_grade: A, force: true}\n")
    t = load_tasks(f, _D)[0]
    assert t.n_cand == 1 and t.min_grade == "A" and t.force is True
    assert t.n_ch == 60                                 # 未覆盖→取 default


def test_load_tasks_default_out(tmp_path):
    f = _write(tmp_path, "tasks:\n  - {slug: a, source: x.txt}\n")
    assert load_tasks(f, {**_D, "out": "myout"})[0].out_dir == Path("myout/a")


def test_load_tasks_dup_slug_rejected(tmp_path):
    f = _write(tmp_path, "tasks:\n  - {slug: a, source: x.txt}\n  - {slug: a, source: y.txt}\n")
    with pytest.raises(ValueError, match="slug 重复"):
        load_tasks(f, _D)


def test_load_tasks_missing_source_rejected(tmp_path):
    f = _write(tmp_path, "tasks:\n  - {slug: a}\n")
    with pytest.raises(ValueError, match="缺 source"):
        load_tasks(f, _D)


def test_load_tasks_yaml_typo_hint(tmp_path):
    # 用户的 `out:output/x` 缺空格 → 友好提示
    f = _write(tmp_path, "tasks:\n  - slug: a\n    source: x.txt\n    out:output/new\n")
    with pytest.raises(ValueError, match="冒号后缺空格"):
        load_tasks(f, _D)


def test_write_summary_aggregates(tmp_path):
    results = [
        {"slug": "a", "ok": True, "rejected": False, "cost_cny": 7.0, "out_chapters": 60, "交付门": ["通过"]},
        {"slug": "b", "ok": True, "rejected": True, "cost_cny": 6.0, "交付门": ["事件重演2处"]},
        {"slug": "c", "ok": False, "error": "Boom"},
    ]
    s = write_summary(results, 100.0, out_dir=tmp_path)
    assert s["任务数"] == 3 and s["成功"] == 2 and s["失败"] == 1
    assert s["可交付"] == 1 and s["拒收/不可交付"] == 1 and s["总成本_cny"] == 13.0
    assert (tmp_path / "batch_summary.md").exists() and (tmp_path / "batch_summary.json").exists()


# ---------- best-of-N 拒收即重掷 ----------
def test_should_retry_gate_reject():
    # 交付门拒(deliverable False, 非源头致命) → 重掷
    assert batch._should_retry({"deliverable": False}) is True


def test_should_retry_delivered():
    # 已交付 → 不重
    assert batch._should_retry({"deliverable": True}) is False


def test_should_retry_source_fatal():
    # 源头致命(Q/暗黑/min-grade: rejected=True) → 重掷无用,不重
    assert batch._should_retry({"rejected": True}) is False
    assert batch._should_retry({"deliverable": False, "rejected": True}) is False


def test_should_retry_no_signal():
    # 既非 deliverable False 也非 rejected(异常/缺字段) → 不重(保守)
    assert batch._should_retry({}) is False


def test_task_best_of_default():
    t = batch.Task(slug="x", source=Path("a"), out_dir=Path("o"))
    assert t.best_of == 1


def _task(tmp_path, best_of):
    src = tmp_path / "s.txt"; src.write_text("x", encoding="utf-8")
    return batch.Task(slug="t", source=src, out_dir=tmp_path / "o", best_of=best_of)


def test_one_retries_until_deliverable(tmp_path):
    # best_of=3, 前两稿交付门拒、第三稿可交付 → 3 throws, 终态可交付; 重掷用 force=True
    reps = [{"deliverable": False}, {"deliverable": False}, {"deliverable": True, "title": "ok"}]
    forces = []
    async def fake_run(*a, force=False, **k):
        forces.append(force); return reps[len(forces) - 1]
    res = asyncio.run(batch._one(asyncio.Semaphore(1), _task(tmp_path, 3), run_fn=fake_run))
    assert res["throws"] == 3 and res["rejected"] is False
    assert forces == [False, True, True]      # 首稿用 task.force(False), 重掷强制 force


def test_one_stops_on_first_deliverable(tmp_path):
    reps = [{"deliverable": True, "title": "ok"}]
    async def fake_run(*a, **k): return reps[0]
    res = asyncio.run(batch._one(asyncio.Semaphore(1), _task(tmp_path, 3), run_fn=fake_run))
    assert res["throws"] == 1 and res["rejected"] is False


def test_one_no_retry_on_source_fatal(tmp_path):
    calls = []
    async def fake_run(*a, **k): calls.append(1); return {"rejected": True}
    res = asyncio.run(batch._one(asyncio.Semaphore(1), _task(tmp_path, 3), run_fn=fake_run))
    assert res["throws"] == 1 and len(calls) == 1   # 源头致命不重掷


def test_one_exhausts_best_of_all_rejected(tmp_path):
    async def fake_run(*a, **k): return {"deliverable": False, "交付门": ["死人复活"]}
    res = asyncio.run(batch._one(asyncio.Semaphore(1), _task(tmp_path, 2), run_fn=fake_run))
    assert res["throws"] == 2 and res["rejected"] is True


def test_load_tasks_best_of(tmp_path):
    y = tmp_path / "t.yaml"
    y.write_text("tasks:\n  - slug: a\n    source: x.txt\n    best_of: 3\n  - slug: b\n    source: y.txt\n",
                 encoding="utf-8")
    defaults = {"out": "output", "chapters": 60, "chunks": 12, "candidates": 3,
                "refine_rounds": 5, "min_grade": None, "force": False, "best_of": 2}
    tasks = batch.load_tasks(y, defaults)
    assert tasks[0].best_of == 3      # per-task 覆盖
    assert tasks[1].best_of == 2      # 取 default
