# 修复回读验证 (Repair Read-back Verification) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the章缝 / 邻章版本 repair passes **re-detect after adopting a fix**, so `seam_fixed`/`adj_fixed` count only *verified-resolved* chapters — turning the residual signal honest and surfacing "修复但未净" chapters.

**Architecture:** Today `_seam_pass`/`_adj_dup_pass` adopt a rewrite via a length-guard only, then mark it `fixed`. The residual `seam_found - len(seam_fixed)` thus means "fix not *adopted*", not "seam not *resolved*". This is the dominant false-negative the read-through found in all 3 certified books (catalog `docs/evidence/readthrough_defect_catalog.md`: "检出→'修复'标记→正文未净→sub-threshold→照发"). Fix: after adopting a rewrite, **re-run the existing `_check(i)` detector on the rewritten text**; only count it `fixed` if the detector now passes, else collect it into a new `unresolved` list. The residual formula stays identical but becomes honest, and the report gains a "修复未净" field that makes the previously-invisible failure visible.

**Tech Stack:** Python `asyncio`, DeepSeek via `hiki.Client`, `pytest`.

## Global Constraints

- **Residual formula MUST stay `seam_found - len(seam_fixed)`** (produce.py:1422 gate `残缝`, produce.py:1469 frozen `seam_residual`). Do NOT change the formula or the signal schema — making `seam_fixed` *verified-only* makes the residual honest by itself.
- **signals schema v1 frozen** (`src/hiki/signals.py`): `seam_residual` is an existing key; do NOT add/rename/remove any signal key. This plan does not touch `signals.py`.
- **Re-detect cost**: +1 LLM `chunk_extract` call **per ADOPTED fix only** (not per chapter). Re-detect ONLY chapters whose rewrite passed the length-guard. Acceptable.
- **Conservative bias preserved**: the existing `_check` returns `{}` after 3 empty retries (treated as "衔接正常/不互斥"). On re-check, `{}` → `.get("ok")`/`.get("dup")` is None → counted as **resolved** (not unresolved), matching the existing "保守不误修" default — a flaky empty re-check must not fabricate a residual.
- **Tests zero real API**: use the self-contained `FakeClient` from Task 1 (per-bucket scripted response queues). No real DeepSeek calls.
- **Run tests**: `.venv\Scripts\python.exe -m pytest -q` (pyproject `pythonpath=["src","."]`, bare run auto-deselects `api`).
- Model: DeepSeek-v4 only; passes use the existing `cli.complete("chunk_extract"/"draft", ...)` channel; no new model.
- Don't break existing `tests/test_produce_units.py`, `tests/test_gate.py`, `tests/test_signals.py`.

## File Structure

- `src/hiki/produce.py` — modify `_seam_pass` (145-185), `_adj_dup_pass` (203-237) to re-detect adopted fixes and return a 4-tuple `(ch_texts, fixed, found, unresolved)`; update the two call sites (1351, 1356) and add two report fields (near 1442, 1448).
- `tests/test_repair_readback.py` (new) — `FakeClient` + seam/adj re-detect tests; zero real API.

---

### Task 1: `_seam_pass` re-detect after adopt

**Files:**
- Modify: `src/hiki/produce.py:145-185` (`_seam_pass`)
- Test: `tests/test_repair_readback.py` (new)

**Interfaces:**
- Consumes: `produce._split_head(t: str, n: int = 1200) -> tuple[str, str]` (existing); `gate._safe_json`; `prompts.SEAM_CHECK`/`SEAM_FIX`.
- Produces: `_seam_pass(cli, ch_texts: list[str], cap: int = 60)` now returns a **4-tuple** `(ch_texts, fixed: list[str], found: int, unresolved: list[str])`. `fixed` = chapters whose rewrite was adopted AND re-detect passed; `unresolved` = adopted but re-detect still `ok is False`; chapters whose rewrite was rejected by the length-guard appear in neither. Re-detect runs ONLY on adopted chapters.

- [ ] **Step 1: Write the failing test**

Create `tests/test_repair_readback.py`:

```python
"""修复回读验证: 章缝/邻章版本 修复后重跑 detect。FakeClient(零真实 API)。"""
import asyncio
import json
from hiki import produce


class FakeClient:
    """按 bucket 分队列返回预置响应。detect 与 recheck 都走 'chunk_extract',
    按调用顺序出队(先 detect 后 recheck);fix 走 'draft'。"""
    def __init__(self, by_bucket: dict):
        self.q = {k: list(v) for k, v in by_bucket.items()}
        self.calls = []

    async def complete(self, bucket, sys, usr, *, json_mode=False, max_tokens=0, temperature=0.0):
        self.calls.append(bucket)
        return self.q[bucket].pop(0)


def _run(coro):
    return asyncio.run(coro)


# ch1 短(<720字, 无 \n\n) → _split_head 的 head = 整章, rest = ""
CH1 = "第二章 牙行买人\n" + "正" * 120


def test_seam_verified_resolved_counts_as_fixed():
    head, _ = produce._split_head(CH1)
    cli = FakeClient({
        "chunk_extract": [
            json.dumps({"ok": False, "issue": "时间倒退"}),  # detect ch idx1 = 断裂
            json.dumps({"ok": True}),                         # recheck → 已净
        ],
        "draft": [head],                                      # 改写=head, 过长度守卫
    })
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert found == 1
    assert len(fixed) == 1 and "第2章" in fixed[0]
    assert unresolved == []
    assert found - len(fixed) == 0          # 残缝=0(诚实)


def test_seam_adopted_but_unresolved_counts_as_residual():
    head, _ = produce._split_head(CH1)
    cli = FakeClient({
        "chunk_extract": [
            json.dumps({"ok": False, "issue": "时间倒退"}),  # detect
            json.dumps({"ok": False, "issue": "仍倒退"}),    # recheck → 仍断裂
        ],
        "draft": [head],
    })
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert found == 1
    assert fixed == []
    assert len(unresolved) == 1 and "第2章" in unresolved[0]
    assert found - len(fixed) == 1          # 残缝=1(过去会错记为0)


def test_seam_fix_rejected_by_guard_no_recheck():
    cli = FakeClient({
        "chunk_extract": [json.dumps({"ok": False, "issue": "x"})],  # 只 detect, 无 recheck
        "draft": ["短"],                                              # 太短, 守卫拒绝采用
    })
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert found == 1
    assert fixed == [] and unresolved == []  # 未采用 → 既非fixed也非unresolved
    assert cli.calls.count("chunk_extract") == 1  # recheck 未被调用(未采用不回读)


def test_seam_no_break_no_fix_no_recheck():
    cli = FakeClient({"chunk_extract": [json.dumps({"ok": True})], "draft": []})
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert found == 0 and fixed == [] and unresolved == []
    assert cli.calls == ["chunk_extract"]    # 只 detect


def test_seam_empty_recheck_treated_as_resolved():
    # 回读 3 次空响应 → _check 返回 {} → 保守判为已净(不误记 residual)
    head, _ = produce._split_head(CH1)
    cli = FakeClient({
        "chunk_extract": [json.dumps({"ok": False, "issue": "x"}), "", "", ""],  # detect + 3空recheck
        "draft": [head],
    })
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert len(fixed) == 1 and unresolved == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_repair_readback.py -v`
Expected: FAIL — `_seam_pass` currently returns a 3-tuple, so `out, fixed, found, unresolved = ...` raises `ValueError: not enough values to unpack (expected 4, got 3)`.

- [ ] **Step 3: Implement re-detect in `_seam_pass`**

In `src/hiki/produce.py`, replace the body of `_seam_pass` from the early-return through the return. Specifically:

Change line 150 (`if len(ch_texts) < 2:` early return) and line 170 (`if not bad:` early return) to return a 4-tuple, and replace the adopt loop (178-185) with adopt-then-recheck. The full edited function:

```python
async def _seam_pass(cli: Client, ch_texts: list[str], cap: int = 60):
    """章缝衔接检修（治人工头号缺陷：相邻章时空/动作倒退）。
    detect(59对尾→头并发) → 定向重写断裂章的开头段(其余原样) → 采用守卫 → 回读复检。
    返回 (修后章文, 修复清单, 检出数, 修复未净清单)。修复未净=改写采用但重跑detect仍断裂。"""
    if len(ch_texts) < 2:
        return ch_texts, [], 0, []
    sys_c, usr_c = prompts.SEAM_CHECK

    async def _check(i: int) -> dict:
        for t in range(3):                       # retry-on-empty(flash偶发空响应,核心flaky类)
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-700:], head=ch_texts[i][:900]),
                                     json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if "ok" in r:
                return r
        return {}                                # 3次都空 → 认衔接正常(保守不误修)
    idxs = list(range(1, len(ch_texts)))
    checks = await asyncio.gather(*[_check(i) for i in idxs])
    bad = []
    for i, r in zip(idxs, checks):
        if r.get("ok") is False:
            bad.append((i, (r.get("issue") or "").strip() or "时空/动作衔接断裂"))
    found = len(bad)
    if not bad:
        return ch_texts, [], 0, []
    bad = bad[:cap]
    sys_f, usr_f = prompts.SEAM_FIX
    splits = {i: _split_head(ch_texts[i]) for i, _ in bad}
    res = await asyncio.gather(*[
        cli.complete("draft", sys_f,
                     usr_f.format(prev=ch_texts[i - 1][-700:], issue=iss, head=splits[i][0]),
                     max_tokens=4000, temperature=0.4) for i, iss in bad])
    adopted = []
    for (i, iss), t in zip(bad, res):
        head, rest = splits[i]
        t = _strip_markers((t or "").strip())
        if t and len(head) * 0.5 <= len(t) <= len(head) * 2.0:   # 守卫:开头没崩才采用
            ch_texts[i] = t + rest
            adopted.append((i, iss))
    rechecks = await asyncio.gather(*[_check(i) for i, _ in adopted])  # 回读复检:只查已采用章
    fixed, unresolved = [], []
    for (i, iss), rc in zip(adopted, rechecks):
        label = f"第{i + 1}章:{iss[:18]}"
        (unresolved if rc.get("ok") is False else fixed).append(label)
    return ch_texts, fixed, found, unresolved
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_repair_readback.py -v`
Expected: PASS (5 seam tests). (Other callers of `_seam_pass` will break the full suite until Task 3 — that is expected; run only this file here.)

- [ ] **Step 5: Commit**

```bash
git add src/hiki/produce.py tests/test_repair_readback.py
git commit -m "feat(produce): _seam_pass re-detects adopted fixes; returns unresolved list

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `_adj_dup_pass` re-detect after adopt

**Files:**
- Modify: `src/hiki/produce.py:203-237` (`_adj_dup_pass`)
- Test: `tests/test_repair_readback.py` (append)

**Interfaces:**
- Consumes: `gate._safe_json`; `prompts.ADJ_DUP_CHECK`/`ADJ_DUP_FIX`.
- Produces: `_adj_dup_pass(cli, ch_texts: list[str], cap: int = 12)` now returns a **4-tuple** `(ch_texts, fixed: list[str], found: int, unresolved: list[str])`. Detector key here is `dup` (not `ok`): re-detect still-`dup is True` → `unresolved`. Adopt guard is `len(t) >= len(ch_texts[i]) * 0.7`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repair_readback.py`:

```python
# ——— 邻章版本(_adj_dup_pass): detect/recheck 用 "dup" 键 ———
CH1_DUP = "第二章\n" + "重演前章的内容" * 30


def test_adj_verified_resolved_counts_as_fixed():
    cli = FakeClient({
        "chunk_extract": [
            json.dumps({"dup": True, "issue": "互斥重演"}),  # detect
            json.dumps({"dup": False}),                       # recheck → 已净
        ],
        "draft": [CH1_DUP],                                   # 改写≥原长0.7, 采用
    })
    out, fixed, found, unresolved = _run(produce._adj_dup_pass(cli, ["第一章正文内容", CH1_DUP]))
    assert found == 1
    assert len(fixed) == 1 and "第2章" in fixed[0]
    assert unresolved == []
    assert found - len(fixed) == 0


def test_adj_adopted_but_unresolved_counts_as_residual():
    cli = FakeClient({
        "chunk_extract": [
            json.dumps({"dup": True, "issue": "互斥重演"}),  # detect
            json.dumps({"dup": True, "issue": "仍重演"}),    # recheck → 仍重演
        ],
        "draft": [CH1_DUP],
    })
    out, fixed, found, unresolved = _run(produce._adj_dup_pass(cli, ["第一章正文内容", CH1_DUP]))
    assert found == 1
    assert fixed == []
    assert len(unresolved) == 1 and "第2章" in unresolved[0]
    assert found - len(fixed) == 1


def test_adj_fix_rejected_by_guard_no_recheck():
    cli = FakeClient({
        "chunk_extract": [json.dumps({"dup": True, "issue": "x"})],  # 只 detect
        "draft": ["短"],                                              # <原长0.7, 拒绝
    })
    out, fixed, found, unresolved = _run(produce._adj_dup_pass(cli, ["第一章正文内容", CH1_DUP]))
    assert found == 1 and fixed == [] and unresolved == []
    assert cli.calls.count("chunk_extract") == 1


def test_adj_no_dup_no_fix():
    cli = FakeClient({"chunk_extract": [json.dumps({"dup": False})], "draft": []})
    out, fixed, found, unresolved = _run(produce._adj_dup_pass(cli, ["第一章正文内容", CH1_DUP]))
    assert found == 0 and fixed == [] and unresolved == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_repair_readback.py -k adj -v`
Expected: FAIL — `_adj_dup_pass` returns a 3-tuple → `ValueError` unpacking 4.

- [ ] **Step 3: Implement re-detect in `_adj_dup_pass`**

In `src/hiki/produce.py`, replace `_adj_dup_pass` body so it returns a 4-tuple and re-detects adopted rewrites. Full edited function:

```python
async def _adj_dup_pass(cli: Client, ch_texts: list[str], cap: int = 12):
    """R11 邻章头部重演检修: 后章开头把前章已演事件重演成互斥版本(冥夙双救场/茶壶两版类)。
    M0(scripts/m0_adjdup_recall.py): 头部类召回1/1,净书误报7%且抽查多为真伤;修复=重写后章开头
    承接前章(同 seam-fix 模式,采用守卫,采用后回读复检),深处互斥不在此环(归点修)。
    返回 (修后, 修复清单, 检出数, 修复未净清单)。"""
    if len(ch_texts) < 2:
        return ch_texts, [], 0, []
    sys_c, usr_c = prompts.ADJ_DUP_CHECK

    async def _check(i: int) -> dict:
        for t in range(3):
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-1800:], head=ch_texts[i][:2200]),
                                     json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if isinstance(r, dict) and "dup" in r:
                return r
        return {}
    idxs = list(range(1, len(ch_texts)))
    checks = await asyncio.gather(*[_check(i) for i in idxs])
    bad = [(i, (r.get("issue") or "互斥重演").strip()) for i, r in zip(idxs, checks)
           if r.get("dup") is True][:cap]
    found = len(bad)
    if not bad:
        return ch_texts, [], 0, []
    sys_f, usr_f = prompts.ADJ_DUP_FIX
    rewrites = await asyncio.gather(*[
        cli.complete("draft", sys_f, usr_f.format(issue=iss, prev=ch_texts[i - 1][-1500:],
                                                  text=ch_texts[i][:14000]),
                     max_tokens=8000, temperature=0.3) for i, iss in bad])
    adopted = []
    for (i, iss), t in zip(bad, rewrites):
        t = _strip_markers((t or "").strip())
        if t and len(t) >= len(ch_texts[i]) * 0.7:   # 采用守卫
            ch_texts[i] = t
            adopted.append((i, iss))
    rechecks = await asyncio.gather(*[_check(i) for i, _ in adopted])  # 回读复检
    fixed, unresolved = [], []
    for (i, iss), rc in zip(adopted, rechecks):
        label = f"第{i + 1}章:{iss[:20]}"
        (unresolved if rc.get("dup") is True else fixed).append(label)
    return ch_texts, fixed, found, unresolved
```

Note: `found` is now `len(bad)` captured before the `if not bad` return (previously the function returned `len(bad)` at the end). Behavior identical: `found == len(bad)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_repair_readback.py -v`
Expected: PASS (all 9 tests, seam + adj).

- [ ] **Step 5: Commit**

```bash
git add src/hiki/produce.py tests/test_repair_readback.py
git commit -m "feat(produce): _adj_dup_pass re-detects adopted fixes; returns unresolved list

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire 4-tuple into call sites + report

**Files:**
- Modify: `src/hiki/produce.py:1351` & `:1356` (call sites), `:1353` & `:1358` (print), `:1442` & `:1448` (report dict)
- Test: existing suite must stay green; no new unit test (end-to-end covered by Tasks 1-2 pass-level tests + the catalog's real cases).

**Interfaces:**
- Consumes: `_seam_pass`/`_adj_dup_pass` 4-tuple from Tasks 1-2.
- Produces: report gains `"章缝_修复未净"` and `"邻章版本_修复未净"` fields; residual `seam_found - len(seam_fixed)` unchanged in formula (now honest because `seam_fixed` is verified-only).

- [ ] **Step 1: Verify no other callers**

Run: `.venv\Scripts\python.exe -c "import subprocess"` is not needed — instead grep the repo:

Run (Git Bash): `grep -rn "_seam_pass\|_adj_dup_pass" src tests scripts`
Expected: the only call sites are `produce.py:1351` and `produce.py:1356` (plus the `async def` definitions and the new test file). If any OTHER caller exists (e.g. a script unpacking the 3-tuple), STOP and report it — it must be updated too. (Underscore-prefixed internal helpers; expected to be produce-only.)

- [ ] **Step 2: Update the two call sites + prints**

`src/hiki/produce.py`, change line 1351 from:
```python
    ch_texts, seam_fixed, seam_found = await _seam_pass(cli, ch_texts)
```
to:
```python
    ch_texts, seam_fixed, seam_found, seam_unresolved = await _seam_pass(cli, ch_texts)
```

Change line 1353 print from:
```python
        print(f"章缝: 检出 {seam_found} 处断裂, 修复 {len(seam_fixed)} 处: {seam_fixed}")
```
to:
```python
        print(f"章缝: 检出 {seam_found} 处断裂, 修复净 {len(seam_fixed)} 处, 未净 {len(seam_unresolved)} 处: {seam_fixed}")
```

Change line 1356 from:
```python
    ch_texts, adj_fixed, adj_found = await _adj_dup_pass(cli, ch_texts)
```
to:
```python
    ch_texts, adj_fixed, adj_found, adj_unresolved = await _adj_dup_pass(cli, ch_texts)
```

Change line 1358 print from:
```python
        print(f"邻章版本: 检出 {adj_found} 对头部重演, 修复 {len(adj_fixed)} 对: {adj_fixed[:6]}")
```
to:
```python
        print(f"邻章版本: 检出 {adj_found} 对头部重演, 修复净 {len(adj_fixed)} 对, 未净 {len(adj_unresolved)} 对: {adj_fixed[:6]}")
```

- [ ] **Step 3: Add report fields**

`src/hiki/produce.py`, in the report dict, add a `修复未净` field next to each existing pair.

After line 1442 (`"邻章版本_检出": adj_found, "邻章版本_修复": adj_fixed or ["无"],`) make it:
```python
        "邻章版本_检出": adj_found, "邻章版本_修复": adj_fixed or ["无"],
        "邻章版本_修复未净": adj_unresolved or ["无"],
```

After line 1448 (`"章缝_检出": seam_found, "章缝_修复": seam_fixed or ["无"],`) make it:
```python
        "章缝_检出": seam_found, "章缝_修复": seam_fixed or ["无"],
        "章缝_修复未净": seam_unresolved or ["无"],
```

Do NOT touch line 1422 (`seam_found - len(seam_fixed)` to the gate) or line 1469 (`seam_residual=seam_found - len(seam_fixed)`) — the formula is intentionally unchanged; it is now honest because `seam_fixed` is verified-only.

- [ ] **Step 4: Run full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS, no regressions (the new 9 repair-readback tests + all existing, api deselected). Confirm the summary shows the new tests and 0 failures.

Also static import sanity:
Run: `.venv\Scripts\python.exe -c "import hiki.produce"`
Expected: no error.

- [ ] **Step 5: Commit**

```bash
git add src/hiki/produce.py
git commit -m "feat(produce): wire repair-readback unresolved into report; residual now honest

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:** re-detect adopted seam fixes (Task 1) ✓ · re-detect adopted adj_dup fixes (Task 2) ✓ · honest residual via verified-only `fixed` (Tasks 1-2, formula unchanged at call site) ✓ · surface "修复未净" in report (Task 3) ✓ · no schema change (`seam_residual` reused) ✓.

**2. Placeholder scan:** no TBD/TODO; every code step has full function/edit text; every test step has complete assertions. Task 3 Step 1 "verify no other callers" is a real grep check (not a placeholder) — it guards the 3-tuple→4-tuple signature change.

**3. Type consistency:**
- Both passes return `(ch_texts, fixed: list[str], found: int, unresolved: list[str])` — Tasks 1-2 define, Task 3 unpacks exactly 4 in both call sites (`seam_*` / `adj_*`).
- Detector keys: seam uses `"ok"` (resolved when not `is False`), adj uses `"dup"` (resolved when not `is True`) — matches each pass's existing detector and the FakeClient scripts.
- Report keys `"章缝_修复未净"` / `"邻章版本_修复未净"` are new; no existing key renamed. `seam_residual` signal untouched.
- Conservative `{}`-recheck path: seam `{}.get("ok") is False` → False → `fixed`; adj `{}.get("dup") is True` → False → `fixed`. Both treat an indeterminate re-check as resolved (per Global Constraints). The `test_seam_empty_recheck_treated_as_resolved` test pins this.

---

## 后续(本 plan 之外)
- 阈值重标定(reenact 7→? / spine_net 6→?):等 2 本 holdout(CPBXN00188/ZYGGY02252)读完做验证集后再定。本 plan 让 residual 诚实,是重标定的前提。
- `early_repeat` 扩到"章内重述"(intra_repeat 12-gram 漏改写式重复:书2 ch1/书3 ch1/ch30)——独立小 plan。
