# A3 wave 2 — LIFE_EVENTS schema 校验 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `mining._extract_life_one`(LIFE_EVENTS)从"解析失败静默丢生死事件"改成 `complete_validated`(validate→retry→stderr 浮现),并扩 infra 支持 callable schema(容 dict-or-list)。

**Architecture:** `complete_validated` 扩成 schema 可为 dict 或谓词 callable(向后兼容);`schemas.parsed`(dict/list→True,None→False);`_extract_life_one` 改调,None→浮现+`{"life_events":[]}`,否则 dict-or-list 归一(现状逻辑)。happy-path 逐位保持。

**Tech Stack:** Python ≥3.10,标准库,pytest(asyncio.run)。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-28-a3-wave2-life-events-design.md`。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。**
- **向后兼容**:`complete_validated` 扩 callable schema,既有 dict schema 调用(REVIVAL_VERIFY/EXTRACT_CHUNK)零行为变化。
- **happy-path 逐位保持**:`_extract_life_one` 正常返回时 = 原单次调用(温度 0.2);dict-or-list 归一 + `isinstance(e,dict)` 过滤不变。
- **失败路径 fail-closed**:原静默 `[]` → 2-retry + stderr 浮现 + `{"life_events":[]}`。
- **容 dict-or-list**(`schemas.parsed` 只要求解析非空)——裸 list 是可解析数据,保留(避免重蹈 A3.1 过严丢数据)。
- `pytest -m 'not api'` 离线全绿。编码 UTF-8。

---

## Task 1: infra 扩 callable schema + schemas.parsed

**Files:**
- Modify: `src/hiki/llm_validate.py`（`complete_validated` 的 validate 调用)
- Modify: `src/hiki/schemas.py`（加 `parsed`)
- Test: `tests/test_llm_validate.py`（追加)

**Interfaces:**
- Produces: `schemas.parsed(r) -> bool`;`complete_validated(..., schema=<dict|callable>, ...)`(schema 现可为谓词)

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_llm_validate.py(文件已有 _FakeCli + import json/asyncio)
from hiki.schemas import parsed


def test_schemas_parsed():
    assert parsed({"a": 1}) is True
    assert parsed([1, 2]) is True
    assert parsed(None) is False


def test_complete_validated_callable_schema_bare_list_valid():
    cli = _FakeCli([json.dumps([{"x": 1}])])          # 裸 list → _safe_json 返 list → parsed True
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr", schema=parsed, retries=2))
    assert r == [{"x": 1}]
    assert len(cli.calls) == 1


def test_complete_validated_callable_schema_retries_on_none():
    cli = _FakeCli(["garbage", json.dumps({"life_events": []})])
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr", schema=parsed, retries=3))
    assert r == {"life_events": []}
    assert len(cli.calls) == 2


def test_complete_validated_dict_schema_backward_compat():
    cli = _FakeCli([json.dumps({"is_revival": True})])   # 既有 dict schema 仍走旧路
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr", schema=REVIVAL_VERIFY, retries=2))
    assert r == {"is_revival": True}
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_llm_validate.py::test_schemas_parsed tests/test_llm_validate.py::test_complete_validated_callable_schema_bare_list_valid -q`
Expected: FAIL — `ImportError: cannot import name 'parsed'` / callable schema 走 `validate(r, **callable)` 报错

- [ ] **Step 3a: `src/hiki/schemas.py` 加 `parsed`**

在 A3 块(`validate` 附近)追加:
```python
def parsed(r) -> bool:
    """解析出非空(dict 或 list)即有效——数据契约容 dict-or-list(如 LIFE_EVENTS)。_safe_json 返 dict|list|None。"""
    return r is not None
```

- [ ] **Step 3b: `src/hiki/llm_validate.py` 扩 callable schema**

把 `complete_validated` 内的 `if validate(r, **schema):` 改为:
```python
        if (schema(r) if callable(schema) else validate(r, **schema)):
```
(其余不变;`from .schemas import validate` 保留。)

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_llm_validate.py -q`
Expected: PASS（原 9 + 新 4 = 13 passed,含 backward-compat）

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/llm_validate.py src/hiki/schemas.py tests/test_llm_validate.py
git commit -m "feat(A3 wave2): complete_validated 接 callable schema(向后兼容) + schemas.parsed(容 dict-or-list)"
```

---

## Task 2: 迁移 _extract_life_one + 文档 + 终验

**Files:**
- Modify: `src/hiki/mining.py`（`_extract_life_one` ~61-69)
- Modify: `docs/design/tech-debt.md`（A3 行备注追加 wave2)
- Test: `tests/test_a3_landmarks.py`（追加)
- Read first: `mining.py:61-69`

**Interfaces:**
- Consumes: `llm_validate.complete_validated`、`schemas.parsed`

- [ ] **Step 1: 追加测试**

```python
# 追加到 tests/test_a3_landmarks.py(已有本地 _FakeCli + import asyncio/json)
from hiki.mining import _extract_life_one


def test_extract_life_malformed_surfaces_and_empty(capsys):
    cli = _FakeCli(["garbage", "still bad"])           # retries=2
    r = asyncio.run(_extract_life_one(cli, "正文" * 5))
    assert r == {"life_events": []}
    assert "LIFE_EVENTS" in capsys.readouterr().err     # 浮现(不静默)


def test_extract_life_valid_dict():
    cli = _FakeCli([json.dumps({"life_events": [{"who": "甲", "type": "死亡"}]})])
    r = asyncio.run(_extract_life_one(cli, "正文"))
    assert r["life_events"] == [{"who": "甲", "type": "死亡"}]


def test_extract_life_valid_bare_list_keeps_data():
    cli = _FakeCli([json.dumps([{"who": "乙", "type": "复活"}])])   # 裸 list(flaky LLM)
    r = asyncio.run(_extract_life_one(cli, "正文"))
    assert r["life_events"] == [{"who": "乙", "type": "复活"}]      # 不丢可解析数据


def test_extract_life_filters_non_dict_elements():
    cli = _FakeCli([json.dumps([{"who": "甲"}, "noise", 123])])
    r = asyncio.run(_extract_life_one(cli, "正文"))
    assert r["life_events"] == [{"who": "甲"}]            # 非 dict 元素滤除(现状不变)
```

- [ ] **Step 2: 跑确认失败(现状静默 → malformed 测试无 stderr)**

Run: `python -m pytest "tests/test_a3_landmarks.py::test_extract_life_malformed_surfaces_and_empty" -q`
Expected: FAIL — 现状 `_safe_json`=None→`events=[]`→返 `{"life_events":[]}` 无 stderr → `"LIFE_EVENTS" in err` 失败

- [ ] **Step 3: 改 _extract_life_one**

读 `mining.py:61-69` 现状。替换为:
```python
async def _extract_life_one(cli: Client, chunk: str, roster: str = "（本段出现的所有人物）") -> dict:
    sys_p, usr_t = prompts.LIFE_EVENTS
    r = await complete_validated(cli, "chunk_extract", sys_p,
                                 usr_t.format(chunk=chunk[:60000], roster=roster),
                                 schema=schemas.parsed, retries=2, json_mode=True,
                                 max_tokens=1500, temperature=0.2)
    if r is None:                              # A3: 解析失败(重试后)→ 浮现丢失(非静默)
        print("⚠ LIFE_EVENTS 重试后仍无效,该段生死事件零贡献", file=sys.stderr)
        return {"life_events": []}
    events = r if isinstance(r, list) else (r.get("life_events") or [])   # 容 dict-or-list(现状归一)
    return {"life_events": [e for e in events if isinstance(e, dict)]}
```
加 import:`from .llm_validate import complete_validated`、`from . import schemas`(`mining.py` 已有 `gate`/`prompts`/`sys`?确认 `import sys` 已在——A3.1 的 `_extract_one` 已加过,核对;若无则加)。

- [ ] **Step 4: 网守 + 文档**

Run: `python -m pytest tests/test_a3_landmarks.py tests/test_mining.py tests/test_llm_validate.py -q`
Expected: 全绿(fail 浮现 + happy 不变 + 裸 list 保留)。
刷新 `docs/design/tech-debt.md` A3 行备注:追加 `wave2: LIFE_EVENTS(mining._extract_life_one)经 complete_validated(callable schema schemas.parsed 容 dict-or-list)—— 解析失败 retry+stderr 浮现, 治静默丢生死事件; happy 逐位保持`。

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/mining.py docs/design/tech-debt.md tests/test_a3_landmarks.py
git commit -m "feat(A3 wave2): _extract_life_one 经 complete_validated — 畸形→retry+stderr浮现(治静默丢生死事件), 容dict-or-list, happy不变"
```

---

## Self-Review

- **Spec 覆盖**:① callable schema + parsed → Task 1;② LIFE_EVENTS 迁移 → Task 2;③ dict-or-list 容忍 → `schemas.parsed` + 裸 list 测;④ happy 网守 → Task 2 Step4(test_mining);⑤ fail-path mock 测 → Task 2。✅
- **向后兼容**:Task 1 backward-compat 测(dict schema 仍走 validate)守既有 REVIVAL_VERIFY/EXTRACT_CHUNK 不退化。
- **占位**:Task 2 标注"读现状确认 import sys";新代码(Task 1 + Task 2 迁移体 + 测试)给完整代码。
- **类型一致**:`schemas.parsed`/`complete_validated(schema=dict|callable)`/`_extract_life_one` 跨任务一致;测试复用各文件本地 `_FakeCli`。
- **风险**:① callable schema 改 A3.1 已合并 infra → backward-compat 测守;② 裸 list 保留(`schemas.parsed`)避免重蹈 A3.1 过严丢数据;③ happy 首调用温度显式 0.2 = 原值。
