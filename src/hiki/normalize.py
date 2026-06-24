"""成书命名归一 normalize: 把新命名上线前产出的旧书零成本迁移到新规范。
读 report.json + final.md → 重写 <源ID><新书名>.txt 落 _deliverable/(或 _rejected/),删旧 .md。
不重跑、不调 LLM、幂等可重入。

用法: PYTHONPATH=src python -m hiki normalize [output根,默认 output] [--dry-run]
"""
from __future__ import annotations

import json
from pathlib import Path

from .produce import _book_filename, _delivery_path, _safe_filename


def normalize_book(out_dir: Path, dry_run: bool = False) -> dict:
    """归一单本: 读 report.json+final.md → 写新命名交付件,删旧 .md,更新 output_file。
    幂等(已归一→already);缺 report/final → skip;按 deliverable 分流。返回 {slug,status,path?}。"""
    slug = out_dir.name
    rep_path = out_dir / "report.json"
    try:
        report = json.loads(rep_path.read_text(encoding="utf-8"))
    except Exception:
        return {"slug": slug, "status": "skip-no-report"}
    if not isinstance(report, dict):
        return {"slug": slug, "status": "skip-no-report"}
    raw_title = report.get("title") or ""          # 与 produce._stage_finalize 同构:空 title→裸正文
    deliverable = bool(report.get("deliverable"))
    final_path = out_dir / "final.md"
    if not final_path.exists():
        return {"slug": slug, "status": "skip-no-final"}
    safe = _safe_filename(raw_title, fallback=_safe_filename(slug))
    out_name = _book_filename(slug, safe)
    new_path = _delivery_path(out_dir, deliverable, out_name)
    prev = report.get("output_file")                   # 比较用 resolve():绝对(web)/相对(CLI)表示等价才算幂等
    if new_path.exists() and prev and Path(prev).resolve() == new_path.resolve():
        return {"slug": slug, "status": "already", "path": str(new_path)}
    if dry_run:
        return {"slug": slug, "status": "would-normalize", "path": str(new_path)}
    final_text = final_path.read_text(encoding="utf-8")
    body = f"《{raw_title}》\n\n{final_text}" if raw_title else final_text
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(body, encoding="utf-8")
    if prev:                                            # 只认 output_file 指向的旧文件,不猜测
        old_path = out_dir / prev                       # prev 绝对时 / 运算返回该绝对路径
        if old_path.exists() and old_path.resolve() != new_path.resolve():  # resolve 防误删刚写的同一文件
            old_path.unlink()
    report["output_file"] = str(new_path)
    rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"slug": slug, "status": "normalized", "path": str(new_path)}


def normalize_tree(output_root: Path, dry_run: bool = False) -> list[dict]:
    """遍历 output_root 直接子目录(只扫一层),逐本 normalize_book,收集结果。"""
    if not output_root.is_dir():
        return []
    return [normalize_book(p, dry_run) for p in sorted(output_root.iterdir()) if p.is_dir()]
