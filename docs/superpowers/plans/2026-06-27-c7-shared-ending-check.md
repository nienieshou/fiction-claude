# C7.1 共享 ending_check 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `produce._ending_guard` 与 `point_repair.run` 里逐字重复的 ENDING_CHECK 检测循环抽成 `gate.ending_check`,两处都 call,消手工同步,行为逐位保持。

**Architecture:** 新增 `gate.ending_check(cli, prev_tail, tail) -> dict`(3-retry 检测,与 `gate.continuity_check` 同列);两处 adapter 删内联循环、改调用,各自保留 tail 计算与下游(produce 修复 / point_repair flag)。

**Tech Stack:** Python ≥3.10,标准库,pytest(asyncio.run 测异步)。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-27-c7-shared-ending-check-design.md`(读它拿两处现状 + tail 差异是设计 + for-else 等价)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** `gate.py` 已 import prompts/Client、本地 `_safe_json`。
- **行为逐位保持**:`ending_check` 的检测循环 = 两处现状逐字(`chunk_extract`/`ENDING_CHECK`/`max_tokens=400`/`temperature=0.1+0.1*t`/`if "ok" in ec: break`/全失败→`{}`)。两 adapter 的 prev_tail/tail 计算与下游修复/flag **逐字不变**。
- **tail 差异保留**:produce 传 `ch_texts[-1][-2500:]`;point_repair 传其 `tail_blob`(头+尾)。**绝不统一**(误统一=point_repair FP 回归)。
- `pytest -m 'not api'` 离线全绿。编码 UTF-8。

---

## Task 1: gate.ending_check 共享函数

**Files:**
- Modify: `src/hiki/gate.py`(加 `ending_check`,置于 `continuity_check`/`gold_pk` 附近)
- Test: `tests/test_ending_check.py`

**Interfaces:**
- Produces: `gate.ending_check(cli, prev_tail: str, tail: str) -> dict`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ending_check.py
"""gate.ending_check 共享尾门检测(C7.1)。零真实 API(mock cli)。"""
import asyncio
import json
from hiki import gate


class _FakeCli:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def complete(self, stage, sys_p, usr, **kw):
        self.calls.append(kw)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def test_ending_check_valid_returns_ec():
    cli = _FakeCli([json.dumps({"ok": True})])
    ec = asyncio.run(gate.ending_check(cli, "prev", "tail"))
    assert ec == {"ok": True}
    assert len(cli.calls) == 1


def test_ending_check_retries_then_valid():
    cli = _FakeCli(["garbage", json.dumps({"ok": False, "problem": "断尾"})])
    ec = asyncio.run(gate.ending_check(cli, "p", "t"))
    assert ec.get("ok") is False and ec.get("problem") == "断尾"
    assert len(cli.calls) == 2


def test_ending_check_all_invalid_returns_empty():
    cli = _FakeCli(["x", "y", "z"])
    assert asyncio.run(gate.ending_check(cli, "p", "t")) == {}
    assert len(cli.calls) == 3


def test_ending_check_skipped_passthrough():
    cli = _FakeCli([json.dumps({"ok": True, "skipped": True, "skipped_what": "决战"})])
    ec = asyncio.run(gate.ending_check(cli, "p", "t"))
    assert ec.get("skipped") is True and ec.get("skipped_what") == "决战"


def test_ending_check_temperature_ramps():
    cli = _FakeCli(["bad", "bad", json.dumps({"ok": True})])
    asyncio.run(gate.ending_check(cli, "p", "t"))
    assert [round(c["temperature"], 2) for c in cli.calls] == [0.1, 0.2, 0.3]
    assert cli.calls[0]["json_mode"] is True and cli.calls[0]["max_tokens"] == 400
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ending_check.py -q`
Expected: FAIL — `AttributeError: module 'hiki.gate' has no attribute 'ending_check'`

- [ ] **Step 3: 在 `src/hiki/gate.py` 加 `ending_check`(置于 `continuity_check` 之后)**

```python
async def ending_check(cli: Client, prev_tail: str, tail: str) -> dict:
    """ENDING_CHECK 检测(3-retry-on-empty)。共享: produce._ending_guard + point_repair 两处 call。
    返回 ec dict({ok, problem, skipped, skipped_what} 等); 3 次仍无 "ok" 键 → {}。
    调用方各自算 prev_tail/tail(point_repair 头+尾 blob vs produce last[-2500:], tail 差异是设计)。"""
    sys_ec, usr_ec = prompts.ENDING_CHECK
    for t in range(3):
        raw = await cli.complete("chunk_extract", sys_ec,
                                 usr_ec.format(prev_tail=prev_tail, tail=tail),
                                 json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
        ec = _safe_json(raw) or {}
        if "ok" in ec:
            return ec
    return {}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ending_check.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q   # 全绿(只新增)
git add src/hiki/gate.py tests/test_ending_check.py
git commit -m "feat(C7): gate.ending_check 共享尾门检测(3-retry, 供 produce/point_repair 两处 call)"
```

---

## Task 2: produce._ending_guard 改调 gate.ending_check(行为逐位保持)

**Files:**
- Modify: `src/hiki/produce.py`（`_ending_guard` 的检测循环 ~1050-1059）
- Read first: `produce.py:1044-1071`(整个 `_ending_guard`)

**Interfaces:**
- Consumes: `gate.ending_check`(Task 1)

- [ ] **Step 1: 读 `_ending_guard` 现状**

Read `produce.py:1044-1071`。确认 `prev_tail = ch_texts[-2][-800:] if len(ch_texts) >= 2 else "（无）"`、检测循环用 `tail = ch_texts[-1][-2500:]`、`for-else: ec={}`、下游(`ec.get("skipped")`/`ec.get("ok") is False` → ENDING_FIX 补收束)。

- [ ] **Step 2: 替换检测循环**

把内联的 `for t in range(3): ... ec=gate._safe_json(raw) or {}; if "ok" in ec: break; else: ec={}` 整段替换为单行:
```python
    ec = await gate.ending_check(cli, prev_tail, ch_texts[-1][-2500:])
```
**保留 `prev_tail` 计算行 + 下游(climax_skipped/ENDING_FIX/返回 dict)逐字不变。** `sys_ec, usr_ec = prompts.ENDING_CHECK` 那行若仅检测用,可删(已挪进 ending_check);若下游 ENDING_FIX 用的是 `prompts.ENDING_FIX`(另一对),保留其行。读 Step 1 确认。

- [ ] **Step 3: 网守等价**

Run: `python -m pytest tests/test_ending_check.py tests/test_stages.py tests/test_produce_units.py -q`
Expected: 全绿(_ending_guard 输出逐位不变)。

- [ ] **Step 4: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/produce.py
git commit -m "refactor(C7): _ending_guard 改调 gate.ending_check(检测去重, 下游修复不变, 网守)"
```

---

## Task 3: point_repair 改调 gate.ending_check + 文档 + 终验

**Files:**
- Modify: `src/hiki/point_repair.py`（ENDING_CHECK 检测循环 ~155-170）
- Modify: `docs/design/tech-debt.md`（C7 行)
- Read first: `point_repair.py:155-172`

**Interfaces:**
- Consumes: `gate.ending_check`(Task 1)

- [ ] **Step 1: 读 point_repair 的 ending 检测段**

Read `point_repair.py:155-172`。确认 `prev_tail = chs[-2][-800:]`、`tail_blob = last if len(last)<=4500 else (last[:2000]+"\n……(中略)……\n"+last[-2000:])`、循环、下游 flag(`ec.get("skipped") is True` → `issues2.append("预告事件仍被跳过(...)")`)。

- [ ] **Step 2: 替换检测循环**

把 `sys_ec, usr_ec = prompts.ENDING_CHECK` + `ec={}` + `for t in range(3): ... ec=gate._safe_json...; if "ok" in ec: break` 整段替换为(保留 prev_tail/last/tail_blob 计算):
```python
    ec = await gate.ending_check(cli, prev_tail, tail_blob)
```
**保留 `prev_tail`/`last`/`tail_blob` 三行计算 + 下游 flag 逐字不变。** `sys_ec, usr_ec = prompts.ENDING_CHECK` 删(已挪进 ending_check)。

- [ ] **Step 3: 刷新 tech-debt C7 行**

`docs/design/tech-debt.md` C7 行(grep `| C7 |`)状态加 `◐`,备注:`C7.1 已落: ENDING_CHECK 检测抽 gate.ending_check, produce._ending_guard + point_repair 两处 call(消手工同步), 行为逐位保持。残: revival/continuity dedup(缠 produce 尾门 B1)`。

- [ ] **Step 4: 网守 + 终验**

Run: `python -m pytest tests/test_ending_check.py tests/test_point_repair_units.py -q`
Expected: 全绿(point_repair flag 行为不变)。
Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。
Run: 确认两处不再有内联 ENDING_CHECK 循环:`grep -n "ENDING_CHECK" src/hiki/produce.py src/hiki/point_repair.py` 应只剩 `gate.ending_check` 调用 + produce 的 ENDING_FIX(下游)/ 无内联 `for t in range(3)` 配 ENDING_CHECK。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/point_repair.py docs/design/tech-debt.md
git commit -m "refactor(C7): point_repair 改调 gate.ending_check(消手工同步) + tech-debt C7 刷新"
```

---

## Self-Review

- **Spec 覆盖**:① gate.ending_check → Task 1;② produce._ending_guard 改调 → Task 2;③ point_repair 改调 → Task 3;④ tail 差异保留 → Task 2/3 各传各的 tail;⑤ 验证靠既有测试+全量 → 每任务网守 Step。✅
- **行为保持**:每迁移任务验收=既有测试(test_stages/produce_units/point_repair_units)+ 全量绿(非新断言);ending_check 单测证检测循环等价。
- **占位**:Task 2/3 标注"读现状确认/保留下游"——behavior-preserving 重构的有意要求;新代码(Task 1 ending_check + 测试)给完整代码。
- **类型一致**:`gate.ending_check(cli, prev_tail, tail) -> dict` 跨任务一致;两 adapter 各传自己的 tail(produce `ch_texts[-1][-2500:]` / point_repair `tail_blob`)。
- **风险**:① tail 差异误统一 → point_repair FP 回归(Task 2/3 各传各的,绝不共用 tail 表达式);② for-else→return {} 等价(全失败两处都得 {},消费方查 skipped/ok 等价)。
