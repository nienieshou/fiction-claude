"""hiki run 批量引擎:tasks.yaml 解析 + out 映射 + 校验。零 API。"""
import pytest
from pathlib import Path
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
