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
def test_empty_output_returns_empty(fake_output):
    # 无真实产物 → 空列表（不再回退 demo）
    assert adapters.list_books() == []


def test_list_books_newest_first(fake_output):
    import os
    for name in ("a_full", "b_full", "c_full"):
        _write(fake_output / name, "bible.json", {"protagonist": {"name": "x"}})
    base = 1_000_000.0
    os.utime(fake_output / "a_full", (base, base))            # 最旧
    os.utime(fake_output / "b_full", (base + 10, base + 10))
    os.utime(fake_output / "c_full", (base + 20, base + 20))  # 最新
    ids = [b["id"] for b in adapters.list_books()]
    assert ids == ["c_full", "b_full", "a_full"]


def test_list_books_uploads_pinned_top(fake_output):
    _write(fake_output / "old_full", "bible.json", {"protagonist": {"name": "x"}})
    stub = {"id": "new_full", "title": "新上传", "slug": "new", "uploaded": True,
            "src": "x", "genre": "—", "grade": "—", "comp": "—", "stage": 0,
            "status": "running", "mode": 0, "human": None, "cost": 0}
    ids = [b["id"] for b in adapters.list_books(job_books=[stub])]
    assert ids[0] == "new_full"     # 刚上传置顶


def test_unknown_detail_is_empty_skeleton(fake_output):
    d = adapters.book_detail("does-not-exist")
    assert d["dna"] is None and d["gate"] is None and d["cost"] == []


def test_fixture_detail_served_by_id(fake_output):
    d = adapters.book_detail("hunyin")
    assert d["dna"] and d["review"]["total"] == 75


# ---------- 真实产物映射 ----------
def test_real_certified_dir(fake_output):
    d = fake_output / "mybook_full"
    _write(d, "report.json", {"deliverable": True, "cost_cny": 30, "source": "原书.txt",
                              "seconds": 1254.3, "calls": 704})
    _write(d, "grade.json", {"grade": "A", "mode": 1, "genre": "现代言情"})
    b = adapters.dir_to_book(d, {})
    assert b["status"] == "certified" and b["stage"] == 5
    assert b["grade"] == "A" and b["cost"] == 30 and b["slug"] == "mybook"
    assert b["real"] is True
    assert b["seconds"] == 1254.3 and b["calls"] == 704


def test_real_mode_string_maps_to_int(fake_output):
    # grade.json.mode 是中文串(mining._GRADE_MODE) → 须映射到原型 mode int
    d = fake_output / "md_full"
    _write(d, "report.json", {"deliverable": True, "cost_cny": 10})
    _write(d, "grade.json", {"grade": "B", "mode": "强化改写"})
    assert adapters.dir_to_book(d, {})["mode"] == 2
    _write(d, "grade.json", {"grade": "A", "mode": "保真压缩"})
    assert adapters.dir_to_book(d, {})["mode"] == 1


def test_real_rejected_dir(fake_output):
    d = fake_output / "bad_full"
    _write(d, "report.json", {"rejected": True, "reject_why": "Q", "cost_cny": 1})
    _write(d, "grade.json", {"grade": "Q"})
    b = adapters.dir_to_book(d, {})
    assert b["status"] == "rejected"


def test_rejected_book_exposes_reject_reason(fake_output):
    d = fake_output / "rej_full"
    _write(d, "report.json", {"deliverable": False, "交付门": ["事实表死人复活1处(verify确认)"], "cost_cny": 2})
    b = adapters.dir_to_book(d, {})
    assert b["status"] == "rejected"
    assert "死人复活" in (b.get("reject_reason") or "")


def test_q_rejected_uses_reject_why(fake_output):
    d = fake_output / "q_full"
    _write(d, "report.json", {"rejected": True, "reject_why": "暗黑比≥0.4→Q拒收", "cost_cny": 1})
    b = adapters.dir_to_book(d, {})
    assert b["status"] == "rejected" and "Q拒收" in (b.get("reject_reason") or "")


def test_deliverable_false_is_rejected(fake_output):
    d = fake_output / "ng_full"
    _write(d, "report.json", {"deliverable": False, "交付门": ["维14死人复活"], "cost_cny": 8})
    b = adapters.dir_to_book(d, {})
    assert b["status"] == "rejected"


def test_source_only_dir_is_idle_not_running(fake_output):
    # 只有 source/ 的目录 = ingest 已完成且无活跃任务 → idle(待产)，不是 running(进行中)
    d = fake_output / "stale_full"
    (d / "source").mkdir(parents=True)
    b = adapters.dir_to_book(d, {}, active=frozenset())
    assert b["status"] == "idle"


def test_source_only_with_live_job_is_running(fake_output):
    # 有活跃后台任务 → running
    d = fake_output / "live_full"
    (d / "source").mkdir(parents=True)
    b = adapters.dir_to_book(d, {}, active=frozenset({"live"}))
    assert b["status"] == "running"


def test_production_started_no_job_is_stalled(fake_output):
    # 已产出 bible 但无 report 且无活跃任务 → stalled(中断,被打断)
    d = fake_output / "mid_full"
    _write(d, "bible.json", {"protagonist": {"name": "x"}})
    (d / "source").mkdir(parents=True)
    assert adapters.dir_to_book(d, {}, active=frozenset())["status"] == "stalled"


def test_production_started_with_job_is_running(fake_output):
    # 已产出 bible 且有活跃任务 → running
    d = fake_output / "mid2_full"
    _write(d, "bible.json", {"protagonist": {"name": "x"}})
    assert adapters.dir_to_book(d, {}, active=frozenset({"mid2"}))["status"] == "running"


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


def test_real_scenes_from_plan(fake_output):
    d = fake_output / "sc_full"
    _write(d, "plan.json", {"chapters": [
        {"index": 1, "title": "开场", "scenes": [{"mode": "DRAMATIZE"}]},
        {"index": 2, "title": "过渡", "scenes": [{"mode": "SUMMARIZE"}]}]})
    _write(d, "macro.json", {"chapters": [
        {"i": 1, "act": "开篇", "beat": "主角登场打脸"},
        {"i": 2, "act": "发展", "beat": "三月后过渡"}]})
    detail = adapters.book_detail("sc_full")
    assert detail["scenes"] is not None
    assert detail["scenes"]["total"] == 2
    assert detail["scenes"]["list"][0]["type"] == "DRAMATIZE"
    assert "打脸" in detail["scenes"]["list"][0]["beat"]


def test_real_spine_from_bible(fake_output):
    d = fake_output / "sp_full"
    _write(d, "bible.json", {
        "protagonist": {"name": "王亦初", "identity": "村医"},
        "characters": [{"name": "白芷莹", "role": "女主播"}],
        "places": [{"name": "大王村", "aliases": []}],
        "power_system": "练气→筑基→金丹"})
    detail = adapters.book_detail("sp_full")
    assert detail["spine"] is not None
    groups = {g["group"]: g for g in detail["spine"]}
    assert "人物登记" in groups
    names = [it["name"] for it in groups["人物登记"]["items"]]
    assert "王亦初" in names and "白芷莹" in names


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


# ---------- delete: 删产出目录但绝不删已跟踪库内源 ----------
def test_delete_book_removes_output_keeps_library_source(fake_output, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from web.backend import app as appmod

    srcdir = tmp_path / "fictions_source"
    srcdir.mkdir()
    monkeypatch.setattr(paths, "SOURCES", srcdir)

    d = fake_output / "delme_full"
    (d / "source").mkdir(parents=True)
    (d / "source" / "clean.txt").write_text("x", encoding="utf-8")
    libfile = srcdir / "delme.txt"          # 库内源(非 _uploads)
    libfile.write_text("y", encoding="utf-8")

    client = TestClient(appmod.app)
    assert "delme_full" in [b["id"] for b in client.get("/api/books").json()]

    r = client.delete("/api/books/delme_full")
    assert r.status_code == 200
    body = r.json()
    assert body["output_removed"] is True
    assert body["source_removed"] is None       # 不删已跟踪库内源
    assert not d.exists() and libfile.exists()   # 库内源保留
    assert "delme_full" not in [b["id"] for b in client.get("/api/books").json()]


def test_delete_unknown_book_404(fake_output):
    from fastapi.testclient import TestClient
    from web.backend import app as appmod
    r = TestClient(appmod.app).delete("/api/books/does-not-exist")
    assert r.status_code == 404


# ---------- 产物下载: 中文 slug 不得让 Content-Disposition 头 latin-1 编码崩(500) ----------
def test_download_generated_artifact_with_cjk_slug(fake_output):
    # 拒收本只生成 diagnostic.json/cost_ledger.json(无真实文件)→ 走手搓 Response 头路径。
    # slug 含中文时,旧代码把原始中文塞进 Content-Disposition → starlette latin-1 编码 500。
    from fastapi.testclient import TestClient
    from web.backend import app as appmod

    bid = "ZTGGX02751听说我死后成了反派白月光_20260617_full"
    d = fake_output / bid
    _write(d, "report.json", {"deliverable": False, "交付门": ["维14死人复活"], "cost_cny": 2})
    _write(d, "grade.json", {"grade": "A"})

    client = TestClient(appmod.app)
    for name in ("diagnostic.json", "cost_ledger.json"):
        r = client.get(f"/api/books/{bid}/artifacts/{name}")
        assert r.status_code == 200, f"{name}: {r.status_code}"
        cd = r.headers["content-disposition"]
        cd.encode("latin-1")                       # 头必须 latin-1 可编码,否则 ASGI 崩
        assert "filename*=utf-8''" in cd.lower()    # RFC 5987 带中文文件名


def test_content_disposition_is_latin1_safe():
    from web.backend import app as appmod
    cd = appmod._content_disposition("反派白月光_20260617.diagnostic.json")
    cd.encode("latin-1")                            # 不抛 UnicodeEncodeError
    assert "filename*=utf-8''" in cd.lower()


def test_upload_dedupes_against_library(monkeypatch, tmp_path):
    lib = tmp_path / "fictions_source"
    lib.mkdir()
    monkeypatch.setattr(paths, "SOURCES", lib)
    monkeypatch.setattr(runner, "UPLOAD_DIR", lib / "_uploads")
    (lib / "原书.txt").write_bytes(b"hello world content")
    p = runner._resolve_src("原书", "新名", b"hello world content")   # 同内容
    assert p == lib / "原书.txt"                                      # 复用库内源
    assert not (lib / "_uploads").exists()                           # 未写副本


def test_upload_new_content_goes_to_staging(monkeypatch, tmp_path):
    lib = tmp_path / "fictions_source"
    lib.mkdir()
    monkeypatch.setattr(paths, "SOURCES", lib)
    monkeypatch.setattr(runner, "UPLOAD_DIR", lib / "_uploads")
    p = runner._resolve_src("新书", "新书", b"brand new content")
    assert (lib / "_uploads") in p.parents and p.exists()            # 落暂存区
    assert list(lib.glob("*.txt")) == []                             # 库根未被污染


def test_make_slug_strips_punct():
    s = runner.make_slug("霸总隐婚之偏偏宠我", "隐婚·偏偏宠我")
    assert s.startswith("霸总隐婚之偏偏宠我_隐婚偏偏宠我_")
    assert "·" not in s and " " not in s


def test_quality_config_is_quality_first():
    # 行之有效·质量优先：Spine 开 + 精修 3 轮 + 候选 3（见 fact_spine.md M2）
    assert runner.QUALITY == {"spine": True, "refine_rounds": 3, "n_cand": 3}


def test_make_slug_collapses_when_not_renamed():
    # 未改名（新==源）→ 源名_date，不再 名_名_date
    same = runner.make_slug("极品全能小村医", "极品全能小村医")
    assert same.startswith("极品全能小村医_") and same.count("极品全能小村医") == 1
    empty = runner.make_slug("某本", "")
    assert empty.startswith("某本_") and empty.count("某本") == 1
