"""P0 Ingest · 一等清洗管线（FR-1，纯确定性，0-LLM）。

输入任意 txt → clean.txt + IngestMeta。去防盗章/广告/作者的话、编码修复、
章节切分、去重、多书拼接检测。万本规模真翻车点（A7 便宜早筛）。
"""
from __future__ import annotations
import re
from pathlib import Path
from . import config
from .schemas import IngestMeta

_CFG = config.load("pipeline")["ingest"]
_CHAPTER_RE = re.compile(_CFG["chapter_regex"])
_JUNK_RE = re.compile("|".join(f"(?:{p})" for p in _CFG["junk_line_patterns"]))
_FIRST_CH_RE = re.compile(r"第\s*[一1]\s*[章回]")


def detect_encoding(raw: bytes) -> tuple[str, str]:
    """按配置顺序试解码，返回 (encoding, text)。"""
    for enc in _CFG["encodings"]:
        try:
            return enc, raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8(replace)", raw.decode("utf-8", errors="replace")


def clean(text: str) -> tuple[list[str], dict]:
    """逐行清洗。返回 (干净行, 统计)。"""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    gc = _CFG["garbage_char"]
    garbage = text.count(gc)
    text = text.replace(gc, "")
    removed, out, prev = 0, [], None
    for line in text.split("\n"):
        s = line.strip()
        if s and _JUNK_RE.search(s):
            removed += 1
            continue
        if s and s == prev:          # 去连续重复行
            continue
        out.append(line)
        prev = s
    # 压缩连续空行
    compact, blank = [], False
    for line in out:
        if not line.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        compact.append(line)
    return compact, {"removed_junk_lines": removed, "garbage_chars": garbage}


def split_chapters(lines: list[str]) -> list[tuple[str, str]]:
    """按章标题切分，返回 [(标题, 正文)]。无标题则整体为一章。"""
    chapters, title, body = [], None, []
    for line in lines:
        if _CHAPTER_RE.match(line):
            if title is not None or body:
                chapters.append((title or "(前言)", "\n".join(body).strip()))
            title, body = line.strip(), []
        else:
            body.append(line)
    if title is not None or body:
        chapters.append((title or "(全文)", "\n".join(body).strip()))
    return chapters


def ingest(src: str | Path, out_dir: str | Path) -> IngestMeta:
    """P0 主入口：清洗 + 切分 + 元数据，落盘 clean.txt / meta.json（A1 文件即状态）。"""
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()
    enc, text = detect_encoding(raw)
    raw_chars = len(text)
    lines, stats = clean(text)
    chapters = split_chapters(lines)
    body_chapters = [c for c in chapters if c[0] not in ("(前言)", "(全文)")]
    min_chars = _CFG["min_chapter_chars"]
    short = sum(1 for _, b in body_chapters if len(b) < min_chars)
    splice = len(_FIRST_CH_RE.findall("\n".join(c[0] for c in chapters))) > 1

    clean_text = "\n\n".join(f"{t}\n{b}" if b else t for t, b in chapters)
    (out_dir / "clean.txt").write_text(clean_text, encoding="utf-8")
    notes = []
    if splice:
        notes.append("疑似多书拼接（多个'第一章'）→ 需边界确认")
    if short:
        notes.append(f"{short} 个过短章（<{min_chars}字）→ 可疑")

    meta = IngestMeta(
        source_path=str(src), encoding=enc, raw_chars=raw_chars,
        clean_chars=len(clean_text), approx_wan_zi=round(len(clean_text) / 10000, 1),
        chapter_count=len(body_chapters), removed_junk_lines=stats["removed_junk_lines"],
        garbage_chars=stats["garbage_chars"], short_chapters=short,
        suspected_splice=splice, notes=notes,
    )
    (out_dir / "meta.json").write_text(meta.to_json(), encoding="utf-8")
    return meta
