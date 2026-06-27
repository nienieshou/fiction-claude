# C5 name 谓词单源 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 7 处 `2 <= len(name) <= N` 人名/物品长度判定收口为单源 `src/hiki/names.py`,行为逐位保持。

**Architecture:** 新建纯模块 `names.py`(`is_person_name(nm, max_len)` + `is_item_name(nm)`,只做长度);7 站点把 `2<=len<=N` 换成谓词调用,**各自的 isinstance/strip/truthiness 前检与后置条件原样保留**(逐位等价)。各站点显式传现状界(4/5/6/8)= bug 单旋钮,本期不改值。

**Tech Stack:** Python ≥3.10,标准库,pytest。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-27-c5-name-predicates-design.md`(读它拿 7 站点现状 + 行为保持纪律)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** `names.py` 零依赖(只是长度判定)。
- **行为逐位保持**:谓词只做 `2 <= len(nm) <= max_len`;各站点的 `isinstance`/`.strip()`/`who and`/`and ev`/`and any(...)`/`and who not in deaths`/`counts>=3`/`not (...)` 等前检后置**原样保留**。
- **不改界值**(本期):各站点传其现状 `max_len`(deaths/milestones/cross_check=6;roster/cluster=5;variant 锚=4;items 用 `is_item_name`=8)。界统一是 follow-up。
- **反相语义**:`prose_continuity` `_variant_scan` 是 `not (2<=len(c)<=4)` → `not is_person_name(c, 4)`,保持反相。
- `pytest -m 'not api'` 离线全绿。编码 UTF-8。
- 行号是 master 近似值;实现者读实际代码定位每个站点。

---

## Task 1: names.py 谓词 + 测试

**Files:**
- Create: `src/hiki/names.py`
- Test: `tests/test_names.py`

**Interfaces:**
- Produces: `is_person_name(nm: str, max_len: int) -> bool`;`is_item_name(nm: str) -> bool`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_names.py
"""name 长度谓词单源(C5)。零 API。"""
from hiki.names import is_person_name, is_item_name


def test_is_person_name_bounds_max6():
    assert is_person_name("叶凡", 6) is True       # len2 下界
    assert is_person_name("欧阳上官修远", 6) is True  # len6 上界
    assert is_person_name("叶", 6) is False         # len1 < 下界
    assert is_person_name("欧阳上官修远长", 6) is False  # len7 > 上界


def test_is_person_name_bounds_max5_and_max4():
    assert is_person_name("欧阳娜娜", 5) is True    # len4 ≤ 5
    assert is_person_name("欧阳上官修", 5) is True   # len5 上界
    assert is_person_name("欧阳上官修远", 5) is False  # len6 > 5
    assert is_person_name("司马懿", 4) is True       # len3 ≤ 4
    assert is_person_name("欧阳上官修", 4) is False   # len5 > 4


def test_is_item_name_bounds():
    assert is_item_name("玉佩") is True             # len2 下界
    assert is_item_name("天雷血玉珠混元伞") is True   # len8 上界
    assert is_item_name("刀") is False              # len1 < 下界
    assert is_item_name("天雷血玉珠混元伞甲") is False  # len9 > 上界
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_names.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiki.names'`

- [ ] **Step 3: 实现 `src/hiki/names.py`**

```python
"""人名/物品名长度谓词单源(C5)。纯, 零依赖。

收口散落 7 处的 `2 <= len(name) <= N` 判定。谓词只做长度;调用方保留各自的
isinstance/strip/truthiness 前检与后置条件(确保行为逐位等价)。
各站点显式传 max_len(现状 4/5/6 人名 / 8 物品)——界统一(修 provenance 缺口)留 follow-up。
"""
from __future__ import annotations


def is_person_name(nm: str, max_len: int) -> bool:
    """人名长度谓词。nm 须为已 str 化字符串。下界 2(最短中文名),上界 max_len。"""
    return 2 <= len(nm) <= max_len


def is_item_name(nm: str) -> bool:
    """物品/法器名谓词(可较长的复合名, 如 '天雷血玉珠')。界 2-8。"""
    return 2 <= len(nm) <= 8
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_names.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q   # 全绿(只新增模块+测试)
git add src/hiki/names.py tests/test_names.py
git commit -m "feat(C5): names.py 人名/物品长度谓词单源(is_person_name/is_item_name)"
```

---

## Task 2: 迁移 produce.py(3 站点)+ prose_facts.py(1 站点)

简单 `X and 2<=len<=N` 模式的 4 站点。行为逐位保持,既有测试 + 全量绿是验收。

**Files:**
- Modify: `src/hiki/produce.py`(_settle_facts deaths/milestones/items,~322/330/335)
- Modify: `src/hiki/prose_facts.py`(cross_check deaths,~102)
- Read first: 各站点实际行(行号 master 近似)

**Interfaces:**
- Consumes: `names.is_person_name`、`names.is_item_name`

- [ ] **Step 1: 读 4 站点实际代码,确认前检/后置**

Read `produce.py` `_settle_facts`(grep `2 <= len(who) <= 6` 与 `2 <= len(name) <= 8`)+ `prose_facts.py` cross_check 死亡段(grep `2 <= len(who) <= 6`)。确认每行的完整条件(`who and`、`and ev`、`and any(...)`、`and who not in deaths`)。

- [ ] **Step 2: 改 produce.py 3 站点**

加 `from .names import is_person_name, is_item_name`(置于现有 import 区)。改:
- deaths: `if who and 2 <= len(who) <= 6:` → `if who and is_person_name(who, 6):`
- items: `if name and 2 <= len(name) <= 8 and any(k in state for k in _ITEM_TERMINAL):` → `if name and is_item_name(name) and any(k in state for k in _ITEM_TERMINAL):`
- milestones: `if who and 2 <= len(who) <= 6 and ev:` → `if who and is_person_name(who, 6) and ev:`
**只换长度子句,其余条件原样。** 用 Step 1 读到的真实行覆盖上面(若措辞略异以实际为准)。

- [ ] **Step 3: 改 prose_facts.py 1 站点**

加 `from .names import is_person_name`。改 cross_check 死亡段:`if who and 2 <= len(who) <= 6 and who not in deaths:` → `if who and is_person_name(who, 6) and who not in deaths:`(master 版含 `and who not in deaths`;以实际为准)。

- [ ] **Step 4: 网守等价**

Run: `python -m pytest tests/test_produce_units.py tests/test_prose_facts.py tests/test_mining.py tests/test_stages.py -q`
Expected: 全绿(行为逐位不变)。

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/produce.py src/hiki/prose_facts.py
git commit -m "refactor(C5): produce/_settle_facts 3站点 + prose_facts cross_check 经 name 谓词(逐位等价)"
```

---

## Task 3: 迁移 prose_continuity.py(3 站点,含反相锚 + characterization)

含 `_variant_scan` 的反相语义 + roster/cluster。`_variant_scan` 若无直接测试则先补 characterization。

**Files:**
- Modify: `src/hiki/prose_continuity.py`(extract_roster ~40、_variant_scan ~121、cluster_names ~146)
- Create/Modify: `tests/test_prose_continuity_names.py`(若 _variant_scan 无覆盖)
- Read first: 3 站点 + `tests/` 中 prose_continuity 相关覆盖

- [ ] **Step 1: 盘点覆盖 + 读 3 站点**

Read `prose_continuity.py` extract_roster(grep `len(nm.strip()) <= 5`)、_variant_scan(grep `2 <= len(c) <= 4`)、cluster_names(grep `2 <= len(p) <= 5`)。检查 `tests/` 是否覆盖 extract_roster/cluster_names/_variant_scan(grep test 文件)。

- [ ] **Step 2: 若 _variant_scan / 任一站点无网,补 characterization**

读 `_variant_scan` 行为(高频名锚选取),若无测试,写 `tests/test_prose_continuity_names.py` 钉死现状(synthetic 输入→现状输出)。**钉的是现状,迁移后须不变。** 若已有覆盖则跳过此步并在报告说明。

- [ ] **Step 3: 改 3 站点**

加 `from .names import is_person_name`。改:
- extract_roster: `if isinstance(nm, str) and 2 <= len(nm.strip()) <= 5:` → `if isinstance(nm, str) and is_person_name(nm.strip(), 5):`
- _variant_scan(**反相**): `if cc < floor or not (2 <= len(c) <= 4):` → `if cc < floor or not is_person_name(c, 4):`
- cluster_names: `ps = [p for p in counts if counts.get(p, 0) >= 3 and 2 <= len(p) <= 5]` → `ps = [p for p in counts if counts.get(p, 0) >= 3 and is_person_name(p, 5)]`
**isinstance/strip/counts>=3/not 反相 全部原样保留。** 以 Step 1 实际行为准。

- [ ] **Step 4: 网守等价**

Run: `python -m pytest tests/test_prose_continuity_names.py tests/ -k "continuity or roster or cluster or prose" -q`(若新建测试)+ 全量。
Expected: 全绿(行为逐位不变, 反相语义保持)。

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/prose_continuity.py tests/test_prose_continuity_names.py
git commit -m "refactor(C5): prose_continuity roster/variant锚/cluster 经 name 谓词(反相保持, 逐位等价)"
```

---

## Task 4: 文档 + 终验

**Files:**
- Modify: `docs/design/tech-debt.md`（C5 行状态）

- [ ] **Step 1: 刷新 tech-debt C5 行**

`docs/design/tech-debt.md` C5 行(grep `| C5 |`)状态 `⬜`→`◐`,备注:`7 站点 2<=len<=N 收口 src/hiki/names.py(is_person_name/is_item_name),行为逐位保持(各站点传现状界 4/5/6/8)。残(follow-up): 界统一(人名 2-5 vs 2-6 分叉=provenance 缺口, 需校准选 5/6)/ safe_pairs 谓词`。

- [ ] **Step 2: 全量终验 + 谓词调用点核**

Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。
Run: 确认所有 7 站点已迁移(grep 剩余 `2 <= len(` 在 prose_facts/prose_continuity/produce 应只剩非人名/物品的用途,如 audit.py 的残句 `2<=len(s)<=12` 不在本期范围)。

- [ ] **Step 3: 提交**

```bash
git add docs/design/tech-debt.md
git commit -m "docs(C5): tech-debt C5 刷新 — name 谓词收口 names.py(行为保持)"
```

---

## Self-Review

- **Spec 覆盖**:① names.py 谓词 → Task 1;② 7 站点迁移 → Task 2(4 站点)+ Task 3(3 站点);③ 反相锚 → Task 3;④ _variant_scan 无网先补 → Task 3 Step 2;⑤ 验证靠既有测试+全量 → 每任务网守 Step。✅
- **行为保持**:每迁移任务验收=既有测试 + 全量绿(非新断言);谓词只做长度,前检后置留站点。
- **占位**:Task 2/3 标注"以实际行为准覆盖"——behavior-preserving 重构的有意要求(实现者读 master 实际行);新代码(Task 1 names.py + 测试)给完整代码。
- **类型一致**:`is_person_name(nm, max_len)`/`is_item_name(nm)` 跨任务一致;各站点 max_len(4/5/6)与 is_item_name(8)与 spec 表一致。
- **风险**:最易错处 = `_variant_scan` 反相语义(`not is_person_name(c,4)`)与"误把 isinstance/strip 并进谓词"。Task 3 Step 2 的 characterization + 全量绿守门。
