# A3.1 LLM 输出 schema 校验层(基础设施 + 2 标杆)设计

> 2026-06-27 · 技术债 A3(可靠性:LLM 输出零 schema 校验)首切。范围:**校验基础设施 + 2 标杆契约**。
> A3 全量 30 契约/34 调用点 —— 本 spec 只做 infra + 2 标杆证明模式;其余 28 契约后续波。
> 基于:`master`(独立)。配套:`docs/design/tech-debt.md` A3 行。

## 目标

建可复用的 `validate(raw, schema) → retry → reject` 层,替换散落的 ad-hoc retry 循环与 `_safe_json or {}` 静默默认;在 2 个高危标杆契约上证明模式。

**风险姿态(关键,与 C1/C2/C5 不同)**:A3 **本质上改失败路径行为**——现状"解析失败→静默默认 = fail-open",A3 改成"validate→retry→失败显式处理 = fail-closed"。这是 A3 的**目的**,非 bug。
- **happy-path(LLM 正常返回)逐位保持**:既有测试 + 全量 + 金标网证不变。
- **失败路径有意改 fail-closed**:新测注入畸形 LLM 输出(mock cli)验新行为。

## 现状(已核实,master)

- `src/hiki/schemas.py`:23 行,仅 `IngestMeta`。其余契约全走裸 dict。
- `_safe_json`(`gate.py:82`):4 级恢复,解析失败返 `None`。54 个调用点、21 个 ad-hoc `for t/k in range` retry 循环散落。
- 标杆 1 **`PROSE_REVIVAL_VERIFY`**(`prose_continuity.py:229-243` `verify_revivals`):每候选 `cli.complete("chunk_extract", ..., json_mode=True, max_tokens=500, temperature=0.1)`(并发 gather),`v=_safe_json(c) or {}; if v.get("is_revival") is True: out.append(r)`。**无 retry**;解析失败→`{}`→`is_revival is True`=False→**候选静默丢弃(漏掉真复活)**。
- 标杆 2 **`EXTRACT_CHUNK`**(`mining.py:41-49` `_extract_one`):`cli.complete("chunk_extract", ..., max_tokens=8000, temperature=0.3)`,`r=gate._safe_json(raw) or {}`,标 `scene_cards` 的 `_chunk`。**无 retry**;解析失败→`{}`→空 scene_cards→**整 chunk 零贡献(静默丢数据)**。

## 架构

### 基础设施
**`src/hiki/schemas.py` 加**(纯):
```python
def validate(raw: dict, required, types: dict | None = None) -> bool:
    """轻量契约校验: required 键全在 + (可选)类型匹配。raw 须为 dict。"""
    if not isinstance(raw, dict):
        return False
    for k in required:
        if k not in raw:
            return False
    for k, t in (types or {}).items():
        if k in raw and not isinstance(raw[k], t):
            return False
    return True

# 标杆 schema 常量(读现状契约定精确键)
REVIVAL_VERIFY = {"required": ("is_revival",), "types": {"is_revival": bool}}
EXTRACT_CHUNK = {"required": ("scene_cards",)}   # 有 scene_cards 键=有效抽取(空列表合法); 无=解析失败
```

**新建 `src/hiki/llm_validate.py`**(避免循环导入;`_safe_json` 从 gate 导入,不搬动):
```python
from .gate import _safe_json
from .schemas import validate

async def complete_validated(cli, stage, sys_p, usr, *, schema, retries=3, **complete_kw):
    """cli.complete → _safe_json → validate; 失败重试(温度递增); 终败返回 None。
    返回 dict(有效)| None(retries 次后仍无效)——fail 动作由调用方显式处理。"""
    base_t = complete_kw.pop("temperature", 0.2)
    for t in range(retries):
        raw = await cli.complete(stage, sys_p, usr, temperature=base_t + 0.1 * t, **complete_kw)
        r = _safe_json(raw)
        if validate(r, **schema):
            return r
    return None
```
**返回 `dict | None`,fail 动作显式留调用点**(不藏 callback,每契约清晰可读)。

### 2 标杆迁移(各自 fail-closed 动作)
- **`verify_revivals`**(标杆1):每候选改用 `complete_validated(cli, "chunk_extract", sys_p, usr, schema=schemas.REVIVAL_VERIFY, retries=2, json_mode=True, max_tokens=500)`。
  - `r is None`(校验失败)→ **fail-closed:保留候选为存疑复活**(`out.append(r)`)——治"漏掉真复活"。
  - `r` 有效 → 用 `r["is_revival"]`(True 留,False 滤,与现状一致)。
  - 保持并发 gather。
- **`_extract_one`**(标杆2):改用 `complete_validated(cli, "chunk_extract", sys_p, usr, schema=schemas.EXTRACT_CHUNK, retries=2, json_mode=True, max_tokens=8000)`。
  - `r is None` → **fail-closed:浮现丢失**(`print(f"⚠ chunk {idx} EXTRACT_CHUNK 重试后仍无效,该窗零贡献", file=sys.stderr)` + 返回 `{}`)——不再静默(整本拒收对单坏窗过激,故"让丢失变响"而非 reject)。
  - `r` 有效 → 照常标 `_chunk` 返回。

## 验证

- `tests/test_llm_validate.py`:
  - `validate()` 谓词:required 全在/缺键/类型不符/非 dict。
  - `complete_validated`(mock cli):首次有效即返;前 N 次畸形→重试→末次有效返;全畸形→返 None;验温度递增、retries 次数。
- **fail-path 测试**(mock cli 返畸形):
  - `verify_revivals`:候选在 LLM 全畸形时**被保留**(fail-closed),非静默丢。
  - `_extract_one`:全畸形时返 `{}` + stderr 浮现(可用 capsys 验告警)。
- **happy-path 不变**:既有 `test_mining`/`test_prose_*`/全量 + **金标网**(revival→`ft_revival_residual` happy 零变化)。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- 其余 28 契约(Class A/B/C 后续波,各自 spec)。
- 不搬 `_safe_json`(54 站点,另议)。
- 不改 happy-path 行为。
- 不动"故意存疑不报"的契约(如 `IDENTITY_VERIFY` 失败→`real=False` 是防 FP 的设计,非 bug)。

## 风险
- **金标网只护 happy-path**:revival fail-closed 改变 `ft_revival_residual` **仅在 LLM 畸形时**;7 本金标的冻结信号是 happy-path,故金标网应零变化——若金标网红=happy 路径漂移了,回查。fail-path 改变靠 mock 测覆盖。
- **并发 gather + 重试**:`complete_validated` 在 gather 内多次 await,成本上升(重试);retries=2 控制。
- `validate` 对 `EXTRACT_CHUNK` 只要求 `scene_cards` 键——空列表算有效(章genuinely无场景),仅"无键/解析失败"算无效。确认这与"区分解析失败 vs 合法空"一致。
