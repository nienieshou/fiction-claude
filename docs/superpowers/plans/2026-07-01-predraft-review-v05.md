# PreDraft Review v0.5 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** 把预起草门接进 `produce.run`:只硬拦 det `章节复制` → plan-regen(≤2)→ 仍拦搁置(跳起草)。核心逻辑在**可测纯/半纯 helper**,run() 手术最小化 + happy-path 字节保真。

**Architecture:** 新 `src/hiki/predraft.py`(produce 可 import;不同于 scripts/ 校准工具):`predraft_gate_check(plan, scenes)`(纯)+ `predraft_gate_loop(...)`(async,注入 plan_fn,可测 regen/搁置决策)。`produce.run` 只加:快照 bible_mined + 调 loop + 搁置/draft_force。

**Tech Stack:** Python 3;pytest;`python -m pytest`(勿 PYTHONPATH=src);中文注释。

## Global Constraints
- spec:`docs/superpowers/specs/2026-07-01-predraft-review-v05-design.md`(codex approved rounds=2)。逐条实现。
- **只硬拦 det `章节复制`**(shared `source_scene_index`);LLM 类目**不接线**。
- **happy-path 字节保真**:gate 不 blocked 的书**照原路径**进 `_stage_draft`(同 plan/bible/force)。
- **codex 修正(必守)**:regen 每次从 `copy.deepcopy(bible_mined)` 重规划(隔离 `_stage_plan` 的 `enrich_places` 污染);`draft_force = force or regens>0`(防复用旧 `draft/ch_NN.md`);refresh 全部 run() locals(plan/beats/ordered/n_scenes/macro/_ps)。
- **schema 容错**:plan 缺 scenes/source_scene_index → 不 blocked、不崩。
- 不硬拦 LLM 类目、不做 bible-rooted regen、不改末端门、不动冻结向量/gold。
- 全量 `pytest -m 'not api'` 绿;SDD。

## File Structure
- `src/hiki/predraft.py` — `predraft_gate_check`、`predraft_gate_loop`、`PREDRAFT_MAX_PLAN_REGEN`、`UNSOURCED_RATIO_MAX`。
- `tests/test_predraft_gate.py` — 纯/半纯单测。
- `src/hiki/produce.py` — `_predraft_shelved_report` + `run()` 接线。
- `tests/test_predraft_wiring.py` — run() 搁置路径测(monkeypatch stages)。

---

### Task 1: `predraft_gate_check`(纯,det 章节复制 + 出处硬化)

**Files:**
- Create: `src/hiki/predraft.py`
- Test: `tests/test_predraft_gate.py`

**Interfaces:**
- Produces:
  - `PREDRAFT_MAX_PLAN_REGEN = 2`、`UNSOURCED_RATIO_MAX = 0.5`
  - `predraft_gate_check(plan, scenes) -> dict`:`{"blocked":bool, "findings":[{category,severity,evidence_path,contradiction}], "evidence":{"dup_pairs":[...], "unsourced_chapters":[...]}}`。
    - **章节复制(hard→blocked)**:不同 plan 章共享同一有效 `source_scene_index`(0≤idx<len(scenes))→ 每对一 finding(severity="hard")。
    - **unsourced(warn)**:某章 scene 的 `source_scene_index` 缺失/None/-1/越界 占该章比例 > `UNSOURCED_RATIO_MAX` → finding(severity="warn")。
    - `blocked` = 有 hard finding。plan 缺 `chapters`/`scenes` → blocked=False、不崩。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_predraft_gate.py
from hiki.predraft import predraft_gate_check, PREDRAFT_MAX_PLAN_REGEN


def _plan(chapter_idxs):
    # chapter_idxs: 每章的 source_scene_index 列表
    return {"chapters": [{"scenes": [{"source_scene_index": i} for i in idxs]} for idxs in chapter_idxs]}


SCENES = [{"t": i} for i in range(20)]   # len=20


def test_gate_block_on_shared_source():
    g = predraft_gate_check(_plan([[5, 6], [6, 7]]), SCENES)   # ch0∩ch1={6}
    assert g["blocked"] is True
    assert any(f["severity"] == "hard" and f["category"] == "章节复制/注水" for f in g["findings"])
    assert "6" in str(g["evidence"]["dup_pairs"])


def test_gate_no_block_no_share():
    g = predraft_gate_check(_plan([[1, 2], [3, 4]]), SCENES)
    assert g["blocked"] is False


def test_gate_unsourced_warn_not_block():
    # 某章全 -1/越界 → unsourced 100% > 阈 → warn, 不 blocked
    g = predraft_gate_check(_plan([[-1, 99], [3, 4]]), SCENES)
    assert g["blocked"] is False
    assert any(f["severity"] == "warn" for f in g["findings"])
    assert 0 in [c for c in g["evidence"]["unsourced_chapters"]]


def test_gate_missing_fields_safe():
    assert predraft_gate_check({}, SCENES)["blocked"] is False
    assert predraft_gate_check({"chapters": [{"scenes": [{}]}]}, SCENES)["blocked"] is False   # 无 source_scene_index
    assert PREDRAFT_MAX_PLAN_REGEN == 2
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_predraft_gate.py -q`
Expected: FAIL（`No module named hiki.predraft`）

- [ ] **Step 3: 写实现**

```python
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
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_predraft_gate.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add src/hiki/predraft.py tests/test_predraft_gate.py
git commit -m "feat(predraft-v05): predraft_gate_check(det 章节复制硬拦 + unsourced 出处硬化)"
```

---

### Task 2: `predraft_gate_loop`(async,可测 regen/搁置决策)

**Files:**
- Modify: `src/hiki/predraft.py`
- Test: `tests/test_predraft_gate.py`

**Interfaces:**
- Consumes: `predraft_gate_check`、`PREDRAFT_MAX_PLAN_REGEN`
- Produces:
  - `async predraft_gate_loop(cli, bible0, bible_mined, scenes, out_dir, n_ch, pl0, plan_fn, max_regen=PREDRAFT_MAX_PLAN_REGEN) -> tuple`:返回 `(bible, pl, regens, blocked)`。
    - `bible0`/`pl0` = 首个 `_stage_plan` 已产(attempt 0)的 enriched bible + plan 结果。
    - blocked 时循环:`bible=copy.deepcopy(bible_mined)`;`pl=await plan_fn(cli, bible, scenes, out_dir, n_ch, True)`(原地 enrich 到该副本);`gate=predraft_gate_check(pl["plan"], scenes)`;`regens+=1`,直到不 blocked 或达 max_regen。
    - 返回通过(或最后一次)的 `bible` + `pl` + `regens` + 最终 `blocked`。

- [ ] **Step 1: 写失败测试**

```python
import asyncio
from hiki.predraft import predraft_gate_loop


def _mk_planner(block_seq):
    """plan_fn 桩: 依次返回 block_seq[i] 对应的 plan(True=blocked plan). 记录调用次数/force."""
    calls = []
    async def plan_fn(cli, bible, scenes, out_dir, n_ch, force):
        i = len(calls); calls.append({"force": force})
        blocked = block_seq[min(i + 1, len(block_seq) - 1)]   # +1: attempt0 已在外, 这里是 regen
        idxs = [[3], [3]] if blocked else [[1], [2]]          # 共享3=blocked / 不共享=ok
        return {"plan": {"chapters": [{"scenes": [{"source_scene_index": j} for j in c]} for c in idxs]},
                "beats": [], "ordered": [], "n_scenes": 2, "macro": {}, "stats": {}}
    plan_fn.calls = calls
    return plan_fn


def _pl(blocked):
    idxs = [[3], [3]] if blocked else [[1], [2]]
    return {"plan": {"chapters": [{"scenes": [{"source_scene_index": j} for j in c]} for c in idxs]},
            "beats": [], "ordered": [], "n_scenes": 2, "macro": {}, "stats": {}}


SC = [{"t": i} for i in range(10)]


def test_loop_no_block_no_regen():
    pf = _mk_planner([False])
    bible, pl, regens, blocked = asyncio.run(predraft_gate_loop(
        None, {"b": 0}, {"b": 0}, SC, None, 60, _pl(False), pf))
    assert regens == 0 and blocked is False and len(pf.calls) == 0   # 未 regen


def test_loop_block_then_pass():
    # attempt0 blocked → regen1 pass
    pf = _mk_planner([True, False])
    bible, pl, regens, blocked = asyncio.run(predraft_gate_loop(
        None, {"b": 0}, {"b": 0}, SC, None, 60, _pl(True), pf))
    assert regens == 1 and blocked is False and pf.calls[0]["force"] is True


def test_loop_persistent_block_shelve():
    # 始终 blocked → 达 max_regen 仍 blocked
    pf = _mk_planner([True, True, True, True])
    bible, pl, regens, blocked = asyncio.run(predraft_gate_loop(
        None, {"b": 0}, {"b": 0}, SC, None, 60, _pl(True), pf, max_regen=2))
    assert regens == 2 and blocked is True
```

- [ ] **Step 2: 跑确认 fail** — `python -m pytest tests/test_predraft_gate.py -q`（无 predraft_gate_loop）

- [ ] **Step 3: 写实现(追加 `src/hiki/predraft.py`)**

```python
async def predraft_gate_loop(cli, bible0, bible_mined, scenes, out_dir, n_ch, pl0,
                             plan_fn, max_regen=PREDRAFT_MAX_PLAN_REGEN):
    """预起草门 regen 回路。bible0/pl0=attempt0 结果。blocked 则从 bible_mined 干净副本重规划(plan-rooted)。
    返回 (bible, pl, regens, blocked): 用于 run() 决定搁置 or 进 draft(draft_force=regens>0)。"""
    bible, pl = bible0, pl0
    gate = predraft_gate_check(pl["plan"], scenes)
    regens = 0
    while gate["blocked"] and regens < max_regen:
        regens += 1
        bible = copy.deepcopy(bible_mined)                # 干净副本: 隔离失败次 enrich_places 累积
        pl = await plan_fn(cli, bible, scenes, out_dir, n_ch, True)   # 原地 enrich 到该副本 + 重写 plan.json
        gate = predraft_gate_check(pl["plan"], scenes)
    return bible, pl, regens, gate["blocked"]
```

- [ ] **Step 4: 跑确认 pass** — `python -m pytest tests/test_predraft_gate.py -q`（7 passed）

- [ ] **Step 5: 提交**

```bash
git add src/hiki/predraft.py tests/test_predraft_gate.py
git commit -m "feat(predraft-v05): predraft_gate_loop(regen 回路, 干净副本重规划)"
```

---

### Task 3: 接线 `produce.run` + 搁置 report + 布线测

**Files:**
- Modify: `src/hiki/produce.py`
- Test: `tests/test_predraft_wiring.py`

**Interfaces:**
- Consumes: `predraft.predraft_gate_loop`、`predraft.predraft_gate_check`
- Produces:
  - `_predraft_shelved_report(out_dir, src, gate, regens, cli, grade, started) -> dict`:搁置 report(见下),写 `out_dir/report.json`,不落 final。
  - `run()` 在 plan 后、draft 前插门;搁置→return;否则 `draft_force=force or regens>0`。

**接线位置(produce.py `run()`,现 1342-1356)**:`bible,scenes,grade=mine[...]`(1342)后加 `import copy; bible_mined=copy.deepcopy(bible)`;plan destructure(1347-1352)后、draft(1355)前插门。

- [ ] **Step 1: 写失败测试(搁置路径)**

```python
# tests/test_predraft_wiring.py
import asyncio
import json
from pathlib import Path
from hiki import produce


def test_run_shelves_on_persistent_block(tmp_path, monkeypatch):
    # mine 返回带共享 source_scene_index 的 plan(blocked); plan 每次都 blocked; draft 必不被调
    scenes = [{"t": i} for i in range(5)]
    blocked_pl = {"plan": {"chapters": [{"scenes": [{"source_scene_index": 3}]},
                                        {"scenes": [{"source_scene_index": 3}]}]},
                  "beats": [], "ordered": [], "n_scenes": 2, "macro": {}, "stats": {}}

    async def fake_mine(*a, **k):
        return {"rejected": False, "bible": {"protagonist": {}}, "scenes": scenes,
                "grade": {"grade": "B"}, "meta": {}, "clean": "", "all_scene_count": 5, "chunks": []}

    async def fake_plan(cli, bible, scenes_, out_dir, n_ch, force):
        return blocked_pl

    async def fake_draft(*a, **k):
        raise AssertionError("draft 不应在搁置时被调")

    class FakeClient:                      # run() 开头 Client() 需 DEEPSEEK_API_KEY, 测试无 → 桩
        cost_cny = 0.0
    monkeypatch.setattr(produce, "Client", FakeClient)
    monkeypatch.setattr(produce, "_stage_mine", fake_mine)
    monkeypatch.setattr(produce, "_stage_plan", fake_plan)
    monkeypatch.setattr(produce, "_stage_draft", fake_draft)

    rep = asyncio.run(produce.run(Path("x.txt"), out_dir=tmp_path))
    assert rep["rejected"] is True and rep["deliverable"] is False
    assert rep["predraft_shelved"] is True and rep["predraft_regens"] == produce.predraft.PREDRAFT_MAX_PLAN_REGEN
    assert not (tmp_path / "final.md").exists()
    assert (tmp_path / "report.json").exists()


class _StopRun(Exception):
    pass


def _pl_dict(blocked):
    idxs = [[3], [3]] if blocked else [[1], [2]]
    return {"plan": {"chapters": [{"scenes": [{"source_scene_index": j} for j in c]} for c in idxs]},
            "beats": [], "ordered": [], "n_scenes": 2, "macro": {}, "stats": {}}


def _wire_common(monkeypatch, plan_seq, recorded):
    scenes = [{"t": i} for i in range(5)]

    async def fake_mine(*a, **k):
        return {"rejected": False, "bible": {"protagonist": {}}, "scenes": scenes,
                "grade": {"grade": "B"}, "meta": {}, "clean": "", "all_scene_count": 5, "chunks": []}

    calls = {"n": 0}
    async def fake_plan(cli, bible, scenes_, out_dir, n_ch, force):
        blocked = plan_seq[min(calls["n"], len(plan_seq) - 1)]; calls["n"] += 1
        return _pl_dict(blocked)

    async def fake_draft(cli, bible, scenes_, p, plan, ordered, beats, n_scenes, n_cand,
                         rr, tc, prod, od, force):
        recorded["force"] = force; recorded["plan"] = plan
        raise _StopRun()

    class FakeClient:
        cost_cny = 0.0
    monkeypatch.setattr(produce, "Client", FakeClient)
    monkeypatch.setattr(produce, "_stage_mine", fake_mine)
    monkeypatch.setattr(produce, "_stage_plan", fake_plan)
    monkeypatch.setattr(produce, "_stage_draft", fake_draft)


def test_run_happy_path_draft_force_unchanged(tmp_path, monkeypatch):
    import pytest
    rec = {}
    _wire_common(monkeypatch, [False], rec)   # attempt0 不 blocked → regens=0
    with pytest.raises(_StopRun):
        asyncio.run(produce.run(Path("x.txt"), out_dir=tmp_path, force=False))
    assert rec["force"] is False   # force or 0>0 == False(happy-path draft 收原 force)


def test_run_regen_pass_draft_force_true(tmp_path, monkeypatch):
    import pytest
    rec = {}
    _wire_common(monkeypatch, [True, False], rec)   # attempt0 blocked → regen1 pass
    with pytest.raises(_StopRun):
        asyncio.run(produce.run(Path("x.txt"), out_dir=tmp_path, force=False))
    assert rec["force"] is True    # regens>0 → draft 强制重跑(不复用旧草稿)
    # draft 收到的是 refreshed 非阻塞 plan(两章不共享 source_scene_index)
    chs = rec["plan"]["chapters"]
    assert chs[0]["scenes"][0]["source_scene_index"] != chs[1]["scenes"][0]["source_scene_index"]
```

- [ ] **Step 2: 跑确认 fail** — `python -m pytest tests/test_predraft_wiring.py -q`（run 尚未接线/无 predraft_shelved）

- [ ] **Step 3: 写实现**

在 `produce.py` import 区加 `from . import predraft` + `import copy`(若无)。

`run()` 中 `bible, scenes, grade = mine["bible"], mine["scenes"], mine["grade"]`(1342)后加:
```python
    bible_mined = copy.deepcopy(bible)                   # v0.5: regen 用干净副本(隔离 enrich_places)
```
plan destructure 段(`_ps = pl.get("stats", {})` 1349 之后、`dropped = ...` 1350 之前)插预起草门:
```python
    # 2.5) 预起草门(v0.5): 只硬拦 det 章节复制 → plan-regen ≤2 → 仍拦搁置(跳起草省钱)
    bible, pl, _pd_regens, _pd_blocked = await predraft.predraft_gate_loop(
        cli, bible, bible_mined, scenes, out_dir, n_ch, pl, _stage_plan)
    if _pd_regens:
        plan, beats, ordered = pl["plan"], pl["beats"], pl["ordered"]      # refresh 全部 locals
        n_scenes, macro = pl["n_scenes"], pl["macro"]; _ps = pl.get("stats", {})
        print(f"预起草门: plan-regen×{_pd_regens}")
    if _pd_blocked:
        return _predraft_shelved_report(out_dir, src, predraft.predraft_gate_check(plan, scenes),
                                        _pd_regens, cli, grade, started)
```
draft 调用(1355)`force` 改 `force or _pd_regens > 0`:
```python
    d = await _stage_draft(cli, bible, scenes, p, plan, ordered, beats, n_scenes, n_cand,
                           refine_rounds, target_chars, prod, out_dir, force or _pd_regens > 0)
```
**最终 report 组装(codex#1:regen 通过的书也要带审计)**——`produce.py:1466` 的 `report = {"deliverable": deliverable, "交付门": ...,` 里加三字段:
```python
    report = {
        "deliverable": deliverable, "交付门": ship_issues or ["通过"],
        "predraft_blocked": _pd_blocked, "predraft_regens": _pd_regens, "predraft_shelved": False,  # v0.5 审计
        ...(现有字段不变)
```
新增搁置 report 函数(放 run 附近):
```python
def _predraft_shelved_report(out_dir: Path, src: Path, gate: dict, regens: int,
                             cli, grade, started) -> dict:
    """预起草门搁置: 不落 final, 省 draft/refine 成本。字段对齐 batch/web/normalize(缺 final 跳过)。"""
    why = f"预起草门:章节复制顽固(plan-regen×{regens} 未净)"
    rep = {"rejected": True, "deliverable": False, "交付门": [why], "reject_why": why,
           "predraft_blocked": True, "predraft_regens": regens, "predraft_shelved": True,
           "source": str(src), "grade": grade, "cost_cny": round(cli.cost_cny, 4),   # grade 存 dict(codex, 对齐 mine reject report:799)
           "seconds": round(time.time() - started, 1),
           "predraft_evidence": gate.get("evidence", {})}
    (out_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep
```

- [ ] **Step 4: 跑确认 pass** — `python -m pytest tests/test_predraft_wiring.py -q`（3 passed:搁置 + happy-path force不变 + regen-pass force=True）

- [ ] **Step 5: happy-path 全量守卫 + 提交**

Run: `python -m pytest -m 'not api' -q`(全绿,报确切数;gold/装配网不端到端跑 run 但须仍绿)
```bash
git add src/hiki/produce.py tests/test_predraft_wiring.py
git commit -m "feat(predraft-v05): 接线 run() 预起草门 + plan-regen + 搁置(draft_force 防旧草稿)"
```

---

## 终检
- [ ] 全量 `python -m pytest -m 'not api'` 绿(报确切 passed/deselected)。
- [ ] happy-path 保真:gate 不 blocked → draft 收 `force`(非强制)、plan/bible 未变(接线测覆盖 or 复核确认)。
- [ ] regen 后 draft_force=True(不复用旧草稿);搁置不调 draft。
- [ ] 不硬拦 LLM 类目、不改末端门/冻结向量/gold。

<!-- codex-peer-reviewed: 2026-07-01T02:18:11Z rounds=2 verdict=approved -->
