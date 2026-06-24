import json
from pathlib import Path

from hiki.normalize import normalize_book, normalize_tree

OLD_MD = "ZYGGY02252_A_20260623_《归隐田园：执子手共白头》.md"


def _make_book(out_dir: Path, title="归隐田园：执子手共白头", deliverable=True,
               old_name=OLD_MD, final_text="第一章\n\n正文内容。") -> Path:
    """造一个旧命名成书目录: report.json + final.md + 旧 .md。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "final.md").write_text(final_text, encoding="utf-8")
    if old_name is not None:
        (out_dir / old_name).write_text("# 旧成书", encoding="utf-8")
    report = {"title": title, "deliverable": deliverable, "output_file": old_name or ""}
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return out_dir


def test_normalize_book_normalized(tmp_path):
    out_dir = _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    res = normalize_book(out_dir)
    assert res["status"] == "normalized"
    new_path = out_dir.parent / "_deliverable" / "ZYGGY02252归隐田园：执子手共白头.txt"
    assert new_path.exists()
    body = new_path.read_text(encoding="utf-8")
    assert body.startswith("《归隐田园：执子手共白头》\n\n")   # 甲格式
    assert "#" not in body.split("\n")[0]
    assert body.endswith("正文内容。")
    assert not (out_dir / OLD_MD).exists()                      # 旧 .md 删除
    rep = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert rep["output_file"] == str(new_path)                  # output_file 更新


def test_normalize_book_idempotent(tmp_path):
    out_dir = _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    normalize_book(out_dir)
    res2 = normalize_book(out_dir)
    assert res2["status"] == "already"


def test_normalize_book_skip_no_final(tmp_path):
    out_dir = _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    (out_dir / "final.md").unlink()
    res = normalize_book(out_dir)
    assert res["status"] == "skip-no-final"
    assert not (out_dir.parent / "_deliverable").exists()


def test_normalize_book_rejected_routing(tmp_path):
    out_dir = _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval", deliverable=False)
    res = normalize_book(out_dir)
    assert res["status"] == "normalized"
    assert (out_dir / "_rejected" / "ZYGGY02252归隐田园：执子手共白头.txt").exists()


def test_normalize_book_dry_run(tmp_path):
    out_dir = _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    res = normalize_book(out_dir, dry_run=True)
    assert res["status"] == "would-normalize"
    assert not (out_dir.parent / "_deliverable").exists()
    assert (out_dir / OLD_MD).exists()                          # 未动盘


def test_normalize_book_idempotent_abs_then_rel(tmp_path, monkeypatch):
    # web 用绝对根、CLI 用相对根 → output_file 字符串不同,不能误判未归一
    # (否则重复迁移会把刚写的已交付文件 unlink 掉 — 数据丢失)。
    book = _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    res1 = normalize_book(book)                      # 第一次:绝对路径(仿 web paths.OUTPUT)
    assert res1["status"] == "normalized"
    new_abs = Path(res1["path"])
    assert new_abs.exists()
    monkeypatch.chdir(tmp_path)                      # 第二次:相对路径(仿 CLI `hiki normalize output`)
    res2 = normalize_book(Path("ZYGGY02252穿成萌娃_reval"))
    assert res2["status"] == "already"              # 等价路径→已归一,不重迁
    assert new_abs.exists()                          # 已交付文件未被误删


def test_normalize_book_no_title_bare_body(tmp_path):
    # 无 title → 裸正文(无《》头),与 produce._stage_finalize / point_repair._repair_delivery 字节一致
    out_dir = _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval", title="")
    res = normalize_book(out_dir)
    assert res["status"] == "normalized"
    body = Path(res["path"]).read_text(encoding="utf-8")
    assert not body.startswith("《")
    assert body == "第一章\n\n正文内容。"


def test_normalize_tree_scans_and_skips(tmp_path):
    _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    (tmp_path / "_misc").mkdir()                                # 目录但无 report.json
    (tmp_path / "batch_summary.json").write_text("{}", encoding="utf-8")  # 非目录
    results = normalize_tree(tmp_path)
    statuses = {r["slug"]: r["status"] for r in results}
    assert statuses["ZYGGY02252穿成萌娃_reval"] == "normalized"
    assert statuses["_misc"] == "skip-no-report"
    assert "batch_summary.json" not in statuses                 # 非目录不计


def test_cli_normalize_dry_run(tmp_path, monkeypatch, capsys):
    import sys
    from hiki.__main__ import main
    _make_book(tmp_path / "ZYGGY02252穿成萌娃_reval")
    monkeypatch.setattr(sys, "argv", ["hiki", "normalize", str(tmp_path), "--dry-run"])
    main()
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "would-normalize" in out
    assert not (tmp_path / "_deliverable").exists()   # dry-run 不动盘
