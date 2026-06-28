# A3 wave4 — verify_identity 静默失败硬化(可见不动门)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `prose_facts.verify_identity._judge` 的 LLM 解析耗尽(infra 真失败)从「判定假」分离并可见(换 `complete_validated` 共享重试 + `verify_failed` 落盘标记 + stderr + 报告 advisory),门行为逐位保持。

**Architecture:** 三处改动:① `_judge` 手抄 2 试循环换 `complete_validated`,耗尽时 `real=False`(不变)+ 标 `f["verify_failed"]=True`;② `verify_identity` gather 后 stderr 浮现耗尽条数(标记随 findings 写入 `fact_table.json`);③ `produce._fact_audit_repair` 把耗尽数追加进既有 `fact_adv` advisory 列表(非门)。

**Tech Stack:** Python ≥3.10,标准库 + pytest。无新第三方依赖。

**设计依据:** `docs/superpowers/specs/2026-06-28-a3-wave4-verify-identity-silent-failure-design.md`(读它拿命门/调用条件/门等价论证)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。**
- **门字节保持**:解析耗尽仍 `real=False`;`spine_id_contra`(`prose_facts.py:193` / `produce.py:1123`)计数不变;唯一新增 `verify_failed` 是只读标记,不入 `sig`/门决策。
- **温度逐位等价**:`complete_validated` 传 `temperature=0.0, retries=2` → 两试 temp 0.0/0.1,与原 `0.0+0.1*k`、2 次完全同。
- **判定假 ≠ infra 失败**:LLM 成功返回 `{"real": false}` 时**不**标 `verify_failed`;仅两试均解析失败(返回 None)才标。
- `pytest -m 'not api'` 离线全绿 + 金标/装配回归网绿。编码 UTF-8。

---

## Task 1: prose_facts `_judge` 换 complete_validated + verify_failed 标记 + stderr 浮现

**Files:**
- Modify: `src/hiki/prose_facts.py`(import 区 `:7-17` 加一行;`_judge` `:214-231`;`verify_identity` gather 后 `:233-236`)
- Create: `tests/test_verify_identity_silent.py`
- Read first: `prose_facts.py:208-236`(verify_identity/_judge 现状)、`prose_facts.py:185-195`(signal_counts_from_fact_table 门计数)、`llm_validate.py:8`(complete_validated 签名)

**Interfaces:**
- Consumes: `llm_validate.complete_validated(cli, stage, sys_p, usr, *, schema, retries=3, **complete_kw) -> dict | None`(现存,不改);`schema` 可为 callable 谓词。
- Produces: `prose_facts.verify_identity(cli, findings, ch_texts) -> list[dict]`(签名不变);耗尽的身份 finding 多带 `f["verify_failed"]=True`;耗尽时向 stderr 印 `⚠️ 身份验证LLM重试耗尽 N 条(...)`。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_verify_identity_silent.py`:
```python
"""A3 wave4: verify_identity 静默失败硬化 —— infra真失败(LLM解析耗尽)与判定假分离。
零 API; fake cli 按固定串回应。"""
import asyncio
from hiki import prose_facts


class _Cli:
    """每次 complete 返回同一固定串; 记调用次数。"""
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def complete(self, *a, **k):
        self.calls += 1
        return self.reply


def _id_finding() -> dict:
    return {"cat": "身份", "who": "张三", "va": "圣子", "vb": "圣帝", "ch_a": 1, "ch_b": 2}


_CHS = ["首章 张三 自称圣子 行走江湖", "次章 张三 被尊圣帝 君临天下"]


def test_parse_exhaustion_flags_verify_failed_and_warns(capsys):
    cli = _Cli("这不是json")
    f = _id_finding()
    asyncio.run(prose_facts.verify_identity(cli, [f], _CHS))
    assert f["real"] is False                 # 保『存疑不报』
    assert f.get("verify_failed") is True      # infra真失败被标
    assert cli.calls == 2                       # retries=2
    assert "身份验证LLM重试耗尽" in capsys.readouterr().err


def test_parse_success_real_true_no_flag():
    cli = _Cli('{"real": true, "reason": "圣子与圣帝同维互斥"}')
    f = _id_finding()
    asyncio.run(prose_facts.verify_identity(cli, [f], _CHS))
    assert f["real"] is True
    assert f["reason"] == "圣子与圣帝同维互斥"
    assert "verify_failed" not in f
    assert cli.calls == 1                       # 首试成功即 break


def test_judged_false_is_not_infra_failure():
    cli = _Cli('{"real": false}')
    f = _id_finding()
    asyncio.run(prose_facts.verify_identity(cli, [f], _CHS))
    assert f["real"] is False
    assert "verify_failed" not in f            # 判定假 ≠ infra失败
    assert cli.calls == 1


def test_empty_values_short_circuit_no_llm():
    cli = _Cli("不该被调用")
    f = {"cat": "身份", "who": "张三", "va": "", "vb": "", "ch_a": 1, "ch_b": 2}
    asyncio.run(prose_facts.verify_identity(cli, [f], _CHS))
    assert f["real"] is True
    assert "verify_failed" not in f
    assert cli.calls == 0                       # va/vb 空 → 早返, 无 LLM 调用


def test_verify_failed_does_not_leak_into_gate_count():
    """门等价钉死: verify_failed 标记不改 spine_id_contra(只数 real)。"""
    findings = [
        {"cat": "身份", "real": True},
        {"cat": "身份", "real": False, "verify_failed": True},
    ]
    counts = prose_facts.signal_counts_from_fact_table({"findings": findings})
    assert counts["spine_id_contra"] == 1
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_verify_identity_silent.py -q`
Expected: FAIL — `test_parse_exhaustion_flags_verify_failed_and_warns` 断 `verify_failed`/stderr 失败(现 `_judge` 不标不印);`test_judged_false_is_not_infra_failure` 可能已过(现默认 false 但也不标 verify_failed,恰过)。至少耗尽与 stderr 两断言失败。

- [ ] **Step 3: import complete_validated(`prose_facts.py:14` 一带)**

在 `from .gate import _safe_json`(`:14`)下加一行:
```python
from .llm_validate import complete_validated
```
(`prose_facts` 已 import `sys`(`:11`)供 stderr;`llm_validate` 仅 import `gate`+`schemas`,`gate` 不 import `prose_facts`,无循环。)

- [ ] **Step 4: `_judge` 换 complete_validated + 标 verify_failed(`prose_facts.py:214-231`)**

把现 `_judge`(`:214-231`):
```python
    async def _judge(f: dict) -> None:
        va, vb = f.get("va", ""), f.get("vb", "")
        if not (va and vb):
            f["real"] = True
            return
        usr = usr_t.format(who=f["who"], ca=f["ch_a"], va=va, cb=f["ch_b"], vb=vb,
                           ctx_a=_ctx(ch_texts, f["ch_a"], f["who"]),
                           ctx_b=_ctx(ch_texts, f["ch_b"], f["who"]))
        real = False                                  # 默认 false(存疑不报)
        for k in range(2):
            raw = await cli.complete("chunk_extract", sys_p, usr,
                                     json_mode=True, max_tokens=200, temperature=0.0 + 0.1 * k)
            r = _safe_json(raw)
            if isinstance(r, dict) and "real" in r:
                real = bool(r["real"])
                f["reason"] = str(r.get("reason", ""))[:30]
                break
        f["real"] = real
```
改为:
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
            f["real"] = bool(r["real"])               # LLM 成功裁决
            f["reason"] = str(r.get("reason", ""))[:30]
        else:
            f["real"] = False                         # 解析耗尽: 保『存疑不报』+ 门字节同
            f["verify_failed"] = True                 # 唯一新增: infra真失败 与 判定假 分开
```

- [ ] **Step 5: gather 后 stderr 浮现(`prose_facts.py:233-236`)**

把现:
```python
    await asyncio.gather(*[_judge(f) for f in findings if f.get("cat") == "身份"])
    for f in findings:
        f.setdefault("real", True)                    # 非身份类默认真
    return findings
```
改为(在 gather 与默认真之间插浮现):
```python
    await asyncio.gather(*[_judge(f) for f in findings if f.get("cat") == "身份"])
    nf = sum(1 for f in findings if f.get("cat") == "身份" and f.get("verify_failed"))
    if nf:
        print(f"⚠️ 身份验证LLM重试耗尽 {nf} 条(存疑默认不报,未进门)", file=sys.stderr)
    for f in findings:
        f.setdefault("real", True)                    # 非身份类默认真
    return findings
```

- [ ] **Step 6: 跑确认通过**

Run: `python -m pytest tests/test_verify_identity_silent.py -q`
Expected: PASS（5 passed）

- [ ] **Step 7: 门等价回归网(零门改动验证)**

Run: `python -m pytest tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全绿(`real` 字节同 → `spine_id_contra` 同 → 冻结信号向量不动)。

- [ ] **Step 8: 提交**

```bash
git add src/hiki/prose_facts.py tests/test_verify_identity_silent.py
git commit -m "feat(A3 wave4): verify_identity 换 complete_validated + verify_failed 标记 + stderr 浮现(门字节保持)"
```

---

## Task 2: produce 报告 advisory 浮现耗尽数(非门)+ tech-debt 刷新

**Files:**
- Modify: `src/hiki/produce.py`(`_fact_audit_repair` 内 `fact_adv` 组装处 `:1125` 一带)
- Modify: `docs/design/tech-debt.md`(A3 行)
- Read first: `produce.py:1119-1139`(`_fact_audit_repair` 的 HIKI_SPINE 块 + fact_adv + 返回 dict)

**Interfaces:**
- Consumes: `prose_facts.verify_identity` 已标的 `f["verify_failed"]`(Task 1 产);`ft["findings"]`(现存)。
- Produces: 无新签名/返回键;仅向既有 `fact_adv: list[str]` 追加一条 advisory 串(流向报告 advisory 通道,不入 `sig`/门)。

- [ ] **Step 1: 追加 advisory(`produce.py:1125` 一带)**

定位 `_fact_audit_repair` 内的 fact_adv 组装行(`:1125`):
```python
        fact_adv = [f["why"] for f in ft["findings"] if f.get("conf") in ("高", "中")]
```
在其**后**插入(仍在 `try` 内、`fact_table.json` 写盘 `:1126` 之前):
```python
        nf_verify = sum(1 for f in ft["findings"] if f.get("cat") == "身份" and f.get("verify_failed"))
        if nf_verify:
            fact_adv.append(f"身份验证LLM耗尽{nf_verify}条(存疑未进门)")
```
(spine 关时 findings 无 `verify_failed` → `nf_verify=0` → 无操作,任何路径安全。)

- [ ] **Step 2: 跑装配/单元相关测确认不破**

Run: `python -m pytest tests/test_assembly_regression.py tests/test_gold_regression.py -q`
Expected: 全绿(advisory 串非冻结信号向量成员)。

- [ ] **Step 3: 全量离线套**

Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。报确切 passed/deselected 数。

- [ ] **Step 4: 刷新 `docs/design/tech-debt.md` A3 行**

A3 行备注追加:
```
A3 wave4 已落: verify_identity._judge 换 complete_validated 共享重试 + 解析耗尽标 verify_failed(落盘 fact_table.json) + stderr 浮现 + 报告 advisory。门字节保持(耗尽仍 real=False, spine_id_contra 不变); 仅 HIKI_SPINE 开时激活。残: extract_facts 逐章失败 per-chapter 浮现(已被 n_unaudited>25% 聚合门覆盖, 边际低)。
```

- [ ] **Step 5: 提交**

```bash
git add src/hiki/produce.py docs/design/tech-debt.md
git commit -m "feat(A3 wave4): 报告 advisory 浮现身份验证耗尽数(非门) + tech-debt 刷新"
```

---

## Self-Review

- **Spec 覆盖**:① `_judge` 换 complete_validated + verify_failed → Task 1 Step 3-4;② stderr + 落盘标记 → Task 1 Step 5(标记随 findings 入 fact_table.json,Task 2 无需重复落盘);③ 报告 advisory → Task 2 Step 1;门等价验证 → Task 1 Step 7 + Task 2 Step 2-3。✅
- **门字节保持**:耗尽 `real=False` 不变;`signal_counts_from_fact_table` 只数 `real`(Task 1 `test_verify_failed_does_not_leak_into_gate_count` 钉死);金标/装配网验收。
- **占位**:无 TBD;所有代码步给完整前后码;测试文件完整。
- **类型一致**:`verify_identity(cli, findings, ch_texts) -> list[dict]` 签名跨 spec/plan/测一致;`complete_validated(..., schema, retries, **kw) -> dict|None` 与 `llm_validate.py:8` 现状一致;`signal_counts_from_fact_table(ft) -> dict` 键 `spine_id_contra` 与 `prose_facts.py:193` 一致。
- **温度等价**:Task 1 Step 4 注释 + Global Constraints 双记 `temperature=0.0,retries=2` → 0.0/0.1 两试,与原 `0.0+0.1*k` 同。
- **风险**:① import 循环 → Step 3 已论证无环(gate 不 import prose_facts);② `verify_failed` 漏进门 → Task 1 第 5 测守;③ spine 关时 Task 2 追加误触 → `nf_verify=0` no-op。
