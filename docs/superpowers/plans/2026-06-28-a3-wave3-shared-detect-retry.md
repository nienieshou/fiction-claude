# A3 wave 3 — 共享检测环 detect_retry + fail-closed 浮现 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 seam/adj_dup/handshake/ending 四处逐字重复的 3-retry LLM 检测环收进单一 `gate.detect_retry`,四处都 call;重试耗尽从"静默当干净"改成 stderr 浮现"可能漏检"。

**Architecture:** 新增 `gate.detect_retry(cli, sys_p, usr, key, *, max_tokens, label, retries=3) -> dict`(检测环 + 失败 stderr 浮现);`gate.ending_check` 改委托它;`produce` 三检 `_check` 闭包改调它。各调用方自 format usr、传 key/max_tokens/label。happy-path 逐位保持(门信号零变化),失败仅加 stderr。

**Tech Stack:** Python ≥3.10,标准库,pytest(`asyncio.run` 测异步)。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-28-a3-wave3-shared-detect-retry-design.md`(读它拿四处现状表 + isinstance 微差 + 非目标)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** `gate.py` 已 import `json`/`re`/`prompts`/`Client`、本地 `_safe_json`;**需加 `import sys`**。
- **行为逐位保持(happy-path)**:四处正常返回(含 `key` 的 dict)时 = 现状(1 次调用、同 prompt/stage `chunk_extract`/`json_mode=True`/各自 `max_tokens`/温度斜坡 `0.1+0.1*t`/`retries=3`)。下游(`r.get("ok") is False`→bad / `r.get("dup") is True`→bad / 回读复检 / 采用守卫 / ending 消费方)**逐字不变**。
- **失败路径 fail-closed**:重试耗尽 → stderr 浮现(`label` 标 pass+对)+ 返 `{}`(调用方按"未检出"消费,同现状保守不误修)。**不改任何返回元组/计数/门信号。**
- **isinstance 守卫微差(有意)**:`detect_retry` 用 `if isinstance(r, dict) and key in r`。seam/handshake/旧 ending 原无此守卫(adj_dup 已有);dict happy 透明,仅 list 响应含 key 成员时变(极罕见、严格更安全)。
- `pytest -m 'not api'` 离线全绿。编码 UTF-8。**金标 + 装配回归网必绿**(happy 逐位 → 门信号向量零变化)。

---

## Task 1: gate.detect_retry 共享检测环 + ending_check 改委托

**Files:**
- Modify: `src/hiki/gate.py`(加 `import sys`;加 `detect_retry`,置于 `ending_check` 前;`ending_check` 改委托)
- Create: `tests/test_detect_retry.py`
- Modify: `tests/test_ending_check.py`(加全畸形→stderr 断言)
- Read first: `gate.py:82-131`(`_safe_json` + `continuity_check` + `ending_check` 现状)

**Interfaces:**
- Produces: `gate.detect_retry(cli, sys_p: str, usr: str, key: str, *, max_tokens: int, label: str, retries: int = 3) -> dict`
- Modifies: `gate.ending_check(cli, prev_tail: str, tail: str) -> dict`(签名不变,内部委托)

- [ ] **Step 1: 写 `detect_retry` 失败测试**

新建 `tests/test_detect_retry.py`:
```python
"""gate.detect_retry 共享 LLM 检测环(A3 wave3)。零真实 API(mock cli)。"""
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


def test_detect_retry_valid_dict_with_key():
    cli = _FakeCli([json.dumps({"ok": True})])
    r = asyncio.run(gate.detect_retry(cli, "sys", "usr", "ok", max_tokens=400, label="X"))
    assert r == {"ok": True}
    assert len(cli.calls) == 1


def test_detect_retry_retries_then_valid():
    cli = _FakeCli(["garbage", json.dumps({"dup": True})])
    r = asyncio.run(gate.detect_retry(cli, "s", "u", "dup", max_tokens=300, label="X"))
    assert r == {"dup": True}
    assert len(cli.calls) == 2


def test_detect_retry_all_invalid_surfaces_and_empty(capsys):
    cli = _FakeCli(["x", "y", "z"])
    r = asyncio.run(gate.detect_retry(cli, "s", "u", "ok", max_tokens=400, label="SEAM 第3章"))
    assert r == {}
    assert len(cli.calls) == 3
    assert "SEAM 第3章" in capsys.readouterr().err      # 浮现(不静默)


def test_detect_retry_passthrough_and_ramp():
    cli = _FakeCli(["bad", "bad", json.dumps({"ok": True})])
    asyncio.run(gate.detect_retry(cli, "s", "u", "ok", max_tokens=300, label="X"))
    assert [round(c["temperature"], 2) for c in cli.calls] == [0.1, 0.2, 0.3]
    assert all(c["max_tokens"] == 300 and c["json_mode"] is True for c in cli.calls)


def test_detect_retry_isinstance_guard_list_retries():
    cli = _FakeCli([json.dumps(["ok"]), json.dumps(["ok"]), json.dumps(["ok"])])  # list 含 "ok" 成员
    r = asyncio.run(gate.detect_retry(cli, "s", "u", "ok", max_tokens=400, label="L"))
    assert r == {}                                       # 非 dict → 不误返
    assert len(cli.calls) == 3
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_detect_retry.py -q`
Expected: FAIL — `AttributeError: module 'hiki.gate' has no attribute 'detect_retry'`

- [ ] **Step 3: 加 `import sys` 到 `gate.py`**

把 `gate.py:7-8`:
```python
import json
import re
```
改为:
```python
import json
import re
import sys
```

- [ ] **Step 4: 加 `detect_retry`(置于 `ending_check` 之前,即 `gate.py:119` `async def ending_check` 那行之前)**

```python
async def detect_retry(cli: Client, sys_p: str, usr: str, key: str, *,
                       max_tokens: int, label: str, retries: int = 3) -> dict:
    """共享 LLM 检测环(N-retry-on-empty)。seam/adj_dup/handshake/ending 四处 call。
    成功 = 解析出 dict 且含 key(各契约判定键 "ok"/"dup")→ 返该 dict。
    retries 次仍无 → stderr 浮现(label 标 pass+对) + 返 {}(调用方按"未检出"消费,同现状保守不误修)。
    调用方各自 format usr(prompt 形状各异),传自己的 key/max_tokens/label。"""
    for t in range(retries):
        raw = await cli.complete("chunk_extract", sys_p, usr,
                                 json_mode=True, max_tokens=max_tokens, temperature=0.1 + 0.1 * t)
        r = _safe_json(raw) or {}
        if isinstance(r, dict) and key in r:
            return r
    print(f'⚠ {label} 校验重试{retries}次仍无效,按"未检出"计(可能漏检)', file=sys.stderr)
    return {}
```

- [ ] **Step 5: `ending_check` 改委托**

把 `gate.py:119-131` 现 `ending_check`(`sys_ec, usr_ec = ...` + `for t in range(3): ...` + `return {}`)整体替换为:
```python
async def ending_check(cli: Client, prev_tail: str, tail: str) -> dict:
    """ENDING_CHECK 检测,委托 detect_retry(A3 wave3 收编)。供 produce._ending_guard + point_repair 两处 call。
    返回 ec dict({ok, problem, skipped, skipped_what} 等); 重试耗尽 → stderr 浮现 + {}。
    调用方各自算 prev_tail/tail(point_repair 头+尾 blob vs produce last[-2500:], tail 差异是设计)。"""
    sys_ec, usr_ec = prompts.ENDING_CHECK
    return await detect_retry(cli, sys_ec, usr_ec.format(prev_tail=prev_tail, tail=tail),
                              "ok", max_tokens=400, label="ENDING_CHECK")
```

- [ ] **Step 6: 加 ending_check 全畸形→stderr 断言**

在 `tests/test_ending_check.py` 末尾追加:
```python
def test_ending_check_all_invalid_surfaces(capsys):
    cli = _FakeCli(["x", "y", "z"])
    assert asyncio.run(gate.ending_check(cli, "p", "t")) == {}
    assert "ENDING_CHECK" in capsys.readouterr().err     # 收编后修其同款静默 bug
```

- [ ] **Step 7: 跑确认通过(含既有 ending 测不退化)**

Run: `python -m pytest tests/test_detect_retry.py tests/test_ending_check.py -q`
Expected: PASS（detect_retry 6 + ending 6 = 12 passed）

- [ ] **Step 8: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/gate.py tests/test_detect_retry.py tests/test_ending_check.py
git commit -m "feat(A3 wave3): gate.detect_retry 共享检测环(4处call) + ending_check 改委托(顺修同款静默bug)"
```

---

## Task 2: produce 三检改调 detect_retry + fail-closed 焦点测 + 文档 + 终验

**Files:**
- Modify: `src/hiki/produce.py`(`_seam_pass._check`:154-162 / `_adj_dup_pass._check`:218-226 / `_handshake_pass._check`:732-746)
- Create: `tests/test_a3_wave3_passes.py`
- Modify: `docs/design/tech-debt.md`(A3 / A1 / C7 行)
- Read first: `produce.py:146-191`(_seam_pass)、`produce.py:209-250`(_adj_dup_pass)、`produce.py:721-746`(_handshake_pass._check)

**Interfaces:**
- Consumes: `gate.detect_retry`(Task 1)。`produce` 已 `import` `gate`(现用 `gate._safe_json`/`gate.ending_check`)。

- [ ] **Step 1: 写 fail-closed 焦点失败测试**

新建 `tests/test_a3_wave3_passes.py`:
```python
"""A3 wave3: 三检 pass 重试耗尽 → stderr 浮现(不静默当干净)。零真实 API(mock cli)。"""
import asyncio
from hiki import produce


class _FakeCli:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def complete(self, stage, sys_p, usr, **kw):
        self.calls.append(kw)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def test_seam_pass_surfaces_on_all_invalid(capsys):
    cli = _FakeCli(["garbage", "garbage", "garbage"])     # 2章→1对,_check 最多3调用全畸形
    ch = ["第一章正文。", "第二章正文。"]
    out, fixed, found, unresolved = asyncio.run(produce._seam_pass(cli, ch))
    assert out == ch and fixed == [] and found == 0 and unresolved == []   # 不误修
    assert "SEAM 第2章" in capsys.readouterr().err          # 浮现该对(可能漏检)


def test_adj_dup_pass_surfaces_on_all_invalid(capsys):
    cli = _FakeCli(["garbage", "garbage", "garbage"])
    ch = ["第一章正文。", "第二章正文。"]
    out, fixed, found, unresolved = asyncio.run(produce._adj_dup_pass(cli, ch))
    assert out == ch and fixed == [] and found == 0 and unresolved == []
    assert "ADJ_DUP 第2章" in capsys.readouterr().err
```

- [ ] **Step 2: 跑确认失败(现状静默 → 无 stderr)**

Run: `python -m pytest tests/test_a3_wave3_passes.py -q`
Expected: FAIL — 现状 `_check` 全空 → 返 `{}` 无 stderr → `"SEAM 第2章" in err` 失败

- [ ] **Step 3: 改 `_seam_pass._check`(produce.py:154-162)**

把:
```python
    async def _check(i: int) -> dict:
        for t in range(3):                       # retry-on-empty(flash偶发空响应,核心flaky类)
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-700:], head=ch_texts[i][:900]),
                                     json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if "ok" in r:
                return r
        return {}                                # 3次都空 → 认衔接正常(保守不误修)
```
替换为:
```python
    async def _check(i: int) -> dict:
        return await gate.detect_retry(
            cli, sys_c, usr_c.format(prev=ch_texts[i - 1][-700:], head=ch_texts[i][:900]),
            "ok", max_tokens=400, label=f"SEAM 第{i + 1}章")
```
(`sys_c, usr_c = prompts.SEAM_CHECK` 那行保留。)

- [ ] **Step 4: 改 `_adj_dup_pass._check`(produce.py:218-226)**

把:
```python
    async def _check(i: int) -> dict:
        for t in range(3):
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-1800:], head=ch_texts[i][:2200]),
                                     json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if isinstance(r, dict) and "dup" in r:
                return r
        return {}
```
替换为:
```python
    async def _check(i: int) -> dict:
        return await gate.detect_retry(
            cli, sys_c, usr_c.format(prev=ch_texts[i - 1][-1800:], head=ch_texts[i][:2200]),
            "dup", max_tokens=300, label=f"ADJ_DUP 第{i + 1}章")
```
(`sys_c, usr_c = prompts.ADJ_DUP_CHECK` 那行保留。)

- [ ] **Step 5: 改 `_handshake_pass._check`(produce.py:732-746)**

把内部 `for t in range(3): ... return {}` 段(732 `prev, cur = ...` 之后的循环)替换,**保留** `prev/cur/sc0/brief` 三行计算:
```python
    async def _check(j: int) -> dict:
        prev, cur = chs[j - 1], chs[j]
        sc0 = (cur.get("scenes") or [{}])[0]
        brief = ((sc0.get("brief") if isinstance(sc0, dict) else str(sc0)) or "")[:300]
        return await gate.detect_retry(
            cli, sys_h, usr_h.format(prev_exit=prev.get("exit_state") or "（未知）",
                                     hook=prev.get("end_hook") or "（无）",
                                     start=cur.get("start_state") or "（未填）",
                                     brief=brief or "（无）"),
            "ok", max_tokens=300, label=f"HANDSHAKE 第{j + 1}章")
```
(`sys_h, usr_h = prompts.HANDSHAKE_CHECK` 那行保留。)

- [ ] **Step 6: 跑焦点测 + happy 网守**

Run: `python -m pytest tests/test_a3_wave3_passes.py tests/test_stages.py tests/test_produce_units.py -q`
Expected: 全绿(焦点测浮现 + 三检 happy 行为逐位不变)。

- [ ] **Step 7: 金标 + 装配回归网(门信号零变化)**

Run: `python -m pytest tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全绿(happy 逐位 → 门信号向量零变化)。

- [ ] **Step 8: 刷新 `docs/design/tech-debt.md`**

- **A3 行**(`| A3 |`)备注末尾追加:`wave3: seam/adj_dup/handshake/ending 四检共享环抽 gate.detect_retry(消4处copy-paste) — 重试耗尽 stderr 浮现"可能漏检"(治静默假阴), happy 逐位保持(门信号零变化)`。
- **A1 行**(`| A1 |`)备注:把"每-pass(seam/adj_dup/handshake)的 checked-vs-unknown 仍待办"更新为 `每-pass 重试耗尽已 stderr 浮现(A3 wave3); 进 ship 信号的 unknown 计数仍待办`。
- **C7 行**(`| C7 |`)备注:`ending_check 已并入共享 gate.detect_retry(A3 wave3, 四检同环)`。

- [ ] **Step 9: 确认无残留内联检测环**

Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。
Run grep 核对四处都改调:`grep -n "detect_retry" src/hiki/gate.py src/hiki/produce.py`
Expected: `gate.py` 1 定义 + `ending_check` 1 调用;`produce.py` 3 调用(seam/adj_dup/handshake)。三检 `_check` 内不再有内联 `for t in range(3)` 配 `cli.complete`。

- [ ] **Step 10: 提交**

```bash
git add src/hiki/produce.py tests/test_a3_wave3_passes.py docs/design/tech-debt.md
git commit -m "feat(A3 wave3): seam/adj_dup/handshake 三检改调 gate.detect_retry — 失败 stderr 浮现(治静默假阴), happy 逐位保持 + tech-debt 刷新"
```

---

## Self-Review

- **Spec 覆盖**:① `detect_retry` → Task 1 Step 4;② ending_check 委托 → Task 1 Step 5;③ 三检迁移 → Task 2 Step 3/4/5;④ fail-closed stderr → Task 1(detect_retry 测 + ending 测)+ Task 2(焦点测);⑤ happy 网守 → Task 2 Step 6;⑥ 金标/装配网 → Task 2 Step 7;⑦ isinstance 微差 → Task 1 Step 1 `test_detect_retry_isinstance_guard_list_retries`。✅
- **行为保持**:三检迁移验收 = 既有 `test_stages`/`test_produce_units` + 金标/装配网(非新断言);`detect_retry` 单测证检测环等价。
- **占位**:Task 2 标注"读现状/保留计算行"——behavior-preserving 迁移的有意要求;新代码(detect_retry + 委托 + 测试 + 焦点测)给完整代码。
- **类型一致**:`detect_retry(cli, sys_p, usr, key, *, max_tokens, label, retries=3) -> dict` 跨任务一致;四调用方各传自己的 (usr, key, max_tokens, label);测试复用各文件本地 `_FakeCli`(同 C7.1 形)。
- **风险**:① 收编 ending_check 动 C7.1 已上线码 → 其 6 测(5 既有 + 1 新)+ 两调用方守不退化;② isinstance 守卫微差 → Task 1 显式测 list 响应;③ happy 首调用温度 0.1 = 原值,门信号零变化 → 金标网守。
