"""point_repair.py 纯函数: _repair_delivery。零 API。TDD: 先红后绿。"""
from pathlib import Path
from hiki.point_repair import _repair_delivery


def test_repair_delivery_body_jia_format():
    """甲格式正文: 以《title》\\n\\n开头，无 # > --- 头。"""
    out_dir = Path("output") / "ZYGGY02252穿成萌娃_reval"
    write_path, stale, book = _repair_delivery(out_dir, "归隐田园：执子手共白头", "正文内容。", True)
    assert book.startswith("《归隐田园：执子手共白头》\n\n")
    assert book.endswith("正文内容。")
    assert "#" not in book.split("\n")[0]
    assert ">" not in book.split("\n")[0]
    assert "---" not in book.split("\n")[0]


def test_repair_delivery_no_title_bare_body():
    """无标题时 book_text == 输入正文（不加书名头）。"""
    out_dir = Path("output") / "ZYGGY02252穿成萌娃_reval"
    _, _, book = _repair_delivery(out_dir, "", "纯正文。", True)
    assert book == "纯正文。"


def test_repair_delivery_deliverable_routing():
    """可交付: write_path → _deliverable/; stale → _rejected/ 同名件。"""
    out_dir = Path("output") / "ZYGGY02252穿成萌娃_reval"
    write_path, stale, _ = _repair_delivery(out_dir, "归隐田园：执子手共白头", "x", True)
    # 源ID 直接拼接, 全角冒号保留
    assert write_path == out_dir.parent / "_deliverable" / "ZYGGY02252归隐田园：执子手共白头.txt"
    assert stale == out_dir / "_rejected" / "ZYGGY02252归隐田园：执子手共白头.txt"


def test_repair_delivery_rejected_routing():
    """不可交付: write_path → _rejected/; stale is None。"""
    out_dir = Path("output") / "ZYGGY02252穿成萌娃_reval"
    write_path, stale, _ = _repair_delivery(out_dir, "归隐田园：执子手共白头", "x", False)
    assert write_path == out_dir / "_rejected" / "ZYGGY02252归隐田园：执子手共白头.txt"
    assert stale is None
