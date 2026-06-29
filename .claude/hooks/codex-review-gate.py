#!/usr/bin/env python3
"""Stop hook: block turn-end when a spec/plan was written but not yet codex-peer-reviewed.

Reads Stop event payload from stdin. Scans the session transcript for recent
Write/Edit calls touching docs/superpowers/specs/ or docs/superpowers/plans/.
For each such file, checks for a `<!-- codex-peer-reviewed: ... -->` marker.
If any file lacks the marker, outputs {"decision":"block","reason":"..."} so
Claude is re-invoked with instructions to run the codex-peer-review skill.

Fail-open on any error (bad input, missing transcript, etc.) — never block
Stop on infra issues. Respects `stop_hook_active` to avoid loops.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

WATCHED_DIR_SUBSTRS = ("docs/superpowers/specs/", "docs/superpowers/plans/")
# Marker must carry all three fields the skill emits. This avoids false positives
# when a spec body discusses the marker format in prose or examples — only a real
# completed marker has timestamp+rounds+verdict together.
MARKER_RE = re.compile(
    r"<!--\s*codex-peer-reviewed:\s*\S+\s+rounds=\d+\s+verdict=\S+\s*-->",
    re.IGNORECASE,
)
WRITE_TOOLS = {"Write", "Edit"}
LOOKBACK_MESSAGES = 80  # scan tail of transcript
MARKER_TAIL_BYTES = 1024  # only look for marker in last N bytes of file (it's always appended at EOF)


def _iter_tool_uses(transcript_path: str):
    """Yield (tool_name, input_dict) tuples for assistant tool_use blocks
    in the tail of the transcript. Robust to malformed lines."""
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return

    for raw in lines[-LOOKBACK_MESSAGES:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # Real Claude Code transcript entries are: top-level {type:"assistant", message:{role,content[...]}}
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            tool = block.get("name", "")
            if tool not in WRITE_TOOLS:
                continue
            inp = block.get("input") or {}
            if isinstance(inp, dict):
                yield tool, inp


def _collect_spec_plan_paths(transcript_path: str, cwd: str) -> list[str]:
    """Find spec/plan absolute paths touched by Write/Edit in the transcript tail.
    De-dups, preserves most-recent-first order."""
    paths_in_order: list[str] = []
    seen: set[str] = set()
    for _tool, inp in _iter_tool_uses(transcript_path):
        fp = inp.get("file_path") or ""
        if not isinstance(fp, str) or not fp:
            continue
        fp_norm = fp.replace("\\", "/")  # Windows: match watched substrs against / paths
        if not any(sub in fp_norm for sub in WATCHED_DIR_SUBSTRS):
            continue
        abs_fp = fp if os.path.isabs(fp) else os.path.normpath(os.path.join(cwd, fp))
        if abs_fp in seen:
            continue
        seen.add(abs_fp)
        paths_in_order.append(abs_fp)
    # Most-recent-first: transcript is chronological, so reverse
    paths_in_order.reverse()
    return paths_in_order


def _has_marker(path: str) -> bool:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > MARKER_TAIL_BYTES:
                f.seek(size - MARKER_TAIL_BYTES)
            tail = f.read().decode("utf-8", errors="replace")
        return bool(MARKER_RE.search(tail))
    except OSError:
        # If we can't read the file, treat as reviewed to avoid spurious blocks.
        return True


def _format_block_reason(unreviewed: list[str]) -> str:
    head = unreviewed[0]
    extra = ""
    if len(unreviewed) > 1:
        rest = "\n".join(f"  - {p}" for p in unreviewed[1:])
        extra = f"\n\nOther unreviewed files in this turn:\n{rest}"
    return (
        f"Codex peer review pending.\n\n"
        f"A spec/plan was written in this turn but has not been peer-reviewed by Codex yet:\n"
        f"  {head}{extra}\n\n"
        f"Invoke the `codex-peer-review` skill (Skill tool) now and review this file before ending the turn. "
        f"The skill runs an iterative single-thread dialogue with Codex (round 1 fresh, rounds 2+ via `codex exec ... resume <session-id> ...`) until Codex returns `## Verdict\\nAPPROVED` — no round cap, pushbacks require explicit codex CONCEDE. Then appends a `<!-- codex-peer-reviewed: ... -->` marker that this hook recognizes.\n\n"
        f"If you've already completed the review in conversation but forgot to write the marker, just append it manually:\n"
        f"  cat >> {head} <<'M'\n"
        f"  <!-- codex-peer-reviewed: $(date -u +%Y-%m-%dT%H:%M:%SZ) rounds=<N> verdict=approved -->\n"
        f"  M"
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # fail-open
    if not isinstance(payload, dict):
        return 0

    # Loop guard: if Claude Code already retried after a previous block, give up.
    if payload.get("stop_hook_active"):
        return 0

    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not os.path.exists(transcript_path):
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        cwd = os.getcwd()

    touched = _collect_spec_plan_paths(transcript_path, cwd)
    if not touched:
        return 0

    unreviewed = [p for p in touched if os.path.exists(p) and not _has_marker(p)]
    if not unreviewed:
        return 0

    print(json.dumps({"decision": "block", "reason": _format_block_reason(unreviewed)}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Absolute fail-open. Never let a bug here brick the user's session.
        sys.exit(0)
