# A3.1 LLM 输出 schema 校验层(infra + 2 标杆)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建可复用 `validate → retry → reject` 校验层,在 `PROSE_REVIVAL_VERIFY`/`EXTRACT_CHUNK` 两标杆上把"解析失败静默默认(fail-open)"改成"validate→retry→显式 fail-closed"。

**Architecture:** `schemas.validate()`(纯谓词)+ 标杆 schema 常量;新模块 `llm_validate.complete_validated()`(retry+升温,终败返 None,fail 动作留调用点)。2 标杆改用它,各自 fail-closed 动作(保留存疑 / 浮现丢失)。happy-path 逐位保持(首调用原温度),仅失败路径改 fail-closed。

**Tech Stack:** Python ≥3.10,标准库,pytest(asyncio.run 测异步)。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-27-a3-schema-validate-design.md`(读它拿现状 2 标杆 + fail-closed 姿态)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** `llm_validate.py` 从 `gate` 导入 `_safe_json`(不搬动)、从 `schemas` 导入 `validate`。
- **happy-path 逐位保持**:`complete_validated` 首次调用(t=0)用调用方原温度 → LLM 正常返回时行为 = 原单次调用。金标网证 happy 不变。
- **失败路径有意 fail-closed**(A3 目的):解析/校验失败 retry 后,执行调用点显式 fail 动作(保留存疑 / 浮现),不再静默默认。
- **只动 2 标杆**:`verify_revivals`(`prose_continuity.py`)、`_extract_one`(`mining.py`)。其余契约不碰。
- `pytest -m 'not api'` 离线全绿。编码 UTF-8。

---

## Task 1: 校验基础设施(validate + complete_validated)

**Files:**
- Modify: `src/hiki/schemas.py`(加 `validate` + 标杆 schema 常量)
- Create: `src/hiki/llm_validate.py`
- Test: `tests/test_llm_validate.py`

**Interfaces:**
- Produces:
  - `schemas.validate(raw, required, types=None) -> bool`
  - `schemas.REVIVAL_VERIFY`、`schemas.EXTRACT_CHUNK`(dict 形 `{"required": (...), "types": {...}}`)
  - `llm_validate.complete_validated(cli, stage, sys_p, usr, *, schema, retries=3, **complete_kw) -> dict | None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_llm_validate.py
"""LLM 输出 schema 校验层(A3.1)。零真实 API(mock cli)。"""
import asyncio
import json
from hiki.schemas import validate, REVIVAL_VERIFY, EXTRACT_CHUNK
from hiki.llm_validate import complete_validated


class _FakeCli:
    """mock Client: complete() 按序返回预置响应; 耗尽则返回最后一个。记录每次 kw。"""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def complete(self, stage, sys_p, usr, **kw):
        self.calls.append(kw)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


# ---- validate 谓词 ----
def test_validate_required_present():
    assert validate({"is_revival": True}, **REVIVAL_VERIFY) is True


def test_validate_missing_key():
    assert validate({"foo": 1}, **REVIVAL_VERIFY) is False


def test_validate_wrong_type():
    assert validate({"is_revival": "yes"}, **REVIVAL_VERIFY) is False   # str 非 bool


def test_validate_non_dict():
    assert validate(None, **REVIVAL_VERIFY) is False
    assert validate([1, 2], **REVIVAL_VERIFY) is False


def test_validate_extract_chunk_empty_list_valid_but_missing_invalid():
    assert validate({"scene_cards": []}, **EXTRACT_CHUNK) is True       # 空列表=合法抽取
    assert validate({}, **EXTRACT_CHUNK) is False                       # 无键=解析失败


# ---- complete_validated ----
def test_complete_validated_valid_first_call_uses_base_temperature():
    cli = _FakeCli([json.dumps({"is_revival": True})])
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr",
                                       schema=REVIVAL_VERIFY, retries=2, temperature=0.1, json_mode=True))
    assert r == {"is_revival": True}
    assert len(cli.calls) == 1
    assert round(cli.calls[0]["temperature"], 2) == 0.1                 # 首调用=原温度
    assert cli.calls[0]["json_mode"] is True                            # 其余 kw 透传


def test_complete_validated_retries_then_valid():
    cli = _FakeCli(["garbage{", json.dumps({"is_revival": False})])
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr", schema=REVIVAL_VERIFY, retries=3))
    assert r == {"is_revival": False}
    assert len(cli.calls) == 2


def test_complete_validated_all_invalid_returns_none():
    cli = _FakeCli(["garbage", "{bad", "nope"])
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr", schema=REVIVAL_VERIFY, retries=3))
    assert r is None
    assert len(cli.calls) == 3


def test_complete_validated_temperature_ramps_on_retry():
    cli = _FakeCli(["bad", "bad", json.dumps({"is_revival": True})])
    asyncio.run(complete_validated(cli, "s", "sys", "usr",
                                   schema=REVIVAL_VERIFY, retries=3, temperature=0.1))
    assert [round(c["temperature"], 2) for c in cli.calls] == [0.1, 0.2, 0.3]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_llm_validate.py -q`
Expected: FAIL — `ImportError: cannot import name 'validate' from 'hiki.schemas'`

- [ ] **Step 3a: 在 `src/hiki/schemas.py` 末尾追加**

```python
# ==================== A3: LLM 输出契约校验 ====================
def validate(raw, required, types: dict | None = None) -> bool:
    """轻量契约校验: raw 是 dict 且 required 键全在 + (可选)类型匹配。"""
    if not isinstance(raw, dict):
        return False
    for k in required:
        if k not in raw:
            return False
    for k, t in (types or {}).items():
        if k in raw and not isinstance(raw[k], t):
            return False
    return True


# 标杆 schema(键取自现状契约)
REVIVAL_VERIFY = {"required": ("is_revival",), "types": {"is_revival": bool}}
EXTRACT_CHUNK = {"required": ("scene_cards",)}   # 有 scene_cards 键=有效抽取(空列表合法); 无键=解析失败
```

- [ ] **Step 3b: 创建 `src/hiki/llm_validate.py`**

```python
"""LLM 输出契约校验包装(A3)。cli.complete → _safe_json → schemas.validate; 重试; 终败 None。
返回 dict(有效) | None(retries 次后仍无效)——fail 动作由调用方显式处理(不藏 callback)。"""
from __future__ import annotations
from .gate import _safe_json
from .schemas import validate


async def complete_validated(cli, stage, sys_p, usr, *, schema, retries: int = 3, **complete_kw):
    base_t = complete_kw.pop("temperature", 0.2)
    for t in range(retries):
        raw = await cli.complete(stage, sys_p, usr, temperature=base_t + 0.1 * t, **complete_kw)
        r = _safe_json(raw)
        if validate(r, **schema):
            return r
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_llm_validate.py -q`
Expected: PASS（10 passed）

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q   # 全绿(只新增)
git add src/hiki/schemas.py src/hiki/llm_validate.py tests/test_llm_validate.py
git commit -m "feat(A3): validate 谓词 + complete_validated 校验包装(infra, 无依赖)"
```

---

## Task 2: 标杆1 — verify_revivals 经 complete_validated(fail-closed 保留存疑)

**Files:**
- Modify: `src/hiki/prose_continuity.py`（`verify_revivals` ~229-243)
- Test: `tests/test_a3_landmarks.py`(新)
- Read first: `prose_continuity.py:229-243`

**Interfaces:**
- Consumes: `llm_validate.complete_validated`、`schemas.REVIVAL_VERIFY`

- [ ] **Step 1: 写 fail-path + happy 测试**

```python
# tests/test_a3_landmarks.py
"""A3 标杆契约 fail-closed 行为(A3.1)。零真实 API(mock cli)。"""
import asyncio
import json
from hiki.prose_continuity import verify_revivals


class _FakeCli:
    """mock Client(本地复定义, 避免跨测试 import 脆弱)。"""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def complete(self, stage, sys_p, usr, **kw):
        self.calls.append(kw)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def test_verify_revivals_malformed_keeps_candidate_failclosed():
    # LLM 全畸形 → 候选保留为存疑(fail-closed), 不静默丢
    cli = _FakeCli(["garbage", "still bad"])                # retries=2
    revivals = [{"who": "纪老夫人", "clue": "火化", "revive_ch": 0}]
    out = asyncio.run(verify_revivals(cli, ["纪老夫人又出现了"], revivals))
    assert out == revivals


def test_verify_revivals_valid_false_drops():
    cli = _FakeCli([json.dumps({"is_revival": False})])
    revivals = [{"who": "张三", "clue": "", "revive_ch": 0}]
    out = asyncio.run(verify_revivals(cli, ["张三在场"], revivals))
    assert out == []


def test_verify_revivals_valid_true_keeps():
    cli = _FakeCli([json.dumps({"is_revival": True})])
    revivals = [{"who": "李四", "clue": "坠崖", "revive_ch": 0}]
    out = asyncio.run(verify_revivals(cli, ["李四复活"], revivals))
    assert out == revivals
```

- [ ] **Step 2: 跑测试确认失败(现状静默丢 → malformed 测试失败)**

Run: `python -m pytest tests/test_a3_landmarks.py::test_verify_revivals_malformed_keeps_candidate_failclosed -q`
Expected: FAIL — 现状 malformed→`{}`→`is_revival is True`=False→候选被丢→`out==[]` ≠ revivals

- [ ] **Step 3: 改 verify_revivals**

读 `prose_continuity.py:229-243` 现状(确认 `usr_t.format` 字段 who/clue/text、`[:9000]`、并发 gather)。替换为:
```python
async def verify_revivals(cli: Client, ch_texts: list[str], revivals: list[dict]) -> list[dict]:
    """detect→verify→repair：逐个核查疑似复活是否为真。A3: 校验失败(畸形)→保留存疑(fail-closed)。"""
    sys_p, usr_t = prompts.PROSE_REVIVAL_VERIFY

    async def _keep(r: dict) -> bool:
        v = await complete_validated(
            cli, "chunk_extract", sys_p,
            usr_t.format(who=r["who"], clue=r["clue"] or "已死亡", text=ch_texts[r["revive_ch"]][:9000]),
            schema=schemas.REVIVAL_VERIFY, retries=2, json_mode=True, max_tokens=500, temperature=0.1)
        return v is None or v.get("is_revival") is True     # None=畸形→保留存疑; 否则按 is_revival
    flags = await asyncio.gather(*[_keep(r) for r in revivals])
    return [r for r, k in zip(revivals, flags) if k]
```
加 import:`from .llm_validate import complete_validated` 与 `from . import schemas`(置于现有 import 区;若 `from . import prompts` 已在,追加 schemas)。

- [ ] **Step 4: 网守(happy + fail + 金标)**

Run: `python -m pytest tests/test_a3_landmarks.py tests/test_llm_validate.py tests/test_gold_regression.py tests/test_revival_paths_characterization.py -q`
Expected: 全绿(fail-path 新行为 + happy 不变 + 金标 `ft_revival_residual` 零变化)。

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/prose_continuity.py tests/test_a3_landmarks.py
git commit -m "feat(A3): verify_revivals 经 complete_validated — 畸形→保留存疑(fail-closed), happy不变(金标网守)"
```

---

## Task 3: 标杆2 — _extract_one 经 complete_validated(fail-closed 浮现丢失)

**Files:**
- Modify: `src/hiki/mining.py`（`_extract_one` ~41-49)
- Test: `tests/test_a3_landmarks.py`（追加)
- Read first: `mining.py:41-49`

**Interfaces:**
- Consumes: `llm_validate.complete_validated`、`schemas.EXTRACT_CHUNK`

- [ ] **Step 1: 追加 fail-path 测试**

```python
# 追加到 tests/test_a3_landmarks.py
from hiki.mining import _extract_one


def test_extract_one_malformed_surfaces_loss_and_returns_empty(capsys):
    cli = _FakeCli(["garbage", "still bad"])               # retries=2
    r = asyncio.run(_extract_one(cli, "某章正文" * 10, idx=3))
    assert r == {}                                         # 不静默崩, 返空
    assert "chunk 3" in capsys.readouterr().err            # stderr 浮现丢失(不再静默)


def test_extract_one_valid_marks_chunk():
    cli = _FakeCli([json.dumps({"scene_cards": [{"summary": "x"}]})])
    r = asyncio.run(_extract_one(cli, "正文", idx=5))
    assert r["scene_cards"][0]["_chunk"] == 5              # happy: 标 _chunk 不变
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest "tests/test_a3_landmarks.py::test_extract_one_malformed_surfaces_loss_and_returns_empty" -q`
Expected: FAIL — 现状 malformed 静默返 `{}` 无 stderr 告警 → `"chunk 3" in err` 失败

- [ ] **Step 3: 改 _extract_one**

读 `mining.py:41-49` 现状(确认 `usr_t.format(chunk=chunk[:60000])`、`max_tokens=8000`、`temperature=0.3`、标 `_chunk`)。替换为:
```python
async def _extract_one(cli: Client, chunk: str, idx: int) -> dict:
    sys_p, usr_t = prompts.EXTRACT_CHUNK
    r = await complete_validated(cli, "chunk_extract", sys_p, usr_t.format(chunk=chunk[:60000]),
                                 schema=schemas.EXTRACT_CHUNK, retries=2,
                                 json_mode=True, max_tokens=8000, temperature=0.3)
    if r is None:                                           # A3: 重试后仍无效 → 浮现丢失(不再静默 {})
        print(f"⚠ chunk {idx} EXTRACT_CHUNK 重试后仍无效,该窗零贡献", file=sys.stderr)
        return {}
    for sc in r.get("scene_cards", []):
        sc["_chunk"] = idx
    return r
```
加 import:`from .llm_validate import complete_validated`、`from . import schemas`、`import sys`(若未有;`mining.py` 已用 `gate._safe_json` 其它函数,保留 gate 导入)。

- [ ] **Step 4: 网守**

Run: `python -m pytest tests/test_a3_landmarks.py tests/test_mining.py -q`
Expected: 全绿(fail 浮现 + happy 标 _chunk 不变)。

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/mining.py tests/test_a3_landmarks.py
git commit -m "feat(A3): _extract_one 经 complete_validated — 畸形→stderr浮现丢失+{}(fail-closed), happy不变"
```

---

## Task 4: 文档 + 终验

**Files:**
- Modify: `docs/design/tech-debt.md`（A3 行)

- [ ] **Step 1: 刷新 tech-debt A3 行**

`docs/design/tech-debt.md` A3 行(grep `| A3 |`)状态 `⬜`→`◐`,备注追加:`A3.1 已落: src/hiki/llm_validate.complete_validated(validate→retry→None) + schemas.validate 谓词; 2 标杆 PROSE_REVIVAL_VERIFY(畸形→保留存疑)/EXTRACT_CHUNK(畸形→浮现丢失)改 fail-closed, happy-path逐位保持(金标网守)。残: 其余 28 契约分波(Class A 硬回退/B 静默假阴/C 保护偏置)`。

- [ ] **Step 2: 全量 + 关键网终验**

Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。
Run: `python -m pytest tests/test_llm_validate.py tests/test_a3_landmarks.py tests/test_gold_regression.py tests/test_mining.py tests/test_revival_paths_characterization.py -q`
Expected: 全绿(infra + 标杆 + happy 网守)。

- [ ] **Step 3: 提交**

```bash
git add docs/design/tech-debt.md
git commit -m "docs(A3): tech-debt A3 刷新 ◐ — schema 校验层 infra + 2 标杆 fail-closed"
```

---

## Self-Review

- **Spec 覆盖**:① validate + complete_validated infra → Task 1;② 标杆1 verify_revivals(保留存疑)→ Task 2;③ 标杆2 _extract_one(浮现丢失)→ Task 3;④ happy 网守 → 每任务 Step4(含金标网);⑤ fail-path mock 测 → Task 2/3。✅
- **happy-path 保持**:complete_validated 首调用(t=0)= base_t = 原温度,LLM 正常返回时 1 次调用同原行为;金标网 + 既有测试守。
- **占位**:Task 2/3 标注"读现状确认字段"——behavior 敏感处实现者对齐真实;新代码(Task 1 infra + 测试)给完整代码。
- **类型一致**:`validate(raw, required, types)`/`complete_validated(... schema, retries, **kw) -> dict|None`/`REVIVAL_VERIFY`/`EXTRACT_CHUNK`/`_FakeCli` 跨任务一致。`tests/test_a3_landmarks.py` 复用 `tests/test_llm_validate.py` 的 `_FakeCli`(import)。
- **风险**:① 金标网只护 happy——revival fail-closed 仅在畸形改 `ft_revival_residual`,金标 happy 应零变化(红=happy 漂移,回查);② `_FakeCli` 跨测试 import 需 `tests/` 可作包导入(pythonpath 含 `.`,已配)。
