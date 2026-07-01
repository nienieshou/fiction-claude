# src/hiki/predraft.py
"""PreDraft Review v0.5: 预起草门(接线 produce.run)。只硬拦 det 章节复制 + 出处硬化。
见 docs/superpowers/specs/2026-07-01-predraft-review-v05-design.md。
注:与 scripts/predraft_checks.py(校准工具)分离——本模块供 produce.py import。"""
from __future__ import annotations

import copy

PREDRAFT_MAX_PLAN_REGEN = 2
UNSOURCED_RATIO_MAX = 0.5


def _chapter_source_indices(ch, n_scenes):
    """该章 scenes 的 source_scene_index → (有效索引集, unsourced 数, 总数)。
    有效 = int 且 0<=idx<n_scenes;缺失/None/-1/越界 = unsourced。"""
    valid, unsourced, total = set(), 0, 0
    for sc in (ch.get("scenes") or []):
        if not isinstance(sc, dict):
            continue
        total += 1
        v = sc.get("source_scene_index")
        if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < n_scenes:
            valid.add(v)
        else:
            unsourced += 1
    return valid, unsourced, total


def predraft_gate_check(plan, scenes) -> dict:
    chapters = (plan or {}).get("chapters") or []
    n_scenes = len(scenes or [])
    per_ch = [_chapter_source_indices(ch if isinstance(ch, dict) else {}, n_scenes) for ch in chapters]
    findings, dup_pairs, unsourced_chapters = [], [], []
    # 章节复制: 不同章共享有效 source_scene_index
    for a in range(len(per_ch)):
        for b in range(a + 1, len(per_ch)):
            shared = per_ch[a][0] & per_ch[b][0]
            if shared:
                dup_pairs.append({"ch": [a, b], "shared": sorted(shared)})
                findings.append({"category": "章节复制/注水", "severity": "hard",
                                 "evidence_path": f"plan.chapters[{a}|{b}].scenes[].source_scene_index",
                                 "contradiction": f"第{a}章与第{b}章共享源场景 {sorted(shared)}(同源被拆多章)"})
    # unsourced 躲避信号(warn)
    for i, (valid, unsourced, total) in enumerate(per_ch):
        if total and unsourced / total > UNSOURCED_RATIO_MAX:
            unsourced_chapters.append(i)
            findings.append({"category": "章节复制/注水", "severity": "warn",
                             "evidence_path": f"plan.chapters[{i}].scenes[].source_scene_index",
                             "contradiction": f"第{i}章 unsourced 占比{unsourced}/{total}>{UNSOURCED_RATIO_MAX}(疑用 -1/越界躲检测)"})
    blocked = any(f["severity"] == "hard" for f in findings)
    return {"blocked": blocked, "findings": findings,
            "evidence": {"dup_pairs": dup_pairs, "unsourced_chapters": unsourced_chapters}}
