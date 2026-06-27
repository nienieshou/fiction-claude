# C1 死人复活 Ledger 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把死人复活的 6 路径/3 数据模型收口为一个纯确定性 `RevivalLedger`(带 provenance),3 路检测变薄 adapter,门里手写优先级显式化为 source 优先级——**行为逐位保持、零产品变化**。

**Architecture:** 薄 ledger(`src/hiki/char_ledger.py`)只拥有数据模型 + 确定性合并/裁决;LLM 编排(`verify_revivals`/`verify_revival_beats`/`repair_revivals_smart`)、门、`_fact_audit_repair` 流程不动,只把数据载体从分散 dict 换成 `RevivalRecord`。迁移顺序:先建 ledger → 先给无网的 P1/P3 补特征化 → 再逐路迁移(每步网守等价)。

**Tech Stack:** Python ≥3.10,标准库(dataclasses),pytest。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-27-c1-revival-ledger-design.md`(读它拿现状 6 路径/3 模型 + provenance 优先级 facts>plan>roster)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖**(dataclasses/typing 标准库)。
- **行为逐位保持**:默认生产管线(`produce.py` 的门、LLM 步、`_fact_audit_repair` 流程)零行为变更;迁移只换数据载体。
- **网守门(每个迁移任务后必跑)**:`pytest tests/test_gold_regression.py tests/test_assembly_regression.py tests/test_cross_check_corpus.py` 全绿;7 本 `ft_revival_residual`/`生死_verify后` 零变化。
- **P1/P3 迁移前必须先有特征化网**(Task 2)绿,否则禁止动 P1/P3。
- `pytest -m 'not api'` 离线全绿。编码 UTF-8。
- **provenance 优先级**(裁决依据,复现今天):`facts`(权威) > `plan`(回退) > `roster`(仅修复)。confidence 仅携带不驱动本期裁决。
- name 长度界**不在本期统一**(那是 C5):各 adapter 保留其现有 `2<=len(who)<=N` 过滤原值,不改。

---

## Task 1: RevivalLedger 核心(数据模型 + 确定性合并)

纯模块,零 LLM/IO。这是其余任务的地基。

**Files:**
- Create: `src/hiki/char_ledger.py`
- Test: `tests/test_char_ledger.py`

**Interfaces:**
- Produces:
  - `DeathEvent(who: str, ch: int, clue: str, source: str)` dataclass
  - `AppearanceEvent(who: str, ch: int, source: str)` dataclass
  - `RevivalRecord(who: str, death_ch: int, revive_ch: int, clue: str, sources: frozenset[str], confidence: str)` dataclass
  - `RevivalLedger` with: `record_death(who, ch, clue="", source) -> None`; `record_appearance(who, ch, source) -> None`; `revivals() -> list[RevivalRecord]`; `resolve_gating(verified: list[RevivalRecord]) -> list[RevivalRecord]`
  - 常量 `SOURCE_PRECEDENCE = ("facts", "plan", "roster")`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_char_ledger.py
"""RevivalLedger 纯函数 characterization(C1)。零 API。"""
from hiki.char_ledger import RevivalLedger, RevivalRecord


def test_death_then_later_appearance_is_revival():
    lg = RevivalLedger()
    lg.record_death("纪老夫人", 15, clue="火化", source="facts")
    lg.record_appearance("纪老夫人", 47, source="facts")
    revs = lg.revivals()
    assert len(revs) == 1
    r = revs[0]
    assert r.who == "纪老夫人" and r.death_ch == 15 and r.revive_ch == 47
    assert r.clue == "火化" and "facts" in r.sources


def test_appearance_before_death_not_revival():
    lg = RevivalLedger()
    lg.record_appearance("张三", 3, source="facts")
    lg.record_death("张三", 10, clue="", source="facts")
    assert lg.revivals() == []


def test_earliest_death_earliest_later_appearance():
    lg = RevivalLedger()
    lg.record_death("李四", 20, clue="坠崖", source="facts")
    lg.record_appearance("李四", 25, source="facts")
    lg.record_appearance("李四", 30, source="facts")
    r = lg.revivals()[0]
    assert r.death_ch == 20 and r.revive_ch == 25   # 死后最早出场


def test_multi_source_merges_sources():
    lg = RevivalLedger()
    lg.record_death("王五", 10, clue="病故", source="facts")
    lg.record_appearance("王五", 12, source="facts")
    lg.record_death("王五", 10, clue="", source="plan")
    lg.record_appearance("王五", 12, source="plan")
    revs = lg.revivals()
    assert len(revs) == 1
    assert revs[0].sources == frozenset({"facts", "plan"})


def test_resolve_gating_source_precedence():
    # facts 权威进门; 仅 roster 来源不进门(仅修复)
    facts_rev = RevivalRecord("A", 5, 8, "", frozenset({"facts"}), "高")
    roster_only = RevivalRecord("B", 5, 8, "", frozenset({"roster"}), "高")
    plan_only = RevivalRecord("C", 5, 8, "", frozenset({"plan"}), "高")
    lg = RevivalLedger()
    gated = lg.resolve_gating([facts_rev, roster_only, plan_only])
    whos = {r.who for r in gated}
    assert "A" in whos          # facts 权威
    assert "B" not in whos      # 仅 roster = 仅修复, 不进门
    assert "C" in whos          # plan 回退也算门级来源
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_char_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiki.char_ledger'`

- [ ] **Step 3: 实现 `src/hiki/char_ledger.py`**

```python
"""角色状态账本(C1 起步: 仅死人复活)。纯确定性, 零 LLM/IO。

把死人复活在 6 路径/3 数据模型(plan维度/事实表findings/roster)上的重复检测
收口为单一来源: 各路把 死亡/出场事件 写入 ledger(带 source provenance),
ledger 确定性地配对成 RevivalRecord。门裁决按 source 优先级显式化(复现今天)。

后续 C2 修为 / C3 身份 / C5 name 谓词 往本模块加 sibling concern。
"""
from __future__ import annotations
from dataclasses import dataclass, field

# 门级来源优先级: facts(事实表权威) > plan(回退) > roster(仅叙事修复, 不进门)
SOURCE_PRECEDENCE = ("facts", "plan", "roster")
_GATING_SOURCES = frozenset({"facts", "plan"})   # roster 仅修复


@dataclass(frozen=True)
class DeathEvent:
    who: str
    ch: int
    clue: str
    source: str


@dataclass(frozen=True)
class AppearanceEvent:
    who: str
    ch: int
    source: str


@dataclass(frozen=True)
class RevivalRecord:
    who: str
    death_ch: int
    revive_ch: int
    clue: str
    sources: frozenset
    confidence: str = "高"   # 复活 findings 现状一律 高; 仅携带, 不驱动本期裁决


class RevivalLedger:
    """死亡/出场事件账本。record_* 写入, revivals() 确定性配对。"""

    def __init__(self) -> None:
        self._deaths: list[DeathEvent] = []
        self._apps: list[AppearanceEvent] = []

    def record_death(self, who: str, ch: int, clue: str = "", source: str = "facts") -> None:
        if who and isinstance(ch, int):
            self._deaths.append(DeathEvent(who.strip(), ch, clue or "", source))

    def record_appearance(self, who: str, ch: int, source: str = "facts") -> None:
        if who and isinstance(ch, int):
            self._apps.append(AppearanceEvent(who.strip(), ch, source))

    def revivals(self) -> list[RevivalRecord]:
        """同 who: 取最早 death_ch, 其后最早 appearance → 一条 RevivalRecord。
        多源命中并 sources。确定性(按 who 排序输出)。"""
        deaths_by_who: dict[str, list[DeathEvent]] = {}
        for d in self._deaths:
            deaths_by_who.setdefault(d.who, []).append(d)
        apps_by_who: dict[str, list[AppearanceEvent]] = {}
        for a in self._apps:
            apps_by_who.setdefault(a.who, []).append(a)

        out: list[RevivalRecord] = []
        for who in sorted(deaths_by_who):
            ds = sorted(deaths_by_who[who], key=lambda d: d.ch)
            death_ch = ds[0].ch
            clue = next((d.clue for d in ds if d.clue), "")
            later = sorted(a.ch for a in apps_by_who.get(who, []) if a.ch > death_ch)
            if not later:
                continue
            revive_ch = later[0]
            srcs = frozenset({d.source for d in ds}
                             | {a.source for a in apps_by_who.get(who, []) if a.ch > death_ch})
            out.append(RevivalRecord(who, death_ch, revive_ch, clue, srcs, "高"))
        return out

    def resolve_gating(self, verified: list[RevivalRecord]) -> list[RevivalRecord]:
        """按 source 优先级输出"进门"集合: 任一 gating 源(facts/plan)命中即进门;
        仅 roster 来源 = 仅叙事修复, 不进门。复现今天 P2 权威/P1 回退/P3 仅修复。"""
        return [r for r in verified if r.sources & _GATING_SOURCES]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_char_ledger.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 全量回归**

Run: `python -m pytest -q`
Expected: 全绿（新增 5 测，其余不变）。

- [ ] **Step 6: 提交**

```bash
git add src/hiki/char_ledger.py tests/test_char_ledger.py
git commit -m "feat(C1): RevivalLedger 纯确定性账本 — 数据模型+跨源合并+source优先级裁决"
```

---

## Task 2: P1/P3 迁移前的特征化安全网（无网路径先补网）

P2 有金标+装配网(E2.1);**P1 `check_revival`、P3 `find_revivals` 当前无网**。迁移前先钉死它们的输出,迁后必须逐位相同。本任务**不改任何生产代码**,只加测试。

**Files:**
- Create: `tests/test_revival_paths_characterization.py`
- Read first: `src/hiki/audit.py`(`check_revival` ~331-352)、`src/hiki/prose_continuity.py`(`find_revivals` ~185-202, `extract_roster`)

**Interfaces:**
- Consumes: `audit.check_revival(scenes)`、`prose_continuity.find_revivals(roster, ch_texts)`(现有签名,先读确认)

- [ ] **Step 1: 读现状两函数,确认精确签名与输出结构**

Run: 用 Read 打开 `src/hiki/audit.py:331-352` 与 `src/hiki/prose_continuity.py:185-218`。确认 `check_revival(scenes)->list[str]`、`find_revivals(roster, ch_texts)->list[dict]` 的精确输入键与输出字段。

- [ ] **Step 2: 写特征化测试(钉死当前行为)**

```python
# tests/test_revival_paths_characterization.py
"""P1 check_revival / P3 find_revivals 迁移前行为钉死(C1)。零 API。
迁移到 RevivalLedger 后这些断言必须逐位不变 = 等价证明。"""
from hiki.audit import check_revival
from hiki.prose_continuity import find_revivals


def test_check_revival_detects_post_death_appearance():
    # 场景0 死亡, 场景2 再出场 → 1 条复活 issue
    scenes = [
        {"deaths": ["纪老夫人"]},
        {},
        {"first_appearances": ["纪老夫人"]},
    ]
    issues = check_revival(scenes)
    assert len(issues) == 1 and "纪老夫人" in issues[0] and "死人复活" in issues[0]


def test_check_revival_clean_when_no_reappearance():
    scenes = [{"deaths": ["张三"]}, {"first_appearances": ["李四"]}]
    assert check_revival(scenes) == []


def test_find_revivals_roster_count_threshold():
    # 死亡后章节内该名出现 >=2 次 → 候选复活
    roster = {"win": 1, "deaths": [{"who": "王五", "clue": "坠崖", "ch": 1, "win": 0}], "persons": set(), "n_win": 3}
    ch_texts = ["王五坠崖。", "无关。", "王五回来了, 王五还活着。"]
    revs = find_revivals(roster, ch_texts)
    assert any(r["who"] == "王五" for r in revs)
```

注: Step 1 读完后,若实际字段/阈值与上述 synthetic 不符,**以现状为准调整测试输入使其反映真实行为**(目标是钉死*现状*,不是钉死本计划的假设)。补足覆盖到每个分支(死亡登记、再现判定、阈值边界)。

- [ ] **Step 3: 跑测试确认通过(钉的是现状,应直接绿)**

Run: `python -m pytest tests/test_revival_paths_characterization.py -q`
Expected: PASS（钉死现状 = 直接通过;若红说明对现状理解错,回 Step 1 修正测试而非改生产码）

- [ ] **Step 4: 提交**

```bash
git add tests/test_revival_paths_characterization.py
git commit -m "test(C1): P1/P3 死人复活路径迁移前特征化网(无网路径先补网)"
```

---

## Task 3: 迁移 P2（cross_check 生死段 → ledger）

把 `cross_check` 的 生死 检测段改成经 `RevivalLedger`,产出**等价** `生死` findings。金标+装配网(E2.1)是此任务的等价证明。

**Files:**
- Modify: `src/hiki/prose_facts.py`（`cross_check` 生死段 ~95-111）
- Read first: `src/hiki/prose_facts.py:95-171`（cross_check 全函数）

**Interfaces:**
- Consumes: `char_ledger.RevivalLedger`（Task 1）
- Produces: `cross_check(facts)` 返回的 `生死` findings 结构**不变**：`{"cat":"生死","who","ch_a"(death),"ch_b"(revive),"why","conf":"高"}`

- [ ] **Step 1: 读 cross_check 生死段,记下精确产出**

Read `src/hiki/prose_facts.py:95-111`。确认 生死 findings 的 `why` 串格式、`ch_a`/`ch_b` 语义、`2<=len(who)<=6` 过滤。

- [ ] **Step 2: 改 cross_check 生死段经 ledger（保持 findings 逐位等价）**

把现有的 `deaths` dict 收集 + "death 后最早 present" 循环,替换为:
```python
from .char_ledger import RevivalLedger
# ... 在 cross_check 内, 生死段:
_lg = RevivalLedger()
for i, f in enumerate(facts, 1):
    for d in f.get("deaths") or []:
        who = (d.get("who") if isinstance(d, dict) else str(d) or "").strip()
        if who and 2 <= len(who) <= 6:                      # name 界保持原值(C5 才统一)
            clue = (d.get("clue") or "") if isinstance(d, dict) else ""
            _lg.record_death(who, i, clue, source="facts")
    for p in f.get("present") or []:
        who = str(p).strip()
        if who:
            _lg.record_appearance(who, i, source="facts")
for r in _lg.revivals():
    findings.append({"cat": "生死", "who": r.who, "ch_a": r.death_ch, "ch_b": r.revive_ch,
                     "why": f"{r.who}第{r.death_ch}章death({r.clue})后第{r.revive_ch}章再现",
                     "conf": "高"})
```
**关键**:`why` 串必须与现状逐字相同——Step 1 读到的真实格式覆盖上面的占位格式。`ch_a`=death_ch、`ch_b`=revive_ch 对齐现状。

- [ ] **Step 3: 网守等价(本任务的验收)**

Run: `python -m pytest tests/test_prose_facts.py tests/test_cross_check_corpus.py tests/test_assembly_regression.py tests/test_gold_regression.py -q`
Expected: 全绿。**任一红 = 产出漂移,回 Step 2 对齐。** 7 本 `ft_revival_residual` 零变化。

- [ ] **Step 4: 全量 + 提交**

```bash
python -m pytest -q   # 全绿
git add src/hiki/prose_facts.py
git commit -m "refactor(C1): cross_check 生死段经 RevivalLedger — facts 源, findings 逐位等价(网守)"
```

---

## Task 4: 迁移 P1（check_revival → ledger 适配）

`audit.check_revival` 改成经 `RevivalLedger`(plan 源),输出 `维14死人复活` list 逐位不变。Task 2 的特征化网是验收。

**Files:**
- Modify: `src/hiki/audit.py`（`check_revival` ~331-352）

**Interfaces:**
- Consumes: `char_ledger.RevivalLedger`（plan 源）
- Produces: `check_revival(scenes) -> list[str]` 输出**不变**

- [ ] **Step 1: 改 check_revival 经 ledger**

保持现状的 scene 字段提取(`deaths`/`first_appearances`/`power_after`/`entourage`/`relationships_formed`),把"已死再现"判定改成 ledger:用 `record_death(who, scene_idx, source="plan")` + `record_appearance(who, scene_idx, source="plan")`,再由 `revivals()` 产出。issue 串格式与现状逐字相同(Step 前先读现状串)。
**注意**:check_revival 现状用"场景序号"非"章号",且 present 的来源是多字段并集——adapter 内保持这些提取逻辑,只把判定/配对交给 ledger。

- [ ] **Step 2: 特征化网守 + 全量**

Run: `python -m pytest tests/test_revival_paths_characterization.py tests/test_gold_regression.py -q`
Expected: 全绿(check_revival 输出逐位不变)。然后 `python -m pytest -q` 全绿。

- [ ] **Step 3: 提交**

```bash
git add src/hiki/audit.py
git commit -m "refactor(C1): check_revival(P1) 经 RevivalLedger plan源 — 维14输出逐位不变(网守)"
```

---

## Task 5: 迁移 P3（find_revivals → ledger）+ verify/repair 消费 RevivalRecord

`find_revivals` 改写 roster 源经 ledger;`verify_revivals`/`verify_revival_beats`/`repair_revivals_smart` 改成消费 `RevivalRecord`(或 record→dict 兼容投影,避免下游 `.get()` 取空)。

**Files:**
- Modify: `src/hiki/prose_continuity.py`（`find_revivals` ~185-202;verify_* 消费处)
- Read first: `prose_continuity.py:185-243` + 所有 `find_revivals`/候选 dict 的下游消费点

**Interfaces:**
- Consumes: `char_ledger.RevivalLedger`、`RevivalRecord`
- Produces: `find_revivals` 候选与现状字段兼容(`who`/`clue`/`revive_ch`/`death_win` 等下游依赖键保留)

- [ ] **Step 1: 改 find_revivals 经 ledger(roster 源)**

用 `record_death(who, ch, clue, source="roster")` + 基于 `ch_texts[j].count(who)>=2` 的 `record_appearance(who, j+1, source="roster")`,经 `revivals()` 产候选。**保留下游依赖的字段**:若下游读 `r["death_win"]`/`r["revive_ch"]`,在 record→dict 投影里补齐(读现状下游确认字段集)。

- [ ] **Step 2: verify/repair 消费 RevivalRecord(或兼容投影)**

`verify_revivals`/`verify_revival_beats`/`repair_revivals_smart` 不改 LLM 逻辑,只把入参 dict 换成 record(或在边界做 record↔dict 投影)。确保 `_fact_audit_repair`(produce.py)流程产出的 `生死_verify后` / `gate_rev` **逐位不变**。

- [ ] **Step 3: 网守(最关键——这条直接动 ft_revival_residual 链路)**

Run: `python -m pytest tests/test_revival_paths_characterization.py tests/test_assembly_regression.py tests/test_gold_regression.py -q`
Expected: 全绿。7 本 `ft_revival_residual`/`生死_verify后` 零变化。然后 `python -m pytest -q`。
**任一红 = 链路漂移, 回 Step 1/2 对齐(不要改网/夹具)。**

- [ ] **Step 4: 提交**

```bash
git add src/hiki/prose_continuity.py
git commit -m "refactor(C1): find_revivals(P3) 经 RevivalLedger roster源 + verify/repair 消费 RevivalRecord(网守)"
```

---

## Task 6: 裁决收口 + 文档 + 终验

显式化"门里手写优先级"到 `resolve_gating`(若 Task 3-5 后仍有散落的源优先级逻辑),并收尾文档。

**Files:**
- Modify: `src/hiki/produce.py`（仅当存在散落的手写源优先级可收口到 `ledger.resolve_gating`;**若收口会改行为则不做**,记入 follow-up)
- Modify: `docs/design/tech-debt.md`（C1 行状态）
- Create: `assets/gold_regression/README.md` 无需改;`docs/superpowers/specs/` 已有

- [ ] **Step 1: 审视 produce.py `_fact_audit_repair` 的源优先级**

Read `produce.py:1091-1115`。判断手写的 facts权威/plan回退/roster仅修复逻辑能否无行为变化地换成 `ledger.resolve_gating`。**能等价则换;不能等价(会改判)则保持现状并在 tech-debt 记为 follow-up**(principled 改判本就非本期目标)。

- [ ] **Step 2: 刷新 tech-debt C1 行**

`docs/design/tech-debt.md` C1 行状态 `⬜`→`◐`(或 `✅` 若 3 模型已全收),备注:`RevivalLedger(char_ledger.py)收 P1/P2/P3 为单源, source优先级显式化(行为保持); 残: 散落手写优先级收口(若改判)/C2/C3/C5 各自 follow-up`。

- [ ] **Step 3: 全量 + 全网终验**

Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。
Run: `python -m pytest tests/test_gold_regression.py tests/test_assembly_regression.py tests/test_char_ledger.py tests/test_revival_paths_characterization.py -q`
Expected: 全绿(网证等价)。

- [ ] **Step 4: 提交**

```bash
git add src/hiki/produce.py docs/design/tech-debt.md
git commit -m "refactor(C1): 源优先级收口 resolve_gating(可等价处) + tech-debt C1 刷新"
```

---

## Self-Review

- **Spec 覆盖**:① RevivalLedger 数据模型+合并 → Task 1;② 裁决 source 优先级 → Task 1 `resolve_gating` + Task 6;③ 3 路 adapter → Task 3(P2)/4(P1)/5(P3);④ P1/P3 先补网 → Task 2(在 P1/P3 迁移 Task 4/5 之前);⑤ 网守等价 → 每个迁移任务的网守 Step。✅
- **顺序依赖**:Task 2(特征化)必须在 Task 4/5 之前——计划顺序已保证。Task 1 是地基,先行。
- **行为保持**:每个迁移任务的验收 = 既有网(金标/装配/特征化)绿 + 全量绿,而非新断言。✅
- **占位扫描**:Task 3/4/5 的迁移代码标注了"以现状串/字段为准覆盖占位"——这是**有意的**(behavior-preserving 重构必须对齐真实现状,实现者读现状后落定),非偷懒占位;新代码(Task 1 ledger、Task 2 测试结构)给了完整代码。
- **类型一致**:`RevivalRecord`/`RevivalLedger`/`record_death`/`record_appearance`/`revivals`/`resolve_gating`/`SOURCE_PRECEDENCE` 跨任务一致。
- **风险**:最高风险在 Task 3 与 Task 5(直接动 `ft_revival_residual` 链路)——二者均以金标+装配网为即时红灯守门。
