# scripts/predraft_checks.py
"""PreDraft Review v0 确定性预检: 启发式正则解析 bible/plan 的 prose 模式 → findings。
非 typed schema(codex 实证: 亲属在 key_relation prose, 重复章看 scenes source_scene_index)。
不调 API。见 docs/superpowers/specs/2026-06-30-predraft-review-v0-design.md。"""
from __future__ import annotations

import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

_KINSHIP_ROLES = {"亲生母亲": "母", "亲生父亲": "父", "生母": "母", "生父": "父"}
_KIN_RE = re.compile(r"(.+?)(亲生母亲|亲生父亲|生母|生父)")


def _finding(category, severity, evidence_path, contradiction, confidence, parse_pattern):
    return {"category": category, "severity": severity, "evidence_path": evidence_path,
            "contradiction": contradiction, "confidence": confidence, "parse_pattern": parse_pattern}


def kinship_uniqueness(bible) -> list[dict]:
    chars = (bible or {}).get("characters") or []
    # (目标人, 归一角色) -> set(claimant 名)
    claims: dict = {}
    for i, c in enumerate(chars):
        if not isinstance(c, dict):
            continue
        kr = c.get("key_relation")
        name = c.get("name")
        if not isinstance(kr, str) or not name:
            continue
        m = _KIN_RE.match(kr.strip())
        if not m:
            continue
        target = m.group(1).strip("的 ，,、").strip()
        role = _KINSHIP_ROLES[m.group(2)]
        if target:
            claims.setdefault((target, role), set()).add(name)
    out = []
    for (target, role), claimants in sorted(claims.items()):
        if len(claimants) >= 2:
            who = "、".join(sorted(claimants))
            out.append(_finding(
                "混名/认亲矛盾", "hard", "characters[].key_relation",
                f"{who} 都被标为「{target}」的{role}(生身唯一角色被多人声称)",
                "det", "key_relation~生母/生父"))
    return out
