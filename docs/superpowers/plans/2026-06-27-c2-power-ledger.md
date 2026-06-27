# C2 修为 PowerLedger 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把修为单调的 2 套引擎(audit 序数 / prose 数值)收口为一个可插拔比较器的纯 `PowerLedger`,两引擎 + 修复变薄 adapter——**行为逐位保持、零产品变化**。

**Architecture:** `PowerLedger`(住 `src/hiki/char_ledger.py`,与 RevivalLedger 并存)= per-key running-best + 回退检测;比较器是三元 callables(`key`/`parse`/`is_regression`),由工厂 `ordinal_comparator`/`numeric_comparator` 构造,**域逻辑(`_power_rank`/`num_of`)留在 adapter 注入**,故 char_ledger 不依赖 audit/prose。迁移顺序:先建 ledger → 先补无网的 fix characterization → 逐引擎迁移(网守等价)。

**Tech Stack:** Python ≥3.10,标准库(dataclasses/typing),pytest。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-27-c2-power-ledger-design.md`(读它拿现状 2 引擎 + 比较器三元 + record→bool 修复交错)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** char_ledger.py **不得 import audit/prose_facts**(域逻辑由 adapter 注入,避免循环)。
- **行为逐位保持**:`produce.py` 门/LLM 步/`_fact_audit_repair` 流程零变更;两引擎输出(issue 串 / fix 串 + scene 改写 / `cat="数值"conf="中"` finding)逐位等价。
- **两引擎均非硬门**:维5 advisory;cross_check power `conf="中"` 不入 `spine_net_num`。故无金标信号牵连——等价由 characterization + cross_check_corpus 守,**不是**金标网。
- **fix_power_monotonic 迁移前必须先有 characterization**(Task 2)绿,尤其其 **scene-mutation**(就地改写 `sc["power_after"]`)。
- `pytest -m 'not api'` 离线全绿。编码 UTF-8。
- name/parse 语义不改:`_power_rank` 返回 `-1`(判不出)→ 比较器 parse 映射为 `None`(record 跳过),复现现状 `if r<0: continue`。

---

## Task 1: PowerLedger 核心 + 两比较器工厂

纯,零 LLM/IO/audit/prose 依赖。

**Files:**
- Modify: `src/hiki/char_ledger.py`(在文件末尾追加;不动 RevivalLedger 部分)
- Test: `tests/test_power_ledger.py`

**Interfaces:**
- Produces:
  - `PowerRegression(who: str, ch: int, raw_value: str, best_raw: str, mode: str)` dataclass(frozen）
  - `Comparator(key, parse, is_regression, mode)` dataclass(frozen，持 3 callables + mode 串)
  - `ordinal_comparator(rank_fn) -> Comparator`;`numeric_comparator(value_fn, unit_fn) -> Comparator`
  - `PowerLedger(comparator)`：`record(who, raw_value, ch) -> bool`（True=此值回退）；`regressions() -> list[PowerRegression]`；`current_best(who, raw_value="") -> str | None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_power_ledger.py
"""PowerLedger + 比较器纯函数 characterization(C2)。零 API/audit/prose 依赖。"""
from hiki.char_ledger import PowerLedger, ordinal_comparator, numeric_comparator


# 序数: 简单 rank_fn 注入(模拟 _power_rank, -1→None)
_RANK = {"练气": 1, "筑基": 2, "金丹": 3, "元婴": 4}
def _rank_fn(raw):
    r = _RANK.get(raw, -1)
    return float(r) if r >= 0 else None


def test_ordinal_no_regression_on_ascend():
    lg = PowerLedger(ordinal_comparator(_rank_fn))
    assert lg.record("叶凡", "练气", 1) is False
    assert lg.record("叶凡", "金丹", 2) is False     # 升


def test_ordinal_regression_on_descend():
    lg = PowerLedger(ordinal_comparator(_rank_fn))
    lg.record("叶凡", "金丹", 1)
    assert lg.record("叶凡", "筑基", 2) is True       # 金丹(3)→筑基(2) 退
    regs = lg.regressions()
    assert len(regs) == 1 and regs[0].who == "叶凡" and regs[0].raw_value == "筑基"
    assert regs[0].best_raw == "金丹" and regs[0].mode == "ordinal"


def test_ordinal_unparseable_skipped():
    lg = PowerLedger(ordinal_comparator(_rank_fn))
    lg.record("叶凡", "金丹", 1)
    assert lg.record("叶凡", "无法识别的境界", 2) is False   # parse None → 跳过, 不报不更新
    assert lg.current_best("叶凡") == "金丹"


def test_ordinal_current_best_tracks_max():
    lg = PowerLedger(ordinal_comparator(_rank_fn))
    lg.record("叶凡", "练气", 1)
    lg.record("叶凡", "元婴", 2)
    lg.record("叶凡", "筑基", 3)                       # 退, best 不变
    assert lg.current_best("叶凡") == "元婴"


# 数值: value_fn + unit_fn 注入
def _value_fn(raw):
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(m.group(1)) if m else None
def _unit_fn(raw):
    import re
    return re.sub(r"(\d+(?:\.\d+)?)", "#", raw).strip()


def test_numeric_5pct_threshold_boundary():
    lg = PowerLedger(numeric_comparator(_value_fn, _unit_fn))
    lg.record("叶凡", "气血100卡", 1)
    assert lg.record("叶凡", "气血95卡", 2) is False    # 100→95 恰 95%, 不算退(<95*0.95? 95<95.0 False)
    assert lg.record("叶凡", "气血94卡", 3) is True     # 94 < 100*0.95=95.0 → 退


def test_numeric_keyed_by_unit():
    lg = PowerLedger(numeric_comparator(_value_fn, _unit_fn))
    lg.record("叶凡", "气血100卡", 1)
    assert lg.record("叶凡", "灵力10级", 2) is False    # 不同 unit, 独立桶, 不比
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_power_ledger.py -q`
Expected: FAIL — `ImportError: cannot import name 'PowerLedger' from 'hiki.char_ledger'`

- [ ] **Step 3: 在 `src/hiki/char_ledger.py` 末尾追加**

```python
# ==================== C2: 修为/战力单调账本 ====================
from typing import Callable, Hashable, Optional


@dataclass(frozen=True)
class PowerRegression:
    who: str
    ch: int
    raw_value: str        # 触发回退的原始值串
    best_raw: str         # 当时 running-best 的原始串(供修复钉回)
    mode: str             # "ordinal" | "numeric"


@dataclass(frozen=True)
class Comparator:
    """可插拔比较器: 三元 callables。key 分桶, parse→可比量(None=跳过), is_regression(new,best)。
    域逻辑(_power_rank/num_of)由 adapter 注入, 故本模块不依赖 audit/prose。"""
    key: Callable[[str, str], Hashable]
    parse: Callable[[str], Optional[float]]
    is_regression: Callable[[float, float], bool]
    mode: str


def ordinal_comparator(rank_fn: Callable[[str], Optional[float]]) -> Comparator:
    """序数: key=who; parse=rank_fn(已把判不出映射为 None); 退=new<best(严格)。"""
    return Comparator(key=lambda who, raw: who, parse=rank_fn,
                      is_regression=lambda new, best: new < best, mode="ordinal")


def numeric_comparator(value_fn: Callable[[str], Optional[float]],
                       unit_fn: Callable[[str], str]) -> Comparator:
    """数值: key=(who, unit_fn(raw)); parse=value_fn; 退=new<best*0.95(>5%跌)。"""
    return Comparator(key=lambda who, raw: (who, unit_fn(raw)), parse=value_fn,
                      is_regression=lambda new, best: new < best * 0.95, mode="numeric")


class PowerLedger:
    """修为单调账本(C2)。纯, 零 LLM/IO。per-key 追 running-best, 新值低于阈值即标回退。
    两修为引擎(audit.check/fix_power_monotonic + prose_facts.cross_check power)共享此骨架,
    差异全在注入的 comparator。"""

    def __init__(self, comparator: Comparator) -> None:
        self._cmp = comparator
        self._best: dict = {}          # key -> (value: float, raw: str)
        self._regressions: list[PowerRegression] = []

    def record(self, who: str, raw_value: str, ch: int) -> bool:
        raw = str(raw_value)
        k = self._cmp.key(who, raw)
        v = self._cmp.parse(raw)
        if v is None:
            return False
        best = self._best.get(k)
        regressed = best is not None and self._cmp.is_regression(v, best[0])
        if regressed:
            self._regressions.append(PowerRegression(who, ch, raw, best[1], self._cmp.mode))
        if best is None or v > best[0]:
            self._best[k] = (v, raw)
        return regressed

    def regressions(self) -> list[PowerRegression]:
        return list(self._regressions)

    def current_best(self, who: str, raw_value: str = "") -> str | None:
        best = self._best.get(self._cmp.key(who, str(raw_value)))
        return best[1] if best else None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_power_ledger.py -q`
Expected: PASS（7 passed）

- [ ] **Step 5: 全量 + 提交**

```bash
python -m pytest -q   # 全绿(只新增模块代码+测试)
git add src/hiki/char_ledger.py tests/test_power_ledger.py
git commit -m "feat(C2): PowerLedger + 可插拔比较器(序数/数值)— 纯骨架, 域逻辑 adapter 注入"
```

---

## Task 2: 修为引擎迁移前 characterization(尤其 fix 的 scene-mutation)

确认/补三处迁移目标的迁移前行为网。`check_power_monotonic` / `cross_check` power 可能已有部分覆盖;**`fix_power_monotonic` 的 scene-mutation 大概率无专测,先补**。本任务**不改生产码**。

**Files:**
- Create/Modify: `tests/test_power_characterization.py`(新)或并入 `tests/test_audit.py`
- Read first: `src/hiki/audit.py:245-301`(power_order_from_bible/fix/check)、`src/hiki/prose_facts.py:112-133`(cross_check power)、`tests/test_audit.py` + `tests/test_prose_facts.py`(看已有 power 覆盖)

**Interfaces:**
- Consumes: `audit.check_power_monotonic(bible, scenes)`、`audit.fix_power_monotonic(bible, scenes)`、`prose_facts.cross_check(facts)`(现签名)

- [ ] **Step 1: 盘点现有 power 测试覆盖**

Read `tests/test_audit.py`、`tests/test_prose_facts.py`、`tests/test_cross_check_corpus.py`。记下:`check_power_monotonic`/`fix_power_monotonic`/`cross_check` power 段各已被哪些测试覆盖、覆盖哪些分支。

- [ ] **Step 2: 写缺失的 characterization(钉死现状)**

针对盘点出的缺口补测试。**必含**(读现状确认精确 I/O 后写):
```python
# tests/test_power_characterization.py
"""修为 2 引擎迁移前行为钉死(C2)。零 API。迁移后必须逐位不变。"""
from hiki.audit import check_power_monotonic, fix_power_monotonic


def _bible():
    # escalation_ladder 解析 ≥3 级 → 用本书梯; 否则默认梯。读 power_order_from_bible 确认格式
    return {"escalation_ladder": "练气→筑基→金丹→元婴，赌注升级"}


def test_check_power_monotonic_flags_descend():
    scenes = [{"power_after": [["叶凡", "金丹"]]}, {"power_after": [["叶凡", "筑基"]]}]
    issues = check_power_monotonic(_bible(), scenes)
    assert len(issues) == 1 and "叶凡" in issues[0] and "战力崩坏" in issues[0]


def test_check_power_monotonic_clean_on_ascend():
    scenes = [{"power_after": [["叶凡", "练气"]]}, {"power_after": [["叶凡", "金丹"]]}]
    assert check_power_monotonic(_bible(), scenes) == []


def test_fix_power_monotonic_pins_back_and_mutates_scene():
    # 关键: fix 就地改写 scenes 的 power_after, 钉回当前最高
    scenes = [{"power_after": [["叶凡", "金丹"]]}, {"power_after": [["叶凡", "筑基"]]}]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert len(fixed) == 1 and "叶凡" in fixed[0]
    assert scenes[1]["power_after"] == [["叶凡", "金丹"]]   # 场景被钉回(就地 mutate)


def test_fix_power_monotonic_keeps_ascend_untouched():
    scenes = [{"power_after": [["叶凡", "练气"]]}, {"power_after": [["叶凡", "金丹"]]}]
    fixed = fix_power_monotonic(_bible(), scenes)
    assert fixed == [] and scenes[1]["power_after"] == [["叶凡", "金丹"]]
```
注: Step 1 读完后,若实际 issue/fix 串格式、scene 改写形态(钉回 `[sp[0], cs]` 用原名还是 alias、是否保留非 power_after 字段)与上述不符,**以现状为准调整测试**(钉的是现状)。补足 equal-rank、rank 判不出跳过、alias 映射、cross_check power(已有 `test_cross_check_power_regression_conf_medium` 则确认其覆盖)。

- [ ] **Step 3: 跑测试确认通过(钉现状=直接绿)**

Run: `python -m pytest tests/test_power_characterization.py -q`
Expected: PASS（红=对现状理解错,回 Step 1 修测试而非改生产码）

- [ ] **Step 4: 提交**

```bash
git add tests/test_power_characterization.py
git commit -m "test(C2): 修为 2 引擎迁移前 characterization(尤其 fix scene-mutation)"
```

---

## Task 3: 迁移 check_power_monotonic（序数检测 → PowerLedger）

**Files:**
- Modify: `src/hiki/audit.py`（`check_power_monotonic` ~283-301）
- Read first: `audit.py:283-301` + `_power_rank`/`_alias_map`/`_str_pair`

**Interfaces:**
- Consumes: `char_ledger.PowerLedger`、`char_ledger.ordinal_comparator`
- Produces: `check_power_monotonic(bible, scenes) -> list[str]` 输出**不变**

- [ ] **Step 1: 读现状,记 issue 串格式 + alias/rank 用法**

Read `audit.py:283-301`。确认 issue 串 `"场景{i}: 「{who}」修为回退到{pw}(战力崩坏)"`、`who=alias.get(sp[0], sp[0])`、`_power_rank(pw, order)`、`r<0 continue`。

- [ ] **Step 2: 改 check_power_monotonic 经 ledger**

保持 `order=power_order_from_bible`、`alias=_alias_map`、逐场景逐 `power_after` 的 `_str_pair` 提取。把 max-rank + 回退判定换成:
```python
from .char_ledger import PowerLedger, ordinal_comparator
def _rank_fn(raw):
    r = _power_rank(raw, order)
    return float(r) if r >= 0 else None
lg = PowerLedger(ordinal_comparator(_rank_fn))
issues = []
for i, sc in enumerate(scenes):
    for pair in sc.get("power_after") or []:
        sp = _str_pair(pair)
        if not sp:
            continue
        who, pw = alias.get(sp[0], sp[0]), sp[1]
        if lg.record(who, pw, i):                       # record 用 ch=场景序号 i
            issues.append(f"场景{i}: 「{who}」修为回退到{pw}(战力崩坏)")
return issues
```
**串格式必须与现状逐字相同**(Step 1 的真实串覆盖上面)。注意 record 的 ch 传场景序号 `i`(与现状 issue 里的 `场景{i}` 对齐)。

- [ ] **Step 3: 网守等价**

Run: `python -m pytest tests/test_power_characterization.py tests/test_audit.py -q`
Expected: 全绿(issue 输出逐位不变)。

- [ ] **Step 4: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/audit.py
git commit -m "refactor(C2): check_power_monotonic 经 PowerLedger 序数比较器(issue逐位不变, 网守)"
```

---

## Task 4: 迁移 fix_power_monotonic（序数修复 + scene-mutation → PowerLedger）

**最易漂移**:scene 就地改写 + record→bool 交错钉回。Task 2 的 fix characterization 是验收。

**Files:**
- Modify: `src/hiki/audit.py`（`fix_power_monotonic` ~254-280）

**Interfaces:**
- Consumes: `char_ledger.PowerLedger`、`char_ledger.ordinal_comparator`
- Produces: `fix_power_monotonic(bible, scenes) -> list[str]` 输出**不变** + scenes 就地改写**不变**

- [ ] **Step 1: 读现状,记 fix 串 + 钉回形态**

Read `audit.py:254-280`。确认:回退时 `new.append([sp[0], cs])`(原名 `sp[0]` + 当前最高串 `cs`)、`fixed.append(f"场景{i}:{who} {p}→{cs}")`、非回退 `cur[who]=(r,p)`、`sc["power_after"]=new` 重建。

- [ ] **Step 2: 改 fix_power_monotonic 经 ledger（record→bool 交错）**

```python
from .char_ledger import PowerLedger, ordinal_comparator
def _rank_fn(raw):
    r = _power_rank(raw, order)
    return float(r) if r >= 0 else None
lg = PowerLedger(ordinal_comparator(_rank_fn))
fixed = []
for i, sc in enumerate(scenes):
    new = []
    for pair in sc.get("power_after") or []:
        sp = _str_pair(pair)
        if sp:
            who, p = alias.get(sp[0], sp[0]), sp[1]
            if lg.record(who, p, i):                    # True=回退
                cs = lg.current_best(who)               # 当前最高原始串(record后best不变)
                new.append([sp[0], cs])
                fixed.append(f"场景{i}:{who} {p}→{cs}")
                continue
        new.append(pair)
    sc["power_after"] = new
return fixed
```
**关键等价点**:① 钉回用 `[sp[0], cs]`(原名,非 alias)与现状一致;② `cs` 是 record 后的 `current_best(who)`——record 在回退时不更新 best,故 cs=运行最高 = 现状 `cur` 的 `cs`;③ 非回退/`sp` 为空时 `new.append(pair)` 原样保留;④ `sc["power_after"]=new` 就地改写。Step 1 的真实串/形态覆盖上面占位。

- [ ] **Step 3: 网守(scene-mutation 等价是验收)**

Run: `python -m pytest tests/test_power_characterization.py tests/test_audit.py -q`
Expected: 全绿(fix 串 + scenes 就地改写逐位不变)。**红=钉回/改写漂移, 回 Step 2 对齐。**

- [ ] **Step 4: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/audit.py
git commit -m "refactor(C2): fix_power_monotonic 经 PowerLedger + adapter钉回scene(就地改写逐位不变, 网守)"
```

---

## Task 5: 迁移 cross_check power 段（数值 → PowerLedger）

**Files:**
- Modify: `src/hiki/prose_facts.py`（`cross_check` power 段 ~112-133）
- Read first: `prose_facts.py:112-133`（power 段全部）

**Interfaces:**
- Consumes: `char_ledger.PowerLedger`、`char_ledger.numeric_comparator`、`textnum.num_of`、`textnum.NUM`
- Produces: `cross_check(facts)` 的 power `{cat:"数值",conf:"中"}` finding **逐位不变**

- [ ] **Step 1: 读现状 power 段,记 finding 格式**

Read `prose_facts.py:112-133`。确认:`powers[(who, unit)]`、`unit=_NUM.sub("#", val).strip()`、`value=_num_of(val)`、按 ch 排序、`v<hi*0.95`、finding `{cat:"数值", who, ch_a, ch_b, why:"...倒退", conf:"中"}` 的精确 `why` 串与 ch_a/ch_b 语义。

- [ ] **Step 2: 改 cross_check power 段经 ledger**

把 `powers` dict 收集 + 排序 + 5% 判定换成 `PowerLedger(numeric_comparator(num_of, lambda raw: NUM.sub("#", raw).strip()))`,逐章 record,由 `regressions()` 产出等价 finding。**保持 power 段只动这一块**(数值/身份的 identity/numbers 段、生死段不碰)。`why` 串、ch_a(best 所在章)/ch_b(回退章)、conf="中" 逐位对齐 Step 1。
注:现状 power 段按 `(who,unit)` 收齐再排序后单遍找首个跌点(`break`);ledger record 是按输入顺序流式。**确认输入 `facts` 已按章序**(逐章 list)→ 流式 record 等价于排序后扫描。若顺序不一致需在 adapter 内先排序保持等价。

- [ ] **Step 3: 网守等价**

Run: `python -m pytest tests/test_prose_facts.py tests/test_cross_check_corpus.py tests/test_power_characterization.py -q`
Expected: 全绿(power finding 逐位不变)。**红=漂移, 回 Step 2 对齐(不改测试/语料)。**

- [ ] **Step 4: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/prose_facts.py
git commit -m "refactor(C2): cross_check power段 经 PowerLedger 数值比较器(finding逐位不变, 网守)"
```

---

## Task 6: 文档 + 终验

**Files:**
- Modify: `docs/design/tech-debt.md`（C2 行状态）

- [ ] **Step 1: 刷新 tech-debt C2 行**

`docs/design/tech-debt.md` C2 行状态 `⬜`→`✅`(或 `◐` 若有残留),备注:`PowerLedger(char_ledger.py)+可插拔比较器(序数/数值)收 2 引擎+修复为单源, 域逻辑 adapter 注入, 行为逐位保持(characterization+cross_check_corpus 证等价)。残: principled 改判(阈值/判据)留 follow-up`。

- [ ] **Step 2: 全量 + 等价网终验**

Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。
Run: `python -m pytest tests/test_power_ledger.py tests/test_power_characterization.py tests/test_audit.py tests/test_prose_facts.py tests/test_cross_check_corpus.py -q`
Expected: 全绿(等价证明)。

- [ ] **Step 3: 提交**

```bash
git add docs/design/tech-debt.md
git commit -m "docs(C2): tech-debt C2 刷新 — PowerLedger 收 2 引擎(行为保持)"
```

---

## Self-Review

- **Spec 覆盖**:① PowerLedger+比较器 → Task 1;② 比较器三元/工厂 → Task 1;③ check/fix/cross_check 三 adapter → Task 3/4/5;④ fix scene-mutation 先补网 → Task 2(在 Task 4 之前);⑤ 网守等价 → 每迁移任务的网守 Step。✅
- **顺序依赖**:Task 2(characterization)先于 Task 4(fix 迁移)——计划顺序保证。Task 1 地基先行。
- **循环导入**:char_ledger 不 import audit/prose;域逻辑(`_power_rank`/`num_of`)由 adapter 注入工厂。✅
- **行为保持**:每迁移任务验收=既有/新 characterization + cross_check_corpus 绿 + 全量绿,非新断言。
- **占位**:Task 3/4/5 迁移代码标注"以现状串/形态为准覆盖占位"——behavior-preserving 重构的有意要求(实现者读现状后落定);新代码(Task 1 ledger+比较器、Task 2 测试结构)给完整代码。
- **类型一致**:`PowerLedger`/`Comparator`/`ordinal_comparator`/`numeric_comparator`/`record→bool`/`current_best`/`regressions`/`PowerRegression` 跨任务一致。
- **风险**:最高在 Task 4(fix scene-mutation 就地改写)——以 Task 2 characterization 为即时红灯守门。Task 5 数值流式 vs 现状排序-扫描的顺序等价需确认(Step 2 注)。
