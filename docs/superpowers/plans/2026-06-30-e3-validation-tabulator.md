# E3 验证块 tabulator + 评分工件 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现验证块的**唯一新代码**——`scripts/validation_tabulate.py`(纯读盘出 5 张表 + C 门 go/no-go 判据)+ `scripts/jury_to_scorecard.py`(jury JSON→scorecard 转换契约)+ 两个冻结 prompt 工件(jury rubric / 上游探针)。

**Architecture:** tabulator = 纯函数(吃已解析的 `BookRecord` 列表 → 出 dict)+ 薄 IO 外壳(CLI 读盘);所有判据/统计纯函数可单测,不调 API。跑书/jury 编排由人执行(非本计划范围),本计划只产"读产物→出表/判据"的可复跑工具 + 冻结的评分提示词。

**Tech Stack:** Python 3(stdlib + PyYAML);pytest;`PYTHONPATH=src`;Windows 下 stdout 需 `reconfigure(encoding="utf-8")`。

## Global Constraints
- 验证块 spec:`docs/superpowers/specs/2026-06-30-e3-validation-ladder-design.md`(codex 3 轮 approved,rounds=3)。本计划逐条实现其"产出指标 / go/no-go / 上游可拦率 / 存储+ingest 契约 / 评分"节,**不得偏离已定阈值**。
- **假阳判据(预登记,定死)**:门放行(`deliverable=true`)书,某 judge `deliver=="no"` **或** `承重<50` → 该 judge 假阳。
- **C 门 go/no-go**(设门放行 P):P≥4 → 全局停升只认**重叠假阳≥2**(双族共识);单 judge 假阳≥2 但重叠<2 → `待查`(不全局停);**P<4 → `低功效`(不当安全升档)**。
- **不合议**:逐 judge 分别计数 + 重叠,绝不"任一 judge"折叠成单一交付判。
- 评委 = `opus` + `gpt55`(弃 deepseek);rubric = `story4` 四维(故事性0.3/笔力0.25/人0.25/承重0.2,0–100)+ `deliver`(yes/no)+ `reject_reason` + `comments`,**与 `calibration.RUBRIC_WEIGHTS['story4']` 逐字一致**。
- tabulator **纯读盘、不调 API**;Windows stdout/stderr utf-8 硬化(镜 hfl_ingest 教训)。
- 全量 `pytest -m 'not api'` 须绿;tooling 走 SDD(逐任务 TDD + 两段复核 + opus 终审)。

## File Structure
- `scripts/validation_tabulate.py` — tabulator:`FAILURE_CATEGORIES`、`BookRecord`、`load_records`、`false_accept_table`、`gate_decision`、`separation`、`judge_reliability`、`failure_mode_table`、`upstream_interception`、`format_snapshot`、`main`。
- `tests/test_validation_tabulate.py` — 纯函数单测(喂合成 `BookRecord`,不碰盘/网)。
- `scripts/jury_to_scorecard.py` — jury JSON → `scorecard_<judge>.yaml`(喂 `hfl_ingest.py`)。
- `tests/test_jury_to_scorecard.py` — 转换单测。
- `docs/superpowers/specs/validation-jury-rubric.md` — 冻结的盲评 jury 提示词(story4)。
- `docs/superpowers/specs/validation-upstream-probe.md` — 冻结的上游 bible/plan 探针提示词。

---

### Task 1: 失败类目词表 + BookRecord 模型 + loader

**Files:**
- Create: `scripts/validation_tabulate.py`
- Test: `tests/test_validation_tabulate.py`

**Interfaces:**
- Produces:
  - `FAILURE_CATEGORIES: tuple[str, ...]`
  - `@dataclass BookRecord`: `slug:str`、`deliverable:bool`、`jury:dict[str,dict]`(judge→{故事性,笔力,人,承重,total,deliver,reject_reason,comments})、`upstream:dict[str,list[str]]`(judge→预测类目)、`observed:list[str]`(人工标注的实测硬伤类目)、`severity:float|None`(= 各 judge 承重最小值,越低越严)
  - `JUDGES = ("opus", "gpt55")`
  - `load_records(vdir, labels) -> list[BookRecord]`(IO:读 `<vdir>/<slug>/report.json` 的 `signals.deliverable` + `<vdir>/jury/<slug>__<judge>.json` + `<vdir>/upstream/<slug>__<judge>.json`;`labels` = `{slug: [类目]}` 人工实测标注)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_validation_tabulate.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validation_tabulate as vt


def _rec(slug, deliverable, opus, gpt, observed=(), upstream=None, severity=None):
    """合成 BookRecord. opus/gpt = (承重, deliver) 简写; 其余维补占位."""
    def jud(t):
        carry, deliver = t
        total = round(60 * 0.30 + 60 * 0.25 + 60 * 0.25 + carry * 0.20, 2)  # story4(其余维=60)
        return {"故事性": 60, "笔力": 60, "人": 60, "承重": carry,
                "total": total, "deliver": deliver, "reject_reason": "", "comments": ""}
    return vt.BookRecord(slug=slug, deliverable=deliverable,
                         jury={"opus": jud(opus), "gpt55": jud(gpt)},
                         upstream=upstream or {"opus": [], "gpt55": []},
                         observed=list(observed),
                         severity=severity if severity is not None else min(opus[0], gpt[0]))


def test_failure_categories_present():
    assert "境界乱序" in vt.FAILURE_CATEGORIES
    assert "性别错" in vt.FAILURE_CATEGORIES
    assert len(vt.FAILURE_CATEGORIES) >= 8


def test_bookrecord_construct():
    r = _rec("b1", True, (80, "yes"), (60, "no"))
    assert r.slug == "b1" and r.deliverable is True
    assert r.jury["gpt55"]["承重"] == 60
    assert r.severity == 60
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: FAIL（`No module named validation_tabulate` 或 `AttributeError`）

- [ ] **Step 3: 写最小实现**

```python
# scripts/validation_tabulate.py
"""E3 验证块 tabulator: 纯读盘出 5 表 + C 门 go/no-go。不调 API。
用法: python scripts/validation_tabulate.py <validation_dir> [--labels labels.yaml] [--rung C]
见 docs/superpowers/specs/2026-06-30-e3-validation-ladder-design.md。"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

JUDGES = ("opus", "gpt55")
CARRY_THRESHOLD = 50.0          # 承重<50 = 假阳信号(预登记)
MIN_POWER = 4                   # 门放行 P<4 → 低功效
OVERLAP_STOP = 2                # 重叠假阳≥2 → 全局停升
STORY4_W = {"故事性": 0.30, "笔力": 0.25, "人": 0.25, "承重": 0.20}

FAILURE_CATEGORIES = (
    "境界乱序", "修为倒退", "性别错", "混名/认亲矛盾", "死人复活",
    "章节复制/注水", "DNA/身世互斥", "人设崩", "现代腔出戏",
)


@dataclass
class BookRecord:
    slug: str
    deliverable: bool
    jury: dict                      # judge -> {故事性,笔力,人,承重,total,deliver,reject_reason,comments}
    upstream: dict = field(default_factory=dict)   # judge -> [预测类目]
    observed: list = field(default_factory=list)   # 人工标注实测硬伤类目
    severity: float | None = None   # 各 judge 承重最小值(越低越严)


def _story4_total(d: dict) -> float:
    return round(sum(float(d[k]) * w for k, w in STORY4_W.items()), 2)


def load_records(vdir, labels: dict | None = None) -> list[BookRecord]:
    vdir = Path(vdir); labels = labels or {}
    recs = []
    jury_dir = vdir / "jury"
    slugs = sorted({p.name.split("__")[0] for p in jury_dir.glob("*__*.json")}) if jury_dir.is_dir() else []
    for slug in slugs:
        rep = vdir / slug / "report.json"
        deliverable = False
        if rep.exists():
            sig = (json.loads(rep.read_text(encoding="utf-8")).get("signals") or {})
            deliverable = bool(sig.get("deliverable"))
        jury = {}
        for j in JUDGES:
            p = jury_dir / f"{slug}__{j}.json"
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                d.setdefault("total", _story4_total(d))
                jury[j] = d
        upstream = {}
        for j in JUDGES:
            p = vdir / "upstream" / f"{slug}__{j}.json"
            if p.exists():
                upstream[j] = list(json.loads(p.read_text(encoding="utf-8")).get("predicted", []))
        carries = [jury[j]["承重"] for j in jury if "承重" in jury[j]]
        recs.append(BookRecord(slug=slug, deliverable=deliverable, jury=jury,
                               upstream=upstream, observed=list(labels.get(slug, [])),
                               severity=min(carries) if carries else None))
    return recs
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add scripts/validation_tabulate.py tests/test_validation_tabulate.py
git commit -m "feat(e3-tab): validation tabulator 模型 + loader"
```

---

### Task 2: 假阳表 + C 门 go/no-go（核心判据）

**Files:**
- Modify: `scripts/validation_tabulate.py`
- Test: `tests/test_validation_tabulate.py`

**Interfaces:**
- Consumes: `BookRecord`、`JUDGES`、`CARRY_THRESHOLD`、`MIN_POWER`、`OVERLAP_STOP`
- Produces:
  - `is_false_accept(rec, judge, carry_threshold=CARRY_THRESHOLD) -> bool`(门放行 且 该 judge deliver=="no" 或 承重<阈)
  - `false_accept_table(records, carry_threshold=CARRY_THRESHOLD) -> dict`:`{"n_passed":int, "per_judge":{judge:{"fp_slugs":[...],"n":int}}, "overlap_slugs":[...], "n_overlap":int, "rows":[{"slug","judge","承重","total","reject_reason"}]}`(`rows` = spec 要的行级证据表:每个(门放行书×判它假阳的 judge)一行)
  - `gate_decision(records, carry_threshold=CARRY_THRESHOLD, min_power=MIN_POWER, overlap_stop=OVERLAP_STOP) -> dict`:`{"P":int, "per_judge_fp":{judge:int}, "n_overlap":int, "verdict":str, "notes":[str]}`,verdict∈{`"unsafe_consensus"`,`"single_judge_investigate"`,`"safe_advance"`,`"low_power_inconclusive"`}

- [ ] **Step 1: 写失败测试**

```python
def test_is_false_accept_rules():
    # 门放行 + 某judge deliver=no → 假阳
    r = _rec("b", True, (80, "yes"), (70, "no"))
    assert vt.is_false_accept(r, "gpt55") is True
    assert vt.is_false_accept(r, "opus") is False
    # 门放行 + 承重<50 → 假阳(即便 deliver=yes)
    r2 = _rec("b2", True, (45, "yes"), (80, "yes"))
    assert vt.is_false_accept(r2, "opus") is True
    # 门未放行 → 不算假阳(假阳是"门说行但judge说不行")
    r3 = _rec("b3", False, (10, "no"), (10, "no"))
    assert vt.is_false_accept(r3, "opus") is False


def test_false_accept_table_counts_and_overlap():
    recs = [
        _rec("p1", True, (40, "no"), (40, "no")),   # 两judge都假阳 → overlap
        _rec("p2", True, (80, "yes"), (45, "no")),  # 仅 gpt55 假阳
        _rec("p3", True, (90, "yes"), (90, "yes")), # 无假阳
        _rec("r1", False, (10, "no"), (10, "no")),  # 门未放行,不计入 passed
    ]
    t = vt.false_accept_table(recs)
    assert t["n_passed"] == 3
    assert t["per_judge"]["opus"]["n"] == 1 and t["per_judge"]["gpt55"]["n"] == 2
    assert t["n_overlap"] == 1 and t["overlap_slugs"] == ["p1"]
    # 行级证据表(spec 要):p1×2(两judge) + p2×1(gpt55) = 3 行
    assert len(t["rows"]) == 3
    assert any(r["slug"] == "p2" and r["judge"] == "gpt55" and r["承重"] == 45 for r in t["rows"])


def test_gate_decision_overlap_stop():
    # P>=4, 重叠假阳>=2 → unsafe_consensus
    recs = [_rec(f"p{i}", True, (40, "no"), (40, "no")) for i in range(2)] + \
           [_rec(f"q{i}", True, (90, "yes"), (90, "yes")) for i in range(3)]
    d = vt.gate_decision(recs)
    assert d["P"] == 5 and d["n_overlap"] == 2 and d["verdict"] == "unsafe_consensus"


def test_gate_decision_single_judge_investigate():
    # P>=4, 仅 gpt55 假阳>=2, 重叠<2 → single_judge_investigate(不全局停)
    recs = [_rec(f"p{i}", True, (90, "yes"), (40, "no")) for i in range(2)] + \
           [_rec(f"q{i}", True, (90, "yes"), (90, "yes")) for i in range(3)]
    d = vt.gate_decision(recs)
    assert d["verdict"] == "single_judge_investigate"
    assert d["per_judge_fp"]["gpt55"] == 2 and d["n_overlap"] == 0


def test_gate_decision_low_power():
    # P<4 → low_power_inconclusive(不当安全升档)
    recs = [_rec("p1", True, (90, "yes"), (90, "yes"))] + \
           [_rec(f"r{i}", False, (10, "no"), (10, "no")) for i in range(7)]
    d = vt.gate_decision(recs)
    assert d["P"] == 1 and d["verdict"] == "low_power_inconclusive"


def test_gate_decision_safe_advance():
    recs = [_rec(f"p{i}", True, (90, "yes"), (85, "yes")) for i in range(5)]
    d = vt.gate_decision(recs)
    assert d["verdict"] == "safe_advance"
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: FAIL（`AttributeError: ... is_false_accept`）

- [ ] **Step 3: 写实现**

```python
def is_false_accept(rec: BookRecord, judge: str, carry_threshold: float = CARRY_THRESHOLD) -> bool:
    """假阳 = 门放行(deliverable) 但该 judge 判 deliver==no 或 承重<阈。门未放行的书不算假阳。"""
    if not rec.deliverable:
        return False
    j = rec.jury.get(judge)
    if not j:
        return False
    return str(j.get("deliver")).lower() == "no" or float(j.get("承重", 100)) < carry_threshold


def false_accept_table(records, carry_threshold: float = CARRY_THRESHOLD) -> dict:
    passed = [r for r in records if r.deliverable]
    per_judge = {}
    for jdg in JUDGES:
        fp = [r.slug for r in passed if is_false_accept(r, jdg, carry_threshold)]
        per_judge[jdg] = {"fp_slugs": fp, "n": len(fp)}
    fp_sets = [set(per_judge[j]["fp_slugs"]) for j in JUDGES]
    overlap = sorted(set.intersection(*fp_sets)) if fp_sets else []
    rows = [{"slug": r.slug, "judge": j, "承重": r.jury[j]["承重"],
             "total": r.jury[j]["total"], "reject_reason": r.jury[j].get("reject_reason", "")}
            for r in passed for j in JUDGES if is_false_accept(r, j, carry_threshold)]
    return {"n_passed": len(passed), "per_judge": per_judge,
            "overlap_slugs": overlap, "n_overlap": len(overlap), "rows": rows}


def gate_decision(records, carry_threshold: float = CARRY_THRESHOLD,
                  min_power: int = MIN_POWER, overlap_stop: int = OVERLAP_STOP) -> dict:
    t = false_accept_table(records, carry_threshold)
    P = t["n_passed"]
    per_judge_fp = {j: t["per_judge"][j]["n"] for j in JUDGES}
    n_overlap = t["n_overlap"]
    notes = []
    if P < min_power:
        verdict = "low_power_inconclusive"
        notes.append(f"门放行 P={P}<{min_power}: 假阳检验功效不足, 不当'安全'自动升档; 另评门拒收书测过度拒收; 门放行率过低本身=发现(门可能过严)")
    elif n_overlap >= overlap_stop:
        verdict = "unsafe_consensus"
        notes.append(f"重叠假阳 {n_overlap}>={overlap_stop}(双族共识): 门非交付安全 → 停升, 转修门/上游")
    elif any(per_judge_fp[j] >= overlap_stop for j in JUDGES):
        verdict = "single_judge_investigate"
        hi = [j for j in JUDGES if per_judge_fp[j] >= overlap_stop]
        notes.append(f"单 judge 假阳≥{overlap_stop}({','.join(hi)}) 但重叠<{overlap_stop}: 不全局停; 标该 judge 视角不安全 + 触发调查(judge 偏严 vs 真硬伤), 本档=待查, 可带 flag 升档")
    else:
        verdict = "safe_advance"
    return {"P": P, "per_judge_fp": per_judge_fp, "n_overlap": n_overlap,
            "verdict": verdict, "notes": notes}
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add scripts/validation_tabulate.py tests/test_validation_tabulate.py
git commit -m "feat(e3-tab): 假阳表 + C 门 go/no-go(重叠驱动, 不合议)"
```

---

### Task 3: 门分离度 + judge 可靠性 + 失败模式频率×严重度表

**Files:**
- Modify: `scripts/validation_tabulate.py`
- Test: `tests/test_validation_tabulate.py`

**Interfaces:**
- Consumes: `BookRecord`、`JUDGES`、`FAILURE_CATEGORIES`
- Produces:
  - `separation(records) -> dict`:`{judge:{"pass_mean":float|None,"reject_mean":float|None,"delta":float|None}}`(按门放行/拒组的 judge total 均值差;组空→None)
  - `judge_reliability(records) -> dict`:`{"per_book_spread":{slug:float}, "divergent_slugs":[slug], "mean_bias":float|None, "deliver_agreement_rate":float|None}`(spread=|opus−gpt55| total;**divergent_slugs = spread>15 的本(spec 的分歧桶)**;bias=mean(opus−gpt55);agreement=两judge deliver 同判比例)
  - `failure_mode_table(records) -> dict`:`{category:{"n_books":int,"freq":float,"avg_severity":float|None,"gate_caught":int}}`(freq=n_books/总本数;avg_severity=含该类目书的 severity 均值;gate_caught=含该类目书中门拒收(deliverable=False)的本数)

- [ ] **Step 1: 写失败测试**

```python
def test_separation_delta():
    recs = [_rec("p1", True, (90, "yes"), (80, "yes")),   # pass 组
            _rec("r1", False, (40, "no"), (30, "no"))]    # reject 组
    s = vt.separation(recs)
    # opus pass total = story4(承重90,其余60)=... 只验 delta 为正(pass>reject)
    assert s["opus"]["delta"] > 0 and s["gpt55"]["delta"] > 0


def test_judge_reliability():
    recs = [_rec("b1", True, (80, "yes"), (60, "no")),    # deliver 不同判
            _rec("b2", True, (70, "yes"), (70, "yes"))]   # 同判
    rel = vt.judge_reliability(recs)
    assert rel["deliver_agreement_rate"] == 0.5
    assert rel["per_book_spread"]["b1"] >= 0
    assert rel["mean_bias"] is not None   # opus−gpt55 平均


def test_judge_reliability_divergence_bucket():
    # 承重差 80 → total spread = 0.2*80 = 16 > 15 → 进分歧桶
    recs = [_rec("big", True, (100, "yes"), (20, "no")),
            _rec("small", True, (70, "yes"), (65, "yes"))]
    rel = vt.judge_reliability(recs)
    assert "big" in rel["divergent_slugs"] and "small" not in rel["divergent_slugs"]


def test_failure_mode_table():
    recs = [_rec("b1", False, (30, "no"), (30, "no"), observed=["境界乱序", "修为倒退"]),
            _rec("b2", True, (40, "no"), (40, "no"), observed=["境界乱序"]),
            _rec("b3", True, (90, "yes"), (90, "yes"), observed=[])]
    tbl = vt.failure_mode_table(recs)
    assert tbl["境界乱序"]["n_books"] == 2
    assert abs(tbl["境界乱序"]["freq"] - 2/3) < 1e-9
    assert tbl["境界乱序"]["gate_caught"] == 1     # b1 门拒(deliverable False)
    assert tbl["修为倒退"]["n_books"] == 1
    assert "性别错" not in tbl or tbl["性别错"]["n_books"] == 0
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: FAIL（`AttributeError: separation`）

- [ ] **Step 3: 写实现**

```python
def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def separation(records) -> dict:
    out = {}
    for jdg in JUDGES:
        pas = [r.jury[jdg]["total"] for r in records if r.deliverable and jdg in r.jury]
        rej = [r.jury[jdg]["total"] for r in records if not r.deliverable and jdg in r.jury]
        pm, rm = _mean(pas), _mean(rej)
        out[jdg] = {"pass_mean": pm, "reject_mean": rm,
                    "delta": round(pm - rm, 2) if pm is not None and rm is not None else None}
    return out


def judge_reliability(records) -> dict:
    spread, bias, agree = {}, [], []
    for r in records:
        if "opus" in r.jury and "gpt55" in r.jury:
            o, g = r.jury["opus"], r.jury["gpt55"]
            spread[r.slug] = round(abs(o["total"] - g["total"]), 2)
            bias.append(o["total"] - g["total"])
            agree.append(str(o.get("deliver")).lower() == str(g.get("deliver")).lower())
    return {"per_book_spread": spread,
            "divergent_slugs": sorted([s for s, sp in spread.items() if sp > 15]),
            "mean_bias": round(sum(bias) / len(bias), 2) if bias else None,
            "deliver_agreement_rate": round(sum(agree) / len(agree), 4) if agree else None}


def failure_mode_table(records) -> dict:
    N = len(records) or 1
    out = {}
    for cat in FAILURE_CATEGORIES:
        books = [r for r in records if cat in r.observed]
        if not books:
            continue
        sev = _mean([r.severity for r in books])
        out[cat] = {"n_books": len(books), "freq": len(books) / N,
                    "avg_severity": sev,
                    "gate_caught": sum(1 for r in books if not r.deliverable)}
    return out
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/validation_tabulate.py tests/test_validation_tabulate.py
git commit -m "feat(e3-tab): 门分离度 + judge 可靠性 + 失败模式频率×严重度"
```

---

### Task 4: 上游可拦率表（测"跨模型审核越靠前越有价值"）

**Files:**
- Modify: `scripts/validation_tabulate.py`
- Test: `tests/test_validation_tabulate.py`

**Interfaces:**
- Consumes: `BookRecord`、`JUDGES`
- Produces:
  - `upstream_interception(records) -> dict`:`{"per_book":{slug:{"observed":[...],"predicted":[...],"intercepted":[...],"rate":float|None}}, "overall_rate":float|None, "by_category":{cat:{"observed":int,"predicted_upstream":int}}}`
    - 每本 predicted = 两 judge 上游预测类目**并集**;intercepted = predicted ∩ observed;rate = |intercepted|/|observed|(observed 空→None)
    - overall_rate = Σ|intercepted| / Σ|observed|(全书,observed 空跳过)
    - by_category:每类目 在 observed 出现本数 vs 在上游 predicted 出现本数(定位"上游可防 vs 起草新引入")

- [ ] **Step 1: 写失败测试**

```python
def test_upstream_interception():
    recs = [
        _rec("b1", False, (30, "no"), (30, "no"), observed=["境界乱序", "性别错"],
             upstream={"opus": ["境界乱序"], "gpt55": ["境界乱序", "数值错"]}),  # 拦到 境界乱序, 漏 性别错
        _rec("b2", True, (40, "no"), (40, "no"), observed=["章节复制/注水"],
             upstream={"opus": [], "gpt55": []}),                                # 上游全漏
    ]
    u = vt.upstream_interception(recs)
    assert sorted(u["per_book"]["b1"]["intercepted"]) == ["境界乱序"]
    assert abs(u["per_book"]["b1"]["rate"] - 0.5) < 1e-9
    assert u["per_book"]["b2"]["rate"] == 0.0
    # overall = 拦到1(境界乱序) / observed总3 = 1/3
    assert abs(u["overall_rate"] - 1/3) < 1e-9
    assert u["by_category"]["境界乱序"]["observed"] == 1
    assert u["by_category"]["境界乱序"]["predicted_upstream"] == 1


def test_upstream_interception_no_observed():
    recs = [_rec("b", True, (90, "yes"), (90, "yes"), observed=[], upstream={"opus": [], "gpt55": []})]
    u = vt.upstream_interception(recs)
    assert u["per_book"]["b"]["rate"] is None
    assert u["overall_rate"] is None     # 无 observed → N/A 不崩
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: FAIL（`AttributeError: upstream_interception`）

- [ ] **Step 3: 写实现**

```python
def upstream_interception(records) -> dict:
    per_book, tot_int, tot_obs = {}, 0, 0
    by_cat = {}
    for r in records:
        obs = set(r.observed)
        pred = set().union(*[set(r.upstream.get(j, [])) for j in JUDGES]) if r.upstream else set()
        inter = obs & pred
        rate = (len(inter) / len(obs)) if obs else None
        per_book[r.slug] = {"observed": sorted(obs), "predicted": sorted(pred),
                            "intercepted": sorted(inter), "rate": rate}
        if obs:
            tot_int += len(inter); tot_obs += len(obs)
        for c in obs:
            by_cat.setdefault(c, {"observed": 0, "predicted_upstream": 0})["observed"] += 1
        for c in (pred & obs):
            by_cat.setdefault(c, {"observed": 0, "predicted_upstream": 0})["predicted_upstream"] += 1
    return {"per_book": per_book,
            "overall_rate": (tot_int / tot_obs) if tot_obs else None,
            "by_category": by_cat}
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/validation_tabulate.py tests/test_validation_tabulate.py
git commit -m "feat(e3-tab): 上游可拦率表(测跨族审核前移价值)"
```

---

### Task 5: 快照汇总 format_snapshot + CLI main

**Files:**
- Modify: `scripts/validation_tabulate.py`
- Test: `tests/test_validation_tabulate.py`

**Interfaces:**
- Consumes: 全部上述函数
- Produces:
  - `format_snapshot(records, rung="") -> str`(把 gate_decision/false_accept_table/separation/judge_reliability/failure_mode_table/upstream_interception 汇成一张人读快照文本,含诚实边界提醒)
  - `main(argv=None)`:解析 `<validation_dir> [--labels labels.yaml] [--rung X]`,`load_records` → `print(format_snapshot(...))`

- [ ] **Step 1: 写失败测试**

```python
def test_format_snapshot_smoke():
    recs = [_rec("p1", True, (40, "no"), (40, "no"), observed=["境界乱序"],
                 upstream={"opus": ["境界乱序"], "gpt55": []})]
    out = vt.format_snapshot(recs, rung="C")
    assert "go/no-go" in out and "上游可拦率" in out
    assert "分歧桶" in out        # |Δ|>15 桶必现
    assert "AI-only" in out      # 诚实边界提醒必现
    assert isinstance(out, str) and len(out) > 0
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: FAIL

- [ ] **Step 3: 写实现**

```python
def format_snapshot(records, rung: str = "") -> str:
    gd = gate_decision(records)
    fa = false_accept_table(records)
    sep = separation(records)
    rel = judge_reliability(records)
    fm = failure_mode_table(records)
    up = upstream_interception(records)
    L = [f"=== 验证块快照 rung={rung or '?'} (n={len(records)}) ==="]
    L.append(f"[go/no-go] verdict={gd['verdict']} P={gd['P']} per_judge_fp={gd['per_judge_fp']} 重叠={gd['n_overlap']}")
    for n in gd["notes"]:
        L.append(f"  - {n}")
    L.append(f"[假阳] 放行={fa['n_passed']} opus={fa['per_judge']['opus']['n']} gpt55={fa['per_judge']['gpt55']['n']} 重叠={fa['overlap_slugs']}")
    for row in fa["rows"]:
        L.append(f"    · {row['slug']} [{row['judge']}] 承重{row['承重']} 总分{row['total']} 因:{row['reject_reason']}")
    L.append(f"[门分离度] " + " ".join(f"{j}:Δ{sep[j]['delta']}" for j in JUDGES))
    L.append(f"[judge可靠性] 偏置(opus-gpt55)={rel['mean_bias']} deliver同判率={rel['deliver_agreement_rate']} 分歧桶(|Δ|>15)={rel['divergent_slugs']}")
    L.append("[失败模式 频率×严重度]")
    for c, v in sorted(fm.items(), key=lambda kv: -kv[1]["freq"]):
        L.append(f"  {c}: 频率{v['freq']:.0%}({v['n_books']}本) 严重度(承重){v['avg_severity']} 门抓到{v['gate_caught']}")
    L.append(f"[上游可拦率] overall={up['overall_rate']}")
    for c, v in sorted(up["by_category"].items(), key=lambda kv: -kv[1]["observed"]):
        L.append(f"  {c}: 实测{v['observed']}本 上游预测中{v['predicted_upstream']}本")
    L.append("[诚实边界] AI-only 无人锚→非真值; 小n+~20分judge分歧→误差带; 种子行来自#1前引擎不混入当前门相关性。")
    return "\n".join(L)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("validation_dir")
    ap.add_argument("--labels", default=None, help="人工实测硬伤标注 YAML: {slug:[类目]}")
    ap.add_argument("--rung", default="")
    a = ap.parse_args(argv)
    labels = {}
    if a.labels and Path(a.labels).exists():
        import yaml
        labels = yaml.safe_load(Path(a.labels).read_text(encoding="utf-8")) or {}
    recs = load_records(a.validation_dir, labels)
    print(format_snapshot(recs, rung=a.rung))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_validation_tabulate.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/validation_tabulate.py tests/test_validation_tabulate.py
git commit -m "feat(e3-tab): 快照汇总 + CLI"
```

---

### Task 6: jury JSON → scorecard YAML 转换（ingest 契约）

**Files:**
- Create: `scripts/jury_to_scorecard.py`
- Test: `tests/test_jury_to_scorecard.py`

**Interfaces:**
- Produces:
  - `build_scorecard(jury_by_slug: dict, rater: str, date: str | None = None) -> dict`(`{rater, date, scores:{slug:{故事性,笔力,人,承重,追读,最致命←reject_reason,点评←comments}}}`)——纯函数
  - `main(argv=None)`:`<jury_dir> --judge <opus|gpt55> --out <scorecard.yaml> [--date ...]`,读 `<jury_dir>/<slug>__<judge>.json` 聚合 → 写 scorecard YAML
- 契约对齐 `scripts/hfl_ingest.py`(其 `_extract_dims` 认 `RUBRIC_WEIGHTS['story4']` 四维;comments 由 `追读/最致命/点评` 拼)。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_jury_to_scorecard.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jury_to_scorecard as j2s


def test_build_scorecard_maps_fields():
    jury = {"book1": {"故事性": 60, "笔力": 55, "人": 50, "承重": 30,
                      "deliver": "no", "reject_reason": "境界乱序", "comments": "套路化"}}
    sc = j2s.build_scorecard(jury, rater="opus", date="2026-06-30")
    assert sc["rater"] == "opus"
    s = sc["scores"]["book1"]
    assert s["故事性"] == 60 and s["承重"] == 30
    assert s["最致命"] == "境界乱序" and s["点评"] == "套路化"


def test_build_scorecard_roundtrips_to_extract_dims():
    # 产出的 scores 须含 story4 四维(hfl_ingest._extract_dims 可识别)
    jury = {"b": {"故事性": 1, "笔力": 2, "人": 3, "承重": 4, "deliver": "yes",
                  "reject_reason": "", "comments": ""}}
    sc = j2s.build_scorecard(jury, rater="gpt55")
    for k in ("故事性", "笔力", "人", "承重"):
        assert k in sc["scores"]["b"]
    assert "date" not in sc      # date=None 省略键(防 hfl_ingest 读成 "None")
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_jury_to_scorecard.py -q`
Expected: FAIL（`No module named jury_to_scorecard`）

- [ ] **Step 3: 写实现**

```python
# scripts/jury_to_scorecard.py
"""jury JSON → scorecard_<judge>.yaml(喂 scripts/hfl_ingest.py)。
用法: python scripts/jury_to_scorecard.py <jury_dir> --judge opus --out <dir>/scorecard_opus.yaml
见 spec '存储 + ingest 契约' 节。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

_DIMS = ("故事性", "笔力", "人", "承重")


def build_scorecard(jury_by_slug: dict, rater: str, date: str | None = None) -> dict:
    scores = {}
    for slug, j in jury_by_slug.items():
        scores[slug] = {
            **{k: j[k] for k in _DIMS if k in j},
            "追读": "", "最致命": j.get("reject_reason", ""), "点评": j.get("comments", ""),
        }
    out = {"rater": rater, "scores": scores}
    if date is not None:
        out["date"] = date      # date=None 时省略键: 防 hfl_ingest 把 YAML null 读成字符串 "None"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("jury_dir")
    ap.add_argument("--judge", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=None)
    a = ap.parse_args(argv)
    import yaml
    jd = Path(a.jury_dir)
    jury = {}
    for p in sorted(jd.glob(f"*__{a.judge}.json")):
        slug = p.name.split("__")[0]
        jury[slug] = json.loads(p.read_text(encoding="utf-8"))
    sc = build_scorecard(jury, rater=a.judge, date=a.date)
    Path(a.out).write_text(yaml.safe_dump(sc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"✓ {len(jury)} 本 → {a.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_jury_to_scorecard.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/jury_to_scorecard.py tests/test_jury_to_scorecard.py
git commit -m "feat(e3-tab): jury JSON→scorecard 转换契约"
```

---

### Task 7: 冻结评分提示词工件（jury rubric + 上游探针）

**Files:**
- Create: `docs/superpowers/specs/validation-jury-rubric.md`
- Create: `docs/superpowers/specs/validation-upstream-probe.md`

**Interfaces:** 无代码;两份**冻结提示词**,供编排(Opus 子代理 / GPT5.5 codex)逐字使用,保证盲评/上游核查跨本一致。

- [ ] **Step 1: 写 jury rubric 工件**

`docs/superpowers/specs/validation-jury-rubric.md` 内容(盲评,严格 JSON 输出,与 story4 + 现有 jury JSON schema 逐字一致):

```markdown
# 验证块 jury 盲评提示词(冻结,逐字用)

你是网文成品质量评委。**只**依据下面给你的成品正文打分,不臆测来源/模型/门判。
四维各 0–100;`deliver` = 这本能否原样交付读者(yes/no);`reject_reason` = 最致命问题一句;`comments` = 各维简评(致命点带证据/章号)。
**只输出一个 JSON 对象,无其它文字**:
{"故事性":int,"笔力":int,"人":int,"承重":int,"deliver":"yes|no","reject_reason":"...","comments":"..."}
维定义:故事性=钩子/爽感/追读力;笔力=句子/画面/去AI腔;人=人物主动性/弧光/不崩;承重=连续性/设定自洽/无硬伤(境界乱序、修为倒退、性别错、混名、复活、章节复制注水、身世矛盾)。
```

- [ ] **Step 2: 写上游探针工件**

`docs/superpowers/specs/validation-upstream-probe.md` 内容(只审 bible/macro/plan JSON,预测末态硬伤类目):

```markdown
# 验证块 上游跨族探针提示词(冻结,逐字用)

你是设定/大纲审查员。**只**依据给你的 bible/macro/plan(JSON),预测若按此起草 60 章,**最可能出现哪些末态硬伤**。
不改写、不补全;只指出风险。类目限定在:境界乱序 / 修为倒退 / 性别错 / 混名认亲矛盾 / 死人复活 / 章节复制注水 / DNA身世互斥 / 人设崩 / 现代腔出戏。
**只输出一个 JSON 对象**:{"predicted":["类目",...],"why":{"类目":"依据(指 bible/plan 哪处)"}}
predicted 只填你有具体依据的类目;无风险则 predicted 为空数组。
```

- [ ] **Step 3: 提交**

```bash
git add docs/superpowers/specs/validation-jury-rubric.md docs/superpowers/specs/validation-upstream-probe.md
git commit -m "docs(e3-tab): 冻结 jury rubric + 上游探针提示词"
```

---

## 终检
- [ ] 全量 `python -m pytest -m 'not api'` 绿(报确切 passed/deselected)。
- [ ] tabulator 在 Stage-0 现有产物上 smoke 跑一次(`output/stage0` 有 report.json,可临时拼 jury 目录)验证不崩——或留待真验证块产物。
- [ ] 全程不调 API、不改 gate/检测器/冻结向量/gold。

<!-- codex-peer-reviewed: 2026-06-30T10:13:04Z rounds=2 verdict=approved -->
