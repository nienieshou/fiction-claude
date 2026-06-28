# A3 wave4 — verify_identity 静默失败硬化(可见不动门)设计

> 2026-06-28 · 技术债 A3(LLM 输出契约校验)第四波。接 wave2/wave3(complete_validated / detect_retry 共享重试 + stderr 浮现)。
> 基于:`master`。配套:`docs/design/tech-debt.md` A3 行。

## 背景(已核实,master)

`prose_facts.verify_identity`(`prose_facts.py:208-236`)对身份类 findings 逐条 LLM 判真矛盾,annotate `f["real"]`。内层 `_judge`(`:214-231`)是手抄 2 次重试循环:

```python
real = False                                  # 默认 false(存疑不报)
for k in range(2):
    raw = await cli.complete("chunk_extract", sys_p, usr,
                             json_mode=True, max_tokens=200, temperature=0.0 + 0.1 * k)
    r = _safe_json(raw)
    if isinstance(r, dict) and "real" in r:
        real = bool(r["real"]); f["reason"] = str(r.get("reason", ""))[:30]; break
f["real"] = real
```

**命门**:`real=False` 默认是**有意**的「存疑不报」。故 LLM 解析**耗尽**(两试均 malformed / 缺 `real` 键)与「LLM 确判为假」产出**同一个 `real=False`**,无法区分。该 finding 静默掉出 `spine_id_contra` 计数。

**消费链**:`verify_identity` 后 `produce.py:1123` `spine_net_id = sum(... cat=="身份" and f.get("real"))` → 门信号 `身份真矛盾`(`produce.py:1212`)→ `数值真矛盾+身份真矛盾≥6` 硬门。

**调用条件(诚实收窄)**:调用点 `produce.py:1119-1123` 由 `HIKI_SPINE=="1"` **且** `spine_net_num<2` **且** 存在身份 finding 三重守。即此静默洞**仅在 `--spine` 开时**才咬人(与 event_state 同激活类),非「永远在跑」。但 spine 开时它是承重身份硬门,静默假阴是真的。

**攻击路径**:spine 开,6 条真身份矛盾,其中 1 条 verify LLM 解析耗尽 → 静默 `real=False` → `spine_net_id=5` < 6 → 门不响 → 承重硬伤静默出货。无 stderr、无计数、无标记。

## 目标

把 `_judge` 的 infra 真失败从「判定假」分离并**可见**(stderr + 落盘标记 + 报告 advisory),换共享重试基础设施。**门行为逐位保持**(耗尽仍 `real=False`,`spine_id_contra` 字节同);可见性是新增,不动门。

**风险姿态**:门字节不变(用户选「可见但不动门」);只新增一个 `verify_failed` 标记 + stderr + advisory 串。

## 架构

### ① `_judge` 换 `complete_validated`(`prose_facts.py:214-231`)

`complete_validated(cli, stage, sys_p, usr, *, schema, retries=3, **complete_kw)`(`llm_validate.py:8`,wave2 落的共享 infra:validate→retry→None)。`schema` 可为 callable 谓词。

```python
async def _judge(f: dict) -> None:
    va, vb = f.get("va", ""), f.get("vb", "")
    if not (va and vb):
        f["real"] = True
        return
    usr = usr_t.format(who=f["who"], ca=f["ch_a"], va=va, cb=f["ch_b"], vb=vb,
                       ctx_a=_ctx(ch_texts, f["ch_a"], f["who"]),
                       ctx_b=_ctx(ch_texts, f["ch_b"], f["who"]))
    r = await complete_validated(cli, "chunk_extract", sys_p, usr,
                                 schema=lambda r: isinstance(r, dict) and "real" in r,
                                 retries=2, json_mode=True, max_tokens=200, temperature=0.0)
    if r is not None:
        f["real"] = bool(r["real"])
        f["reason"] = str(r.get("reason", ""))[:30]
    else:
        f["real"] = False              # 保『存疑不报』+ 门字节同
        f["verify_failed"] = True      # 唯一新增: infra真失败 与 判定假 分开
```

**温度逐位等价**:`complete_validated` `base_t=complete_kw.pop("temperature",0.2)`;传 `temperature=0.0` → `base_t=0.0` → 两试 0.0、0.1,与原 `0.0+0.1*k` 完全同。`retries=2` 同原 2 次。成功才设 `reason` 同原。空 `va/vb` 早返(无 LLM 调用,非失败)不变。

### ② 可见性 — stderr + 落盘标记(`verify_identity`,`gather` 后)

```python
await asyncio.gather(*[_judge(f) for f in findings if f.get("cat") == "身份"])
nf = sum(1 for f in findings if f.get("cat") == "身份" and f.get("verify_failed"))
if nf:
    print(f"⚠️ 身份验证LLM重试耗尽 {nf} 条(存疑默认不报,未进门)", file=sys.stderr)
for f in findings:
    f.setdefault("real", True)                    # 非身份类默认真(原行,不动)
return findings
```

`verify_failed` 标记随 findings 写入 `fact_table.json`(`produce.py:1126`)— **免费落盘**,人工校准环可查,**无需**穿 produce.py 层叠 dict。(合测量边界备忘:系统出客观信号,人工决策。)

`prose_facts` 需 import:`complete_validated`(从 `.llm_validate`)、`sys`(stderr,确认已 import)。

### ③ 报告 advisory 浮现(`produce.py:_fact_audit_repair`,非门)

`_fact_audit_repair`(`produce.py:1125` 一带)已有 `fact_adv` advisory 列表。在 verify_identity 调用后(`:1123` 一带,仍在 `HIKI_SPINE` 块内或 `fact_adv` 组装处)计 `nf` 并入:

```python
        nf = sum(1 for f in ft["findings"] if f.get("cat") == "身份" and f.get("verify_failed"))
        if nf:
            fact_adv.append(f"身份验证LLM耗尽{nf}条(存疑未进门)")
```

`fact_adv` 是 advisory(`produce.py:1125` 组装,流向报告 advisory 通道),不进 `sig`/门决策。仅一行追加,无新返回键、无新门信号。

## 验证

- **焦点测**(新 `tests/test_verify_identity_silent.py`,mock cli):
  - 两试均返回不可解析 → `f["real"]==False` **且** `f["verify_failed"]==True`;`capsys` 见 stderr `身份验证LLM重试耗尽`。
  - 可解析 `{"real": true, "reason": "x"}` → `f["real"]==True`、`f["reason"]=="x"`、**无** `verify_failed` 键。
  - 可解析 `{"real": false}` → `f["real"]==False`、**无** `verify_failed`(判定假≠infra失败)。
  - 空 `va/vb` finding → `real=True` 早返,无 LLM 调用、无 `verify_failed`。
- **门等价**:`signal_counts_from_fact_table`(`:185`)对含 `verify_failed` 的 findings 的 `spine_id_contra` 计数不变(只数 `real`,新键不碰 `real`)。
- **金标/装配回归网绿**:冻结信号向量不含 `verify_failed`;`real` 字节同 → `spine_id_contra` 同 → 天然绿。
- 既有 `test_produce_units`/`test_stages`/prose_facts 相关测绿。
- 全量 `pytest -m 'not api'` 绿,报确切 passed/deselected。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标

- **不动门**:不 fail-closed、不把耗尽计作 `real=True`、不加新硬门信号。耗尽仍 `real=False`,`spine_id_contra` 字节同。
- **不加 config 旋钮**(无 lean/fail-closed 开关,YAGNI)。
- **不碰** `extract_facts`(`n_unaudited`>25% → `承重审计崩溃` 已覆盖)、`fact_audit`(`prose_facts.py:52`,仅 eval 脚本,不在主管线)、event_audit(advisory/spine 门控)。
- 不改 `IDENTITY_VERIFY` prompt、不改 `real=False` 默认「存疑不报」语义、不改 `reason` 截断。

## 风险

- **为何不动门**:`real=False` 默认是有意噪声控制;`≥6` 阈值下单条欠计极少翻真书(需恰好 6 真 + ≥1 耗尽)。比例修复 = 可见 + 共享重试,非新硬门。fail-closed 会引假阳(本可能假矛盾)且与「存疑不报」相左。
- **新 `verify_failed` 键**:只读不入门;落盘 `fact_table.json` 为客观长线信号。装配网只数 `real`,不破。
- **stderr 新行**:可能被捕获 stderr 的测看到,但未见断言;wave2/wave3 同式浮现先例。
- **import 循环**:`prose_facts` → `llm_validate` → `gate`(`_safe_json`)+`schemas`;`prose_facts` 已用 `_safe_json`(同源 `gate`),`gate` 不 import `prose_facts`,无环(实现期由 import 即验证)。
