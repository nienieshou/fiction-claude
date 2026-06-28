# A3 wave 2 — LIFE_EVENTS schema 校验设计

> 2026-06-28 · 技术债 A3 第二波(接 A3.1)。范围:**仅 LIFE_EVENTS 契约**(唯一清晰的数据丢失 bug)。
> 基于:`master`(独立)。配套:`docs/design/tech-debt.md` A3 行、A3.1 spec(infra 来源)。

## 目标

把 `mining._extract_life_one`(LIFE_EVENTS 契约)从"解析失败静默丢生死事件"改成"validate→retry→浮现丢失",复用 A3.1 的 `llm_validate.complete_validated`。顺带把 infra 扩成支持 **callable schema**(数据契约容 dict-or-list)。

**风险姿态(同 A3.1):happy-path 逐位保持,失败路径有意 fail-closed。**

## 现状(已核实,master)

`mining._extract_life_one`(`mining.py:61-69`):
```python
raw = await cli.complete("chunk_extract", sys_p, usr_t.format(chunk=chunk[:60000], roster=roster),
                         json_mode=True, max_tokens=1500, temperature=0.2)
r = gate._safe_json(raw)                       # 无 retry
events = r if isinstance(r, list) else (r.get("life_events") or [] if isinstance(r, dict) else [])
return {"life_events": [e for e in events if isinstance(e, dict)]}
```
- **无 retry**;解析失败(`r=None`)→ `events=[]` → 返 `{"life_events": []}`(**静默丢生死事件**,喂 lifearc mining 的死亡/复活弧)。
- **容忍 LLM 返 dict `{"life_events":[...]}` 或裸 list `[...]`**(注释:flaky LLM 偶尔吐裸数组)。
- `_safe_json` 返 `dict | list | None`(拒裸标量)。

## 架构

### ① infra 小扩(向后兼容):`complete_validated` 接受 callable schema
A3.1 的 `complete_validated(..., schema, ...)` 现 `validate(r, **schema)`(schema 须 dict)。LIFE_EVENTS 的有效性 = "解析出 dict 或 list"(非 dict-only),用 A3.1 的 dict-required schema 会把**裸 list 判无效→丢**(正是 opus 在 A3.1 抓的"过严丢可解析数据" Important)。故扩 schema 可为 **dict 或谓词 callable**:
```python
# src/hiki/llm_validate.py  complete_validated 内:
        r = _safe_json(raw)
        if (schema(r) if callable(schema) else validate(r, **schema)):
            return r
```
既有调用(`REVIVAL_VERIFY`/`EXTRACT_CHUNK` 传 dict)零影响。

`src/hiki/schemas.py` 加:
```python
def parsed(r) -> bool:
    """解析出非空(dict 或 list)即有效——数据契约容 dict-or-list(如 LIFE_EVENTS)。_safe_json 返 dict|list|None。"""
    return r is not None
```

### ② LIFE_EVENTS 迁移(`mining._extract_life_one`)
```python
async def _extract_life_one(cli: Client, chunk: str, roster: str = "（本段出现的所有人物）") -> dict:
    sys_p, usr_t = prompts.LIFE_EVENTS
    r = await complete_validated(cli, "chunk_extract", sys_p,
                                 usr_t.format(chunk=chunk[:60000], roster=roster),
                                 schema=schemas.parsed, retries=2, json_mode=True,
                                 max_tokens=1500, temperature=0.2)   # 显式 0.2 = 原温度(不靠默认巧合)
    if r is None:                              # A3: 解析失败(重试后)→ 浮现丢失(非静默)
        print("⚠ LIFE_EVENTS 重试后仍无效,该段生死事件零贡献", file=sys.stderr)
        return {"life_events": []}
    events = r if isinstance(r, list) else (r.get("life_events") or [])   # 容 dict-or-list(现状归一不变)
    return {"life_events": [e for e in events if isinstance(e, dict)]}
```
加 import:`from .llm_validate import complete_validated`、`from . import schemas`(`mining.py` 已有 `gate`/`prompts`,保留)。
- **happy-path 逐位保持**:首调用温度=0.2(原温度);dict-or-list 归一 + `isinstance(e,dict)` 过滤逻辑不变。
- **失败路径**:原静默 `[]` → 2-retry + stderr 浮现 + `{"life_events": []}`。

## 验证

- `tests/test_llm_validate.py` 扩:`complete_validated` 接 **callable schema**——谓词返 True 即返 r、返 False 则重试;`schemas.parsed`(dict/list→True,None→False)。
- `tests/test_a3_landmarks.py` 扩(LIFE_EVENTS,mock cli):
  - 畸形(全程 `_safe_json`=None)→ stderr 浮现(capsys)+ 返 `{"life_events": []}`。
  - valid dict `{"life_events":[{...}]}` → events 提取。
  - **valid 裸 list `[{...}]`** → events 提取(证不丢可解析数据,避免重蹈 A3.1 Important)。
  - 非 dict 元素被 `isinstance(e,dict)` 滤除(现状不变)。
- happy 不变:既有 `test_mining` + 全量绿。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- 其余"安全方向/advisory"Class-B 契约(`PROSE_NAME_VERIFY` 不合并=安全 / `SCENE_SCORE` 启发式回退 / `PLANE_CHECK` reenact advisory)—— 不动(fail-open 非 bug)。
- Class A/C 契约。不搬 `_safe_json`。不改 happy-path。

## 风险
- **callable schema 扩 infra**:改的是 A3.1 已合并的 `complete_validated`。扩为向后兼容(dict 走旧路);既有 REVIVAL_VERIFY/EXTRACT_CHUNK 测试守不退化。
- **dict-or-list 容忍**:`schemas.parsed` 只要求"解析出非空",故裸 list(可解析数据)保留——避免重蹈 A3.1 EXTRACT_CHUNK 过严丢数据。归一逻辑(`r if list else r.get`)与现状逐字一致。
- happy-path:首调用温度 0.2 = 原单次调用,LIFE_EVENTS 正常返回时行为同原(1 次调用);仅解析失败时多调用 + 浮现。
