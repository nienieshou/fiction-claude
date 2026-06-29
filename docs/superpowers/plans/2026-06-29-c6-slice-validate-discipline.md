# C6 残留 — slice_validate.py 纪律拉齐 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 M0 dev 工具 `slice_validate.py` 两处拉齐生产纪律:① EXTRACT 裸 `json.loads` 换 `complete_validated`(重试 + 干净 RuntimeError,删 `_json`);② craft_audit 白烧接 `config.advisory_on`(镜 C6②,默认开)。

**Architecture:** 抽两个小可测 helper(`_extract_dna` / `_craft_advisory`)替 `run()` 内联逻辑,给真单测 + 微解 god-function;两处 run() 调用点各一行。happy 路字节保持。

**Tech Stack:** Python ≥3.10,标准库 + pytest。无新第三方依赖。复用 `llm_validate.complete_validated`、`config.advisory_on`、`config.load`。

**设计依据:** `docs/superpowers/specs/2026-06-29-c6-slice-validate-discipline-design.md`(读它拿 dev 工具定位 + 两站点现状 + happy 等价论证)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** 编码 UTF-8。
- **dev 工具内**:不动出货管线(`produce.py`/`run`)、不动任何交付门信号。
- **happy 首试字节等价**:EXTRACT `complete_validated(..., retries=2, temperature=0.3, json_mode=True, max_tokens=8000)` 首试 temp 0.3 同原单发;craft 默认开(`config.advisory_on` 缺省 `default=True`)→ 照烧、报告同。
- **EXTRACT 失败干净化**:解析耗尽 → `RuntimeError`(非裸 `JSONDecodeError`);schema 要求 `scenes` 非空 list → 守卫后 `dna["scenes"]` 永远安全。
- **craft 关时占位串**与 C6② produce.py 同语义:`"(craft advisory 已关:config.advisories.craft_audit)"`。
- **不碰** `_do_plan`(`:192` 已 `_safe_json`)、`_draft_candidates`(`:63` prose)、PICK(`:87`)。不加新 config 旋钮(复用 `craft_audit` 键)。不改 EXTRACT/craft prompt / 报告键名。
- TDD:先写失败测。金标/装配网**不覆盖** slice_validate → 等价靠 happy 首试逐位同 + 焦点测,不靠网。

---

## Task 1: EXTRACT 失软 —— `_extract_dna` 替 `_json`

**Files:**
- Modify: `src/hiki/slice_validate.py`(import `:14`;删 `_json` `:28-32`;新增 `_extract_dna`;`run()` 内 `:175-177` 调用点)
- Create: `tests/test_slice_validate_robust.py`
- Read first: `slice_validate.py:14`(imports)、`:28-32`(`_json` 现状)、`:174-186`(EXTRACT 调用 + 下游 `dna["scenes"]`)、`llm_validate.py:8`(complete_validated 签名)

**Interfaces:**
- Consumes: `llm_validate.complete_validated(cli, stage, sys_p, usr, *, schema, retries=3, **complete_kw) -> dict | None`(现存,不改)。
- Produces: `slice_validate._extract_dna(cli: Client, slice_src: str) -> dict`(解析耗尽抛 `RuntimeError`;成功返回含非空 `scenes` 的 dna dict)。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_slice_validate_robust.py`:
```python
"""C6 残留: slice_validate dev 工具纪律拉齐 —— EXTRACT 失软 + craft_audit 门控。
零 API; fake cli 按固定串回应。"""
import asyncio
import json
import pytest
from hiki import slice_validate


class _Cli:
    """每次 complete 返回同一固定串; 记调用次数。"""
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def complete(self, *a, **k):
        self.calls += 1
        return self.reply


def test_extract_valid_returns_dna():
    cli = _Cli(json.dumps({"scenes": [{"i": 0}], "voice": "网文白话", "bible": {}}))
    dna = asyncio.run(slice_validate._extract_dna(cli, "切片源文本"))
    assert dna["scenes"] == [{"i": 0}]
    assert dna["voice"] == "网文白话"
    assert cli.calls == 1                       # 首试通过即返回


def test_extract_malformed_raises_after_retry():
    cli = _Cli("这不是json <<<")
    with pytest.raises(RuntimeError, match="EXTRACT 失败"):
        asyncio.run(slice_validate._extract_dna(cli, "切片源文本"))
    assert cli.calls == 2                       # retries=2 耗尽


def test_extract_partial_no_scenes_raises():
    cli = _Cli(json.dumps({"voice": "x"}))      # 解析成功但无 scenes
    with pytest.raises(RuntimeError, match="EXTRACT 失败"):
        asyncio.run(slice_validate._extract_dna(cli, "切片源文本"))
    assert cli.calls == 2                       # schema 拒 → 重试耗尽
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_slice_validate_robust.py -q`
Expected: FAIL — `AttributeError: module 'hiki.slice_validate' has no attribute '_extract_dna'`。

- [ ] **Step 3: 加 import(`slice_validate.py:14` 一带)**

在 `from . import prompts, gate, ledger, audit`(`:14`)下加一行:
```python
from .llm_validate import complete_validated
```

- [ ] **Step 4: 删 `_json`(`:28-32`)+ 加 `_extract_dna`**

删除现 `_json`(`:28-32`):
```python
def _json(s: str) -> dict:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1].lstrip("json").strip()
    return json.loads(s)
```
在同位置(原 `_json` 处)加:
```python
async def _extract_dna(cli: Client, slice_src: str) -> dict:
    """EXTRACT 抽取(健壮): 重试解析, 终败干净报错(非裸 JSONDecodeError)。"""
    sys_e, usr_e = prompts.EXTRACT
    dna = await complete_validated(cli, "extract", sys_e, usr_e.format(source=slice_src[:40000]),
                                   schema=lambda r: isinstance(r, dict) and isinstance(r.get("scenes"), list) and bool(r["scenes"]),
                                   retries=2, json_mode=True, max_tokens=8000, temperature=0.3)
    if dna is None:
        raise RuntimeError("EXTRACT 失败:抽取 JSON 解析/重试均无效(flaky 截断或无场景),请重跑。")
    return dna
```

- [ ] **Step 5: `run()` 调用点改用 helper(`slice_validate.py:174-177`)**

把现(`:174-177`):
```python
    # 1) 提取
    sys_e, usr_e = prompts.EXTRACT
    dna = _json(await cli.complete("extract", sys_e, usr_e.format(source=slice_src[:40000]),
                                   json_mode=True, max_tokens=8000, temperature=0.3))
```
改为:
```python
    # 1) 提取
    dna = await _extract_dna(cli, slice_src)
```
(下游 `:178-186` 的 `dna.get("voice")`/`dna.get("bible")`/`dna["scenes"]` 不变 —— schema 保证 `scenes` 非空。)

- [ ] **Step 6: 跑确认通过**

Run: `python -m pytest tests/test_slice_validate_robust.py -q`
Expected: PASS（3 passed）

- [ ] **Step 7: 全量离线套**

Run: `python -m pytest -m 'not api' -q`
Expected: 全绿,报确切 passed/deselected 数(`_json` 删除无残留引用)。

- [ ] **Step 8: 提交**

```bash
git add src/hiki/slice_validate.py tests/test_slice_validate_robust.py
git commit -m "feat(C6): slice_validate EXTRACT 换 complete_validated + 干净 RuntimeError(删 _json)"
```

---

## Task 2: craft_audit config 门控 —— `_craft_advisory`(镜 C6②)

**Files:**
- Modify: `src/hiki/slice_validate.py`(import `:14`;`run()` 加 `cfg` 加载;新增 `_craft_advisory`;`run()` 内 `:280` 调用点)
- Test: `tests/test_slice_validate_robust.py`(Task 1 已建,追加 craft 测)
- Read first: `slice_validate.py:165-173`(run 开头)、`:276-298`(craft 调用 + 报告组装)、`config.py:33,45`(load / advisory_on)

**Interfaces:**
- Consumes: `config.load(name) -> dict`、`config.advisory_on(cfg, name, default=True) -> bool`(现存,不改);`audit.craft_audit(cli, text) -> list`(现存)。
- Produces: `slice_validate._craft_advisory(cli: Client, final: str, cfg: dict) -> list`(`craft_audit` 开→ craft 结果;关→ 占位串列表)。

- [ ] **Step 1: 写失败测试(追加到 `tests/test_slice_validate_robust.py`)**

在文件末尾追加:
```python
def test_craft_advisory_off_skips_burn(monkeypatch):
    calls = {"n": 0}

    async def _fake_craft(cli, final):
        calls["n"] += 1
        return ["craft-ran"]

    monkeypatch.setattr(slice_validate.audit, "craft_audit", _fake_craft)
    out = asyncio.run(slice_validate._craft_advisory(object(), "成品文",
                                                     {"advisories": {"craft_audit": False}}))
    assert out == ["(craft advisory 已关:config.advisories.craft_audit)"]
    assert calls["n"] == 0                       # 关时绝不 await craft_audit


def test_craft_advisory_default_on_runs(monkeypatch):
    calls = {"n": 0}

    async def _fake_craft(cli, final):
        calls["n"] += 1
        return ["craft-ran"]

    monkeypatch.setattr(slice_validate.audit, "craft_audit", _fake_craft)
    out = asyncio.run(slice_validate._craft_advisory(object(), "成品文", {}))   # 缺 advisories → 默认开
    assert out == ["craft-ran"]
    assert calls["n"] == 1
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_slice_validate_robust.py -q`
Expected: FAIL — `AttributeError: module 'hiki.slice_validate' has no attribute '_craft_advisory'`。

- [ ] **Step 3: 加 import config(`slice_validate.py:14`)**

把 `:14`:
```python
from . import prompts, gate, ledger, audit
```
改为(加 `config`):
```python
from . import prompts, gate, ledger, audit, config
```

- [ ] **Step 4: 加 `_craft_advisory`(与 `_extract_dna` 同区,模块级)**

```python
async def _craft_advisory(cli: Client, final: str, cfg: dict) -> list:
    """C6: craft 人/故事性评审(~2500tk, 纯 advisory)。config 可关省 token, 默认开。"""
    if config.advisory_on(cfg, "craft_audit"):
        return await audit.craft_audit(cli, final)
    return ["(craft advisory 已关:config.advisories.craft_audit)"]
```

- [ ] **Step 5: `run()` 加 cfg 加载 + 改 craft 调用点**

(a) 在 `run()` 内 `cli = Client()`(`:173`)下一行加:
```python
    cfg = config.load("pipeline") or {}
```
(b) 把 `:280`:
```python
    audit_craft = await audit.craft_audit(cli, final)
```
改为:
```python
    audit_craft = await _craft_advisory(cli, final, cfg)
```
(报告行 `:293` `audit_craft or ["无"]` 不动。)

- [ ] **Step 6: 跑确认通过**

Run: `python -m pytest tests/test_slice_validate_robust.py -q`
Expected: PASS（5 passed —— Task 1 三测 + 本 Task 两测）

- [ ] **Step 7: 全量离线套**

Run: `python -m pytest -m 'not api' -q`
Expected: 全绿,报确切 passed/deselected 数。

- [ ] **Step 8: 刷新 `docs/design/tech-debt.md` C6 行**

C6 行备注追加:
```
C6 残留已收: slice_validate(dev工具) EXTRACT 换 complete_validated(重试+干净RuntimeError, 删_json) + craft_audit 接 config.advisory_on(镜C6②默认开)。抽 _extract_dna/_craft_advisory 小helper微解run()。dev工具内不动出货/门; happy首试字节同。
```

- [ ] **Step 9: 提交**

```bash
git add src/hiki/slice_validate.py tests/test_slice_validate_robust.py docs/design/tech-debt.md
git commit -m "feat(C6): slice_validate craft_audit 接 config.advisory_on(镜 C6②, 默认开)"
```

---

## Self-Review

- **Spec 覆盖**:① EXTRACT 失软(`_extract_dna` + 删 `_json` + complete_validated)→ Task 1;② craft_audit 门控(`_craft_advisory` + cfg + config import)→ Task 2;③ import → Task 1(complete_validated)+ Task 2(config);验证四轴(extract 合法/malformed/partial,craft 关/开)→ 两 Task 的 5 测;tech-debt 刷新 → Task 2 Step 8。✅
- **占位**:无 TBD;每代码步给完整前后码;测试完整。
- **类型一致**:`_extract_dna(cli, slice_src) -> dict`、`_craft_advisory(cli, final, cfg) -> list` 跨 spec/plan/测一致;`complete_validated(..., schema, retries, **kw) -> dict|None` 与 `llm_validate.py:8` 一致;`config.advisory_on(cfg, name, default=True)`/`config.load(name)` 与 `config.py:45/33` 一致。
- **任务独立**:Task 1(健壮性)与 Task 2(token 门控)互不依赖,各自可被复核独立否决;共改 `:14` import 区但不同行(Task 1 加 complete_validated 行,Task 2 在 `from . import` 加 config),顺序执行无冲突。
- **温度等价**:Task 1 Step 4 `temperature=0.3,retries=2` → 首试 0.3 同原单发。
- **风险**:① `_json` 删除残留引用 → Task 1 Step 7 全量套兜(仅 `:176` 一处用,已实证);② craft 关时误烧 → Task 2 `test_craft_advisory_off_skips_burn` 计数守;③ schema 拒空 scenes 改下游 → `dna["scenes"]` 守卫后安全(Task 1 Step 5 注)。
