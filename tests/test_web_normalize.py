import json
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
