# C6 残留 — slice_validate.py 纪律拉齐(EXTRACT 失软 + craft_audit 门控)设计

> 2026-06-29 · 技术债 C6(检测器 sprawl / 白烧)收尾 + A3(LLM 契约)在 dev 工具的最后两处。
> 接 C6②(produce.py craft_audit config 门控)、A3 wave4/wave5(生产路静默硬化)。基于:`master`。配套:`docs/design/tech-debt.md` C6 行。

## 背景(已核实,master)

`slice_validate.py` 是 **M0 内核切片验证** dev/eval CLI 工具(`python -m hiki.slice_validate <源.txt>`,"最便宜地验证最危险的假设…产出供人工评判"),**非**生产出货管线(`produce.py`/`run`)。它两处未拉齐生产纪律:

| 站点 | 位置 | 现状 | 主题 |
|---|---|---|---|
| EXTRACT 解析 | `_json`(`:28-32`)用于 `:176` | 裸 `json.loads`(去 ```json 围栏后), **无 try/except** → malformed/截断 LLM JSON 抛 `JSONDecodeError`(丑栈);`dna["scenes"]`(`:186`)对 partial dict 再 KeyError | 健壮性 |
| craft_audit | `:280` | `await audit.craft_audit(cli, final)`(~2500tk)无条件烧, 结果仅入报告 `audit_人+故事性_craft(advisory)`(`:293`), **未** `config.advisory_on` 门控 —— C6② 记下的残留 | token 白烧 |

`_json` 仅 `:176` 一处用(grep 实证)→ 可替换并删除。`_do_plan`(`:192`)已 `gate._safe_json or {}` 失软不崩;`_draft_candidates`(`:63`)是 prose 生成非 JSON —— 二者非 A3 式洞, 不动。

`slice_validate` 现 import `from . import prompts, gate, ledger, audit`(无 `config`/`complete_validated`)。`run()` 是大函数、无测试覆盖。

## 目标

把 dev 工具两处拉齐生产纪律:① EXTRACT 失败从"丑崩"变"重试后干净 RuntimeError"(镜 `_plan_macro`/`reduce_bible`);② craft_audit 白烧接 `config.advisory_on`(镜 C6②,默认开行为保持)。**因 `run()` 无测试且过大, 抽两个小可测 helper** 而非内联改 —— 给真单测 + 微解 god-function(对所触代码的定向改良)。

**风险姿态**:happy 路字节保持(EXTRACT 首试 temp 0.3 同今;craft 默认开照烧);新增仅"失败干净化"+"白烧可关"。dev 工具内, 不动出货/门。

## 架构

### ① `_extract_dna` helper(替 `_json` + `:176`,删 `:28-32`)

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
`run()` 内 `:176` 改 `dna = await _extract_dna(cli, slice_src)`。

- **happy 首试字节等价**:`complete_validated` base_t=0.3 → 首试 temp **0.3**(同原单发)、二试 0.4(仅首试败);`json_mode=True/max_tokens=8000` 同。内部 `gate._safe_json` 对干净/围栏响应与原 `_json`(strip 围栏 + `json.loads`)同果(且更鲁棒)。
- **失败干净化**:原 malformed → `JSONDecodeError` 裸崩;现重试耗尽 → `RuntimeError`(可读, 同 `_plan_macro`/`reduce_bible` 风格)。schema 要求 `scenes` 为非空 list → 守卫后 `dna["scenes"]`(`:186`)永远安全, 消除 partial-dict KeyError。
- **删 `_json`(`:28-32`)**:仅此一处用, 删除即消重(单源走共享 infra)。

### ② `_craft_advisory` helper(门控 `:280`,镜 C6②)

```python
async def _craft_advisory(cli: Client, final: str, cfg: dict) -> list:
    """C6: craft 人/故事性评审(~2500tk, 纯 advisory)。config 可关省 token, 默认开。"""
    if config.advisory_on(cfg, "craft_audit"):
        return await audit.craft_audit(cli, final)
    return ["(craft advisory 已关:config.advisories.craft_audit)"]
```
`run()` 内:开头加 `cfg = config.load("pipeline") or {}`(一次);`:280` 改 `audit_craft = await _craft_advisory(cli, final, cfg)`。报告行 `:293`(`audit_craft or ["无"]`)逐字不变。

- **默认开 → 行为保持**:`advisory_on(cfg, "craft_audit")` 缺省 `default=True` → craft 照烧、报告同。`config.advisories.craft_audit: false` 跳烧 + 占位串(与 C6② produce.py 同串/同语义)。

### ③ import(`:14`)

```python
from . import prompts, gate, ledger, audit, config
from .llm_validate import complete_validated
```
(`config`/`llm_validate` 均不 import `slice_validate`,无循环。)

## 验证

- **`_extract_dna` 单测**(新 `tests/test_slice_validate_robust.py`,fake cli):
  - 合法 `{"scenes":[...], "voice":..., "bible":...}` → 返回 dna、`cli.calls==1`(首试通过)。
  - 两试均不可解析 → `RuntimeError`、`cli.calls==2`。
  - partial(parse 成功但无 `scenes` / `scenes` 空)→ 重试 → 耗尽 `RuntimeError`。
- **`_craft_advisory` 单测**(同文件,monkeypatch `audit.craft_audit` 计数):
  - `cfg={"advisories":{"craft_audit":False}}` → 返回占位串、`audit.craft_audit` **不**被 await(计数 0)。
  - `cfg={}`(默认)/ `True` → craft 被调, 结果入返回。
- **全量 `pytest -m 'not api'`** 绿,报确切 passed/deselected。
- **金标/装配回归网**:不经 slice_validate 路 → 不覆盖本改;等价依据为 happy 首试逐位同论证 + 上述单测(spec 显记)。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标

- **dev 工具内**:不动出货管线(`produce.py`/`run`)、不动任何交付门信号。
- **不碰** `_do_plan`(`:192`,已 `_safe_json` 失软)、`_draft_candidates`(`:63`,prose 非 JSON)、PICK 解析(`:87`,已 `_safe_json`)。
- **不加新 config 旋钮**:复用 C6② 的 `config.advisories.craft_audit`(同键, 已在 `config/pipeline.yaml` 记)。
- 不改 EXTRACT / craft prompt、不改报告键名、不改 craft_audit 自身逻辑。
- 不顺手重构 `run()` god-function 其余部分(仅抽这两小 helper, B1 另案)。

## 风险

- **EXTRACT 改抛 vs 原崩**:二者都是"失败即停"(无合理 scenes 无法续), 仅从裸 `JSONDecodeError` 升级为可读 `RuntimeError` + 重试一次 → 净改善, 非行为倒退。happy 首试字节同。
- **抽 helper 改动面**:`_extract_dna`/`_craft_advisory` 是 `run()` 内联逻辑外提, 行为等价;给可测性 + 微解大函数。run() 调用点各一行。
- **craft 默认开**:质量 > token(craft advisory 喂人工三维, 测量边界备忘);省 token 由量产显式置 `false`,默认保行为。
- **stderr/异常面**:`complete_validated` 不吞 `cli.complete` 抛(与原 `_json` 路径异常面平价, 仅解析失败由崩变重试+RuntimeError)。
