import json
import pytest
from pathlib import Path


def _make_old_book(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "final.md").write_text("第一章\n\n正文内容。", encoding="utf-8")
    old = "ZYGGY02252_A_20260623_《归隐田园：执子手共白头》.md"
    (out_dir / old).write_text("# 旧成书", encoding="utf-8")
    (out_dir / "report.json").write_text(
        json.dumps({"title": "归隐田园：执子手共白头", "deliverable": True, "output_file": old},
                   ensure_ascii=False), encoding="utf-8")
    return out_dir


def test_web_normalize_hook_runs(tmp_path, monkeypatch):
    from web.backend import app, paths
    _make_old_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    monkeypatch.setattr(paths, "OUTPUT", tmp_path)
    monkeypatch.setenv("HIKI_WEB_NORMALIZE", "1")
    app._normalize_books()
    assert (tmp_path / "_deliverable" / "ZYGGY02252归隐田园：执子手共白头.txt").exists()


def test_web_normalize_hook_disabled(tmp_path, monkeypatch):
    from web.backend import app, paths
    _make_old_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    monkeypatch.setattr(paths, "OUTPUT", tmp_path)
    monkeypatch.setenv("HIKI_WEB_NORMALIZE", "0")
    app._normalize_books()
    assert not (tmp_path / "_deliverable").exists()   # 关闭→不动盘


def test_output_dirs_skips_delivery_aggregate(tmp_path, monkeypatch):
    # 归一产生的 _deliverable/_rejected 不应被书目发现误当成书(即便其下有像书的子目录)
    from web.backend import paths
    book = tmp_path / "ZYGGY02079买来_reval"
    book.mkdir()
    (book / "report.json").write_text("{}", encoding="utf-8")
    fake = tmp_path / "_deliverable" / "somebook"
    fake.mkdir(parents=True)
    (fake / "report.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "OUTPUT", tmp_path)
    names = [p.name for p in paths.output_dirs()]
    assert "ZYGGY02079买来_reval" in names
    assert "somebook" not in names


@pytest.fixture
def fake_output(tmp_path, monkeypatch):
    from web.backend import paths
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setattr(paths, "OUTPUT", out)
    return out


def test_dir_to_book_crash_is_failed(tmp_path):
    from web.backend import adapters
    d = tmp_path / "Xcrash_full"
    d.mkdir()
    (d / "bible.json").write_text("{}", encoding="utf-8")        # produce 已开产
    (d / "_crash.txt").write_text("boom", encoding="utf-8")      # 但崩了,无 report.json
    b = adapters.dir_to_book(d, {}, frozenset())
    assert b["status"] == "failed"


def test_dir_to_book_report_wins_over_stale_crash(tmp_path):
    from web.backend import adapters
    d = tmp_path / "Xok_full"
    d.mkdir()
    (d / "_crash.txt").write_text("old boom", encoding="utf-8")  # 崩后续跑成功,crash 残留
    (d / "report.json").write_text('{"deliverable": true}', encoding="utf-8")
    b = adapters.dir_to_book(d, {}, frozenset())
    assert b["status"] == "certified"                            # report 优先,非 failed


def test_resume_endpoint_allows_failed(fake_output, monkeypatch):
    from fastapi.testclient import TestClient
    from web.backend import app as appmod, runner
    d = fake_output / "Xfail_full"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bible.json").write_text("{}", encoding="utf-8")
    (d / "_crash.txt").write_text("boom", encoding="utf-8")
    (d / "source").mkdir()
    (d / "source" / "clean.txt").write_text("x", encoding="utf-8")

    async def fake_resume(slug):                                  # 不真跑 produce
        return {"job_slug": slug, "resumed": True}
    monkeypatch.setattr(runner, "resume", fake_resume)

    client = TestClient(appmod.app)
    assert client.get("/api/books").json()                       # 触发 list(失败本应在内,status=failed)
    r = client.post("/api/books/Xfail_full/resume")
    assert r.status_code == 200                                  # failed 被放行(不再 400)
