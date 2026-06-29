# C7 余切 — 复活候选提取单源化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把逐字重复于 `produce._fact_audit_repair` 与 `point_repair._verified_revivals` 的生死→复活候选推导抽成 `prose_facts.revival_candidates(findings, n_ch)` 纯函数,两站点共用。

**Architecture:** 新增一个纯函数(无 LLM、无 IO),置于 `prose_facts.py` 的 `signal_counts_from_fact_table` 邻位;两调用点把 inline 列表推导换成函数调用。零行为改动(字节等价)。

**Tech Stack:** Python ≥3.10,标准库 + pytest。无新第三方依赖。`produce.py`/`point_repair.py` 均已 import `prose_facts`。

**设计依据:** `docs/superpowers/specs/2026-06-29-c7-revival-candidates-single-source-design.md`(读它拿两站点现状 + 范围 nuance:只抽推导不折叠 fact_table_audit)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** 编码 UTF-8。
- **纯重构字节等价**:逐字推导移入纯函数;两站点调用结果与原 inline 逐位同。不改候选字段名(`who`/`clue`/`revive_ch`/`death_ch`)、不改过滤(`cat=="生死"` + `isinstance(ch_b,int)` + `1<=ch_b<=n_ch`)、不改 0-based 转换。
- **只抽候选推导**:不折叠 `fact_table_audit` 调用进 helper(会双审计 produce)。下游 `if cand:` / `verify_revivals(...)` 不动。
- **宿主**:`prose_facts.py`(findings 生产者 + `signal_counts_from_fact_table` 同类纯函数邻居)。
- 不碰 `audit.check_revival`、`prose_continuity.find_revivals`、`RevivalRecord`、`verify_revivals`/`verify_revival_beats`/`repair_revivals_smart`。不加 config/门信号。
- TDD:先写失败测。金标/装配网覆盖 produce 路 → `cand` 字节等价验收。

---

## Task 1: 抽 `prose_facts.revival_candidates` + 两站点改调用

**Files:**
- Modify: `src/hiki/prose_facts.py`(`signal_counts_from_fact_table` 后,`:195` 一带新增函数)
- Modify: `src/hiki/produce.py`(`:1068-1071` 调用点)
- Modify: `src/hiki/point_repair.py`(`:62-65` 调用点)
- Create: `tests/test_revival_candidates.py`
- Read first: `prose_facts.py:185-196`(`signal_counts_from_fact_table` 邻位)、`produce.py:1062-1073`、`point_repair.py:60-66`(两站点现状)

**Interfaces:**
- Produces: `prose_facts.revival_candidates(findings: list[dict], n_ch: int) -> list[dict]` —— 纯函数;每条生死类、`ch_b` 为 int 且 `1<=ch_b<=n_ch` 的 finding → `{"who", "clue"(why[:30]), "revive_ch"(ch_b-1), "death_ch"(ch_a-1 或 None)}`。
- Consumes: 两站点的 `ft["findings"]`(`fact_table_audit` 输出)。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_revival_candidates.py`:
```python
"""C7 余切: prose_facts.revival_candidates 纯函数(生死→复活候选, 单源)。零 API。"""
from hiki import prose_facts


def _f(cat="生死", who="张三", ch_a=2, ch_b=5, why="死了"):
    return {"cat": cat, "who": who, "ch_a": ch_a, "ch_b": ch_b, "why": why}


def test_basic_revival_candidate():
    out = prose_facts.revival_candidates([_f()], 10)
    assert out == [{"who": "张三", "clue": "死了", "revive_ch": 4, "death_ch": 1}]


def test_non_revival_cats_excluded():
    out = prose_facts.revival_candidates([_f(cat="数值"), _f(cat="身份"), _f(cat="体系")], 10)
    assert out == []


def test_ch_b_out_of_bounds_or_non_int_excluded():
    assert prose_facts.revival_candidates([_f(ch_b=0)], 10) == []     # <1
    assert prose_facts.revival_candidates([_f(ch_b=11)], 10) == []    # >n_ch
    assert prose_facts.revival_candidates([_f(ch_b="x")], 10) == []   # 非 int(短路不崩)


def test_ch_a_non_int_yields_death_ch_none():
    out = prose_facts.revival_candidates([_f(ch_a=None)], 10)
    assert out[0]["death_ch"] is None
    assert out[0]["revive_ch"] == 4                                   # revive_ch 仍算


def test_clue_truncated_and_missing_why_empty():
    out = prose_facts.revival_candidates([_f(why="x" * 50)], 10)
    assert out[0]["clue"] == "x" * 30                                 # why[:30]
    f2 = _f()
    del f2["why"]
    assert prose_facts.revival_candidates([f2], 10)[0]["clue"] == ""  # 缺 why → ""


def test_ch_b_at_bounds_included():
    assert prose_facts.revival_candidates([_f(ch_b=1)], 10)[0]["revive_ch"] == 0    # 下界
    assert prose_facts.revival_candidates([_f(ch_b=10)], 10)[0]["revive_ch"] == 9   # 上界
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_revival_candidates.py -q`
Expected: FAIL — `AttributeError: module 'hiki.prose_facts' has no attribute 'revival_candidates'`。

- [ ] **Step 3: 加 `revival_candidates`(`prose_facts.py`,`signal_counts_from_fact_table` 之后)**

在 `signal_counts_from_fact_table`(结束于 `:195` 一带)之后、`_ctx`(`:198`)之前插入:
```python
def revival_candidates(findings: list[dict], n_ch: int) -> list[dict]:
    """从 fact_table findings 取生死类 → 复活候选(who/clue/revive_ch 0-based/death_ch 0-based|None)。
    单源: produce._fact_audit_repair 与 point_repair._verified_revivals 共用(曾逐字重复)。"""
    return [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
             "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
            for f in findings if f.get("cat") == "生死"
            and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= n_ch]
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_revival_candidates.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 改 `produce.py` 调用点(`:1068-1071`)**

把:
```python
        cand = [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
                 "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
                for f in ft["findings"] if f.get("cat") == "生死"
                and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(ch_texts)]
```
改为:
```python
        cand = prose_facts.revival_candidates(ft["findings"], len(ch_texts))
```

- [ ] **Step 6: 改 `point_repair.py` 调用点(`:62-65`)**

把:
```python
    cand = [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
             "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
            for f in ft["findings"] if f.get("cat") == "生死"
            and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(chs)]
```
改为:
```python
    cand = prose_facts.revival_candidates(ft["findings"], len(chs))
```
(`point_repair` 已 import `prose_facts`,见 `:61` `prose_facts.fact_table_audit`;无新 import。)

- [ ] **Step 7: 金标/装配网 + 全量(字节等价验证)**

Run: `python -m pytest tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全绿(`cand` 字节等价 → `ft_deaths_verified`/`事实表生死_verify后` 信号不变)。
Run: `python -m pytest -m 'not api' -q`
Expected: 全绿,报确切 passed/deselected 数。

- [ ] **Step 8: 刷新 `docs/design/tech-debt.md` C7 行**

C7 行备注追加:
```
C7余切 已收: 生死→复活候选推导单源化(prose_facts.revival_candidates), produce._fact_audit_repair 与 point_repair._verified_revivals 共用(曾逐字重复)。纯重构字节等价; 刻意只抽推导不折叠 fact_table_audit(避 produce 二次审计)。
```

- [ ] **Step 9: 提交**

```bash
git add src/hiki/prose_facts.py src/hiki/produce.py src/hiki/point_repair.py tests/test_revival_candidates.py docs/design/tech-debt.md
git commit -m "refactor(C7): 复活候选提取单源化 prose_facts.revival_candidates(两站点共用, 字节等价)"
```

---

## Self-Review

- **Spec 覆盖**:① `revival_candidates` 纯函数 → Step 3;② 两站点改调用 → Step 5/6;③ 范围 nuance(只抽推导)→ Step 5/6 仅换 cand 行, 不动 `ft`/`fact_table_audit`/下游;验证(纯函数 6 测 + 金标/装配网)→ Step 1/7;tech-debt → Step 8。✅
- **占位**:无 TBD;每代码步给完整前后码;测试完整。
- **类型一致**:`revival_candidates(findings: list[dict], n_ch: int) -> list[dict]` 跨 spec/plan/测一致;两调用点传 `ft["findings"]` + `len(...)` 与签名一致;字段名 `who/clue/revive_ch/death_ch` 与原 inline 逐字同。
- **字节等价**:Step 3 函数体与两站点原推导逐字同(仅 `len(ch_texts)`/`len(chs)` → 形参 `n_ch`);过滤短路顺序(`isinstance(ch_b,int)` 先于 `1<=ch_b<=n_ch`)保留 → 非 int ch_b 不崩。
- **风险**:① 站点漏改/残留 inline → Step 7 全量 + 金标网兜;② 宿主 import 环 → `prose_facts` 已被两站点 import(实证),无新 import;③ 边界语义(`1<=ch_b<=n_ch`)→ Step 1 `test_ch_b_at_bounds_included` + `test_ch_b_out_of_bounds_or_non_int_excluded` 双向钉。
