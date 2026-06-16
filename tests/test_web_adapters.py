"""web 后端适配器纯函数测试：真实产物映射 + fixture 兜底 + 统计 + slug。

不起服务、不打 API、不依赖 hiki 改写。运行：
    pytest tests/test_web_adapters.py
"""
import json

import pytest

from web.backend import adapters, fixtures, paths, runner


@pytest.fixture
def fake_output(tmp_path, monkeypatch):
    """把 paths.OUTPUT 指到临时目录，隔离真实 output/。"""
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setattr(paths, "OUTPUT", out)
    return out


def _write(d, name, obj):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


# ---------- fixture 兜底 ----------
def test_empty_output_falls_back_to_fixtures(fake_output):
    books = adapters.list_books()
    assert len(books) == len(fixtures.BOOKS)
    assert {b["id"] for b in books} == {b["id"] for b in fixtures.BOOKS}


def test_unknown_detail_is_empty_skeleton(fake_output):
    d = adapters.book_detail("does-not-exist")
    assert d["dna"] is None and d["gate"] is None and d["cost"] == []


def test_fixture_detail_served_by_id(fake_output):
    d = adapters.book_detail("hunyin")
    assert d["dna"] and d["review"]["total"] == 75


# ---------- 真实产物映射 ----------
def test_real_certified_dir(fake_output):
    d = fake_output / "mybook_full"
    _write(d, "report.json", {"deliverable": True, "cost_cny": 30, "source": "原书.txt"})
    _write(d, "grade.json", {"grade": "A", "mode": 1, "genre": "现代言情"})
    b = adapters.dir_to_book(d, {})
    assert b["status"] == "certified" and b["stage"] == 5
    assert b["grade"] == "A" and b["cost"] == 30 and b["slug"] == "mybook"
    assert b["real"] is True


def test_real_rejected_dir(fake_output):
    d = fake_output / "bad_full"
    _write(d, "report.json", {"rejected": True, "reject_why": "Q", "cost_cny": 1})
    _write(d, "grade.json", {"grade": "Q"})
    b = adapters.dir_to_book(d, {})
    assert b["status"] == "rejected"


def test_deliverable_false_is_rejected(fake_output):
    d = fake_output / "ng_full"
    _write(d, "report.json", {"deliverable": False, "交付门": ["维14死人复活"], "cost_cny": 8})
    b = adapters.dir_to_book(d, {})
    assert b["status"] == "rejected"


def test_stage_inference(fake_output):
    src_only = fake_output / "a_full"
    (src_only / "source").mkdir(parents=True)
    assert adapters._stage_from_artifacts(src_only, None) == 0

    bibled = fake_output / "b_full"
    _write(bibled, "bible.json", {"protagonist": {"name": "x"}})
    assert adapters._stage_from_artifacts(bibled, None) == 2

    planned = fake_output / "c_full"
    _write(planned, "plan.json", {"chapters": []})
    assert adapters._stage_from_artifacts(planned, None) == 3


def test_real_detail_overlay_dna_from_bible(fake_output):
    d = fake_output / "novel_full"
    _write(d, "bible.json", {"central_conflict": "豪门复仇", "genre": "都市",
                             "protagonist": {"name": "陆沉", "arc": "隐忍→张扬"}})
    _write(d, "report.json", {"deliverable": True, "cost_cny": 20})
    detail = adapters.book_detail("novel_full")
    labels = [x["label"] for x in detail["dna"]]
    assert any("spine" in l for l in labels)
    assert any("陆沉" in x["v"] for x in detail["dna"])


# ---------- 统计 ----------
def test_stats_counts(fake_output):
    books = fixtures.BOOKS
    s = adapters.stats(books)
    assert s["total"] == 8 and s["certified"] == 3
    assert s["rejectRate"] == "40%"            # 2 rejected / 5 finished
    assert s["budgetCap"] >= 1


# ---------- human index（真实 hfl.jsonl）----------
def test_human_index_real_file():
    idx = adapters.human_index()
    # human-eval-5 行带 slug
    assert idx.get("xianyan_tuihun") == 76.0
    assert idx.get("xingji_dalao") == 74.8


# ---------- runner slug ----------
def test_make_slug_strips_punct():
    s = runner.make_slug("霸总隐婚之偏偏宠我", "隐婚·偏偏宠我")
    assert s.startswith("霸总隐婚之偏偏宠我_隐婚偏偏宠我_")
    assert "·" not in s and " " not in s
