# PreDraft Review v0 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 实现 PreDraft Review v0 的**可实现代码**:`scripts/predraft_checks.py`(确定性正则预检:亲属唯一+重复章)+ 冻结 `docs/superpowers/specs/predraft-review-prompt.md`(LLM 审提示词)+ `scripts/predraft_tabulate.py`(校准:各 reviewer×类目 精度/召回 + DeepSeek-vs-跨族)。LLM 三路审是**编排**(B 档跑时人工执行),非本计划代码。

**Architecture:** predraft_checks = 纯函数吃 bible/plan dict → findings 列表(启发式正则,非 typed)。predraft_tabulate = 纯函数吃 predraft findings + 实测标注 → 精度表。全部不调 API、可单测。

**Tech Stack:** Python 3 stdlib + PyYAML;pytest;Windows stdout `reconfigure(utf-8)`;`python -m pytest`(pyproject 已设 pythonpath,**勿加 PYTHONPATH=src**)。

## Global Constraints
- spec:`docs/superpowers/specs/2026-06-30-predraft-review-v0-design.md`(codex approved rounds=2)。逐条实现其架构 §1(确定性层)、验证节、校准协议。
- **确定性层 = 启发式正则解析 prose 模式,非 typed schema**(codex 实证):亲属在 `characters[].key_relation`(prose),重复章看 `plan.chapters[].scenes[].source_scene_index`(scene 级)。血型/境界**不在确定性层**(已移 LLM)。
- finding schema:`{category, severity, evidence_path, contradiction, confidence, parse_pattern}`。
- **schema 容错**:缺字段跳过该检查不崩(镜 loader 教训)。
- 不调 API、不改 produce.run、不接管线门(v0=校准旁路)。
- 全量 `pytest -m 'not api'` 绿;SDD(逐任务 TDD + 两段复核 + opus 终审)。

## File Structure
- `scripts/predraft_checks.py` — `_finding`、`kinship_uniqueness(bible)`、`duplicate_chapter_intent(plan)`、`predraft_checks(bible, plan)`。
- `tests/test_predraft_checks.py` — 纯函数单测。
- `docs/superpowers/specs/predraft-review-prompt.md` — 冻结 LLM 审提示词。
- `scripts/predraft_tabulate.py` — `load_predraft(vdir)`、`precision_recall(predraft, observed)`、`format_predraft_report(...)`、`main`。
- `tests/test_predraft_tabulate.py` — 纯函数单测。

---

### Task 1: predraft_checks — finding 模型 + 亲属唯一性

**Files:**
- Create: `scripts/predraft_checks.py`
- Test: `tests/test_predraft_checks.py`

**Interfaces:**
- Produces:
  - `_KINSHIP_ROLES`(`{"生母":"母","亲生母亲":"母","生父":"父","亲生父亲":"父"}`)
  - `_finding(category, severity, evidence_path, contradiction, confidence, parse_pattern) -> dict`
  - `kinship_uniqueness(bible) -> list[dict]`:扫 `bible["characters"][i]["key_relation"]`(str),正则抽 `(目标人)(角色关键词)`,按 (目标人, 归一角色) 归并 claimant 角色名(`characters[i]["name"]`);**同一 (目标,角色) 被 ≥2 个不同 claimant 声称** → 一条 finding(category="混名/认亲矛盾", severity="hard", confidence="det")。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_predraft_checks.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import predraft_checks as pc


def _bible(chars):
    return {"characters": [{"name": n, "key_relation": kr} for n, kr in chars]}


def test_kinship_dup_mother_flagged():
    b = _bible([("方欣", "苏媚禧生母"), ("李诗蕊", "苏媚禧生母"), ("顾巍", "苏媚禧小叔")])
    fs = pc.kinship_uniqueness(b)
    assert len(fs) == 1
    f = fs[0]
    assert f["category"] == "混名/认亲矛盾" and f["severity"] == "hard"
    assert "苏媚禧" in f["contradiction"] and "方欣" in f["contradiction"] and "李诗蕊" in f["contradiction"]
    assert set(f) == {"category", "severity", "evidence_path", "contradiction", "confidence", "parse_pattern"}


def test_kinship_unique_ok():
    b = _bible([("方欣", "苏媚禧生母"), ("苏强", "苏媚禧生父")])  # 不同角色,各唯一
    assert pc.kinship_uniqueness(b) == []


def test_kinship_same_claimant_not_dup():
    # 同一 claimant 名重复出现不算两人(去重 claimant)
    b = _bible([("方欣", "苏媚禧生母"), ("方欣", "苏媚禧亲生母亲")])
    assert pc.kinship_uniqueness(b) == []


def test_kinship_missing_field_no_crash():
    assert pc.kinship_uniqueness({"characters": [{"name": "甲"}]}) == []   # 无 key_relation
    assert pc.kinship_uniqueness({}) == []                                  # 无 characters
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_predraft_checks.py -q`
Expected: FAIL（`No module named predraft_checks`）

- [ ] **Step 3: 写实现**

```python
# scripts/predraft_checks.py
"""PreDraft Review v0 确定性预检: 启发式正则解析 bible/plan 的 prose 模式 → findings。
非 typed schema(codex 实证: 亲属在 key_relation prose, 重复章看 scenes source_scene_index)。
不调 API。见 docs/superpowers/specs/2026-06-30-predraft-review-v0-design.md。"""
from __future__ import annotations

import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

_KINSHIP_ROLES = {"亲生母亲": "母", "亲生父亲": "父", "生母": "母", "生父": "父"}
_KIN_RE = re.compile(r"(.+?)(亲生母亲|亲生父亲|生母|生父)")


def _finding(category, severity, evidence_path, contradiction, confidence, parse_pattern):
    return {"category": category, "severity": severity, "evidence_path": evidence_path,
            "contradiction": contradiction, "confidence": confidence, "parse_pattern": parse_pattern}


def kinship_uniqueness(bible) -> list[dict]:
    chars = (bible or {}).get("characters") or []
    # (目标人, 归一角色) -> set(claimant 名)
    claims: dict = {}
    for i, c in enumerate(chars):
        if not isinstance(c, dict):
            continue
        kr = c.get("key_relation")
        name = c.get("name")
        if not isinstance(kr, str) or not name:
            continue
        m = _KIN_RE.match(kr.strip())
        if not m:
            continue
        target = m.group(1).strip("的 ，,、").strip()
        role = _KINSHIP_ROLES[m.group(2)]
        if target:
            claims.setdefault((target, role), set()).add(name)
    out = []
    for (target, role), claimants in sorted(claims.items()):
        if len(claimants) >= 2:
            who = "、".join(sorted(claimants))
            out.append(_finding(
                "混名/认亲矛盾", "hard", "characters[].key_relation",
                f"{who} 都被标为「{target}」的{role}(生身唯一角色被多人声称)",
                "det", "key_relation~生母/生父"))
    return out
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_predraft_checks.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add scripts/predraft_checks.py tests/test_predraft_checks.py
git commit -m "feat(predraft): 确定性预检 — 亲属唯一性(key_relation 正则)"
```

---

### Task 2: predraft_checks — 重复章意图 + 顶层聚合

**Files:**
- Modify: `scripts/predraft_checks.py`
- Test: `tests/test_predraft_checks.py`

**Interfaces:**
- Consumes: `_finding`
- Produces:
  - `duplicate_chapter_intent(plan) -> list[dict]`:每章收 `chapters[i]["scenes"][j]["source_scene_index"]`(排除 -1/None)成集合;**不同章的源场景集相交** → finding(category="章节复制/注水", severity="hard", confidence="det")。每对重叠章一条。
  - `predraft_checks(bible, plan) -> list[dict]`:`kinship_uniqueness(bible) + duplicate_chapter_intent(plan)`。

- [ ] **Step 1: 写失败测试**

```python
def _plan(chapter_scene_idxs):
    return {"chapters": [{"scenes": [{"source_scene_index": i} for i in idxs]} for idxs in chapter_scene_idxs]}


def test_dup_chapter_overlap_flagged():
    p = _plan([[5, 6], [6, 7], [9]])   # ch0∩ch1={6}
    fs = pc.duplicate_chapter_intent(p)
    assert len(fs) == 1
    assert fs[0]["category"] == "章节复制/注水" and fs[0]["severity"] == "hard"
    assert "6" in fs[0]["contradiction"]


def test_dup_chapter_no_overlap():
    assert pc.duplicate_chapter_intent(_plan([[1, 2], [3, 4]])) == []


def test_dup_chapter_excludes_sentinel():
    assert pc.duplicate_chapter_intent(_plan([[-1], [-1]])) == []   # -1=无源, 不算重复


def test_dup_chapter_missing_field_no_crash():
    assert pc.duplicate_chapter_intent({}) == []
    assert pc.duplicate_chapter_intent({"chapters": [{"scenes": [{}]}]}) == []   # 无 source_scene_index


def test_predraft_checks_aggregates():
    b = _bible([("方欣", "苏媚禧生母"), ("李诗蕊", "苏媚禧生母")])
    p = _plan([[5], [5]])
    fs = pc.predraft_checks(b, p)
    cats = sorted(f["category"] for f in fs)
    assert cats == ["混名/认亲矛盾", "章节复制/注水"]
```

(`_bible`/`_plan` helper 已在本测试文件;`_plan` 在 Task 2 新增,放文件内 helper 区。)

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_predraft_checks.py -q`
Expected: FAIL（`AttributeError: duplicate_chapter_intent`）

- [ ] **Step 3: 写实现(追加到 `scripts/predraft_checks.py` 末尾)**

```python
def duplicate_chapter_intent(plan) -> list[dict]:
    chapters = (plan or {}).get("chapters") or []
    sets = []
    for ch in chapters:
        if not isinstance(ch, dict):
            sets.append(set()); continue
        idxs = set()
        for sc in (ch.get("scenes") or []):
            if isinstance(sc, dict):
                v = sc.get("source_scene_index")
                if isinstance(v, int) and v >= 0:
                    idxs.add(v)
        sets.append(idxs)
    out = []
    for a in range(len(sets)):
        for b in range(a + 1, len(sets)):
            shared = sets[a] & sets[b]
            if shared:
                out.append(_finding(
                    "章节复制/注水", "hard", f"plan.chapters[{a}|{b}].scenes[].source_scene_index",
                    f"第{a}章与第{b}章共享源场景 {sorted(shared)}(同源被拆多章=复演/注水风险)",
                    "det", "source_scene_index 集合相交"))
    return out


def predraft_checks(bible, plan) -> list[dict]:
    return kinship_uniqueness(bible) + duplicate_chapter_intent(plan)
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_predraft_checks.py -q`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git add scripts/predraft_checks.py tests/test_predraft_checks.py
git commit -m "feat(predraft): 重复章意图(source_scene_index 集合相交) + 顶层聚合"
```

---

### Task 3: 冻结 LLM 预起草审核提示词

**Files:**
- Create: `docs/superpowers/specs/predraft-review-prompt.md`

**Interfaces:** 无代码;冻结提示词,供 DeepSeek自审/Opus/GPT5.5 编排逐字用。

- [ ] **Step 1: 写提示词工件**

`docs/superpowers/specs/predraft-review-prompt.md`:

```markdown
# PreDraft Review LLM 审提示词(冻结,逐字用)

你是设定/大纲结构审查员。**只**依据给你的 bible/macro/plan(JSON),预测若按此起草 60 章**最可能出现哪些结构性末态硬伤**。不改写、不补全、**不判文笔/taste**,只指出**结构性矛盾**且**必须引用 bible/plan 的具体路径或字段值**作证据。

类目**逐字**限定在这九个(predicted 原样用):境界乱序、修为倒退、性别错、混名/认亲矛盾、死人复活、章节复制/注水、DNA/身世互斥、人设崩、现代腔出戏。

**题材可解释例外**(不得当矛盾报):修真境界跨阶跳跃若设定已解释、重生/复活若有机制、女扮男装/变身/易容/化形、别名/化名、血缘秘密(养子女/调换)若是有意伏笔。finding 须排除"已被设定明确解释"的情形。

每条 finding:
{"category":"<九类之一>","severity":"hard|warn","evidence_path":"<bible/plan 的路径或字段值>","contradiction":"<具体矛盾一句>","confidence":"高|中|低"}
- severity=hard:闭类、带确凿证据的结构矛盾(亲属/血型/境界阶梯/重复章/时间线/身世互斥)。
- severity=warn:软风险(现代腔、软人设、可解释题材惯例)。
含糊、无 evidence_path 的 finding 不要输出。

**只输出一个 JSON 对象**:{"findings":[{...},...]}  (无风险则 findings 为空数组)
```

- [ ] **Step 2: 提交**

```bash
git add docs/superpowers/specs/predraft-review-prompt.md
git commit -m "docs(predraft): 冻结 LLM 预起草审核提示词"
```

---

### Task 4: predraft_tabulate — 校准(精度/召回 per reviewer×类目)

**Files:**
- Create: `scripts/predraft_tabulate.py`
- Test: `tests/test_predraft_tabulate.py`

**Interfaces:**
- Produces:
  - `REVIEWERS = ("det", "deepseek", "opus", "gpt55", "crossfamily")`
  - `load_predraft(vdir) -> dict`:读 `<vdir>/predraft/<slug>__<reviewer>.json`(每个 `{"findings":[{category,severity,...}]}`)→ `{slug: {reviewer: {"hard":set(类目), "all":set(类目)}}}`。
  - `precision_recall(predraft, observed) -> dict`:`observed` = `{slug: [类目]}`(实测,同 failure_labels)。**先合成 `crossfamily` reviewer = opus∪gpt55(per book,`_augment_crossfamily`)**,与 deepseek 同口径比 P/R。对每 (reviewer, 类目),在**该 reviewer 有数据的 book** 上算:tp=预测hard且实测, fp=预测hard未实测, fn=实测未预测hard;`precision=tp/(tp+fp)`,`recall=tp/(tp+fn)`(分母0→None)。返回 `{reviewer: {category: {"tp","fp","fn","precision","recall"}}}`(含 `crossfamily`)。空输入→`{}`。
  - `format_predraft_report(predraft, observed) -> str`:人读表 + DeepSeek-vs-跨族(opus∪gpt55)按类目精度/召回对比 + 诚实边界。
  - `main(argv)`:`<vdir> --labels labels.yaml`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_predraft_tabulate.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import predraft_tabulate as pt


def test_precision_recall_basic():
    # opus 对 b1 预测 hard {混名,境界}; 实测 {混名,性别错}
    predraft = {"b1": {"opus": {"hard": {"混名/认亲矛盾", "境界乱序"}, "all": {"混名/认亲矛盾", "境界乱序"}}}}
    observed = {"b1": ["混名/认亲矛盾", "性别错"]}
    pr = pt.precision_recall(predraft, observed)
    o = pr["opus"]
    # 混名: tp(预测+实测) ; 境界: fp(预测未实测) ; 性别错: fn(实测未预测)
    assert o["混名/认亲矛盾"]["tp"] == 1 and o["混名/认亲矛盾"]["precision"] == 1.0
    assert o["境界乱序"]["fp"] == 1 and o["境界乱序"]["precision"] == 0.0
    assert o["性别错"]["fn"] == 1 and o["性别错"]["recall"] == 0.0


def test_crossfamily_synthesized_precision_recall():
    # opus 预测 {混名}, gpt55 预测 {境界}; 实测 {混名,境界} → 跨族=opus∪gpt55 两者都 tp
    predraft = {"b1": {"opus": {"hard": {"混名/认亲矛盾"}, "all": {"混名/认亲矛盾"}},
                       "gpt55": {"hard": {"境界乱序"}, "all": {"境界乱序"}}}}
    observed = {"b1": ["混名/认亲矛盾", "境界乱序"]}
    pr = pt.precision_recall(predraft, observed)
    assert "crossfamily" in pr                       # 合成跨族 reviewer
    assert pr["crossfamily"]["混名/认亲矛盾"]["tp"] == 1
    assert pr["crossfamily"]["境界乱序"]["tp"] == 1


def test_precision_recall_no_data_safe():
    pr = pt.precision_recall({}, {})
    assert pr == {}                                  # 空不崩, 返回空 dict


def test_format_report_deepseek_vs_crossfamily_pr():
    # deepseek 漏报混名(实测有)→ R=0; 跨族(opus)报中 → R=1; 报告须含 P/R 对比行
    predraft = {"b1": {"opus": {"hard": {"混名/认亲矛盾"}, "all": {"混名/认亲矛盾"}},
                       "gpt55": {"hard": set(), "all": set()},
                       "deepseek": {"hard": set(), "all": set()}}}
    observed = {"b1": ["混名/认亲矛盾"]}
    out = pt.format_predraft_report(predraft, observed)
    assert "精度" in out and "诚实" in out
    assert "DeepSeek P=" in out and "跨族 P=" in out   # 真 P/R 对比(非仅命中数)
```

- [ ] **Step 2: 跑测试验证 fail**

Run: `python -m pytest tests/test_predraft_tabulate.py -q`
Expected: FAIL（`No module named predraft_tabulate`）

- [ ] **Step 3: 写实现**

```python
# scripts/predraft_tabulate.py
"""PreDraft Review v0 校准: 读 predraft findings + 实测标注 → 各 reviewer×类目 精度/召回。
不调 API。用法: python scripts/predraft_tabulate.py <vdir> --labels labels.yaml"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

REVIEWERS = ("det", "deepseek", "opus", "gpt55", "crossfamily")


def load_predraft(vdir) -> dict:
    vdir = Path(vdir); pdir = vdir / "predraft"
    out: dict = {}
    if not pdir.is_dir():
        return out
    for p in sorted(pdir.glob("*__*.json")):
        slug, reviewer = p.name[:-5].split("__", 1)
        try:
            findings = json.loads(p.read_text(encoding="utf-8")).get("findings") or []
        except (json.JSONDecodeError, OSError):
            continue
        hard = {f["category"] for f in findings if isinstance(f, dict) and f.get("severity") == "hard" and f.get("category")}
        allc = {f["category"] for f in findings if isinstance(f, dict) and f.get("category")}
        out.setdefault(slug, {})[reviewer] = {"hard": hard, "all": allc}
    return out


def _augment_crossfamily(predraft) -> dict:
    """合成 crossfamily reviewer = opus∪gpt55(per book),供与 deepseek 同口径比 P/R。"""
    out = {}
    for slug, byrev in predraft.items():
        byrev = dict(byrev)
        if "opus" in byrev or "gpt55" in byrev:
            byrev["crossfamily"] = {
                "hard": byrev.get("opus", {}).get("hard", set()) | byrev.get("gpt55", {}).get("hard", set()),
                "all": byrev.get("opus", {}).get("all", set()) | byrev.get("gpt55", {}).get("all", set())}
        out[slug] = byrev
    return out


def precision_recall(predraft, observed) -> dict:
    predraft = _augment_crossfamily(predraft)
    # 收集每 reviewer 出现过的类目
    res: dict = {}
    cats_by_rev: dict = {}
    for slug, byrev in predraft.items():
        for rev, d in byrev.items():
            cats_by_rev.setdefault(rev, set()).update(d["hard"])
            cats_by_rev[rev].update(observed.get(slug, []))
    for rev, cats in cats_by_rev.items():
        res[rev] = {}
        for cat in sorted(cats):
            tp = fp = fn = 0
            for slug, byrev in predraft.items():
                if rev not in byrev:
                    continue
                pred = cat in byrev[rev]["hard"]
                obs = cat in set(observed.get(slug, []))
                if pred and obs: tp += 1
                elif pred and not obs: fp += 1
                elif obs and not pred: fn += 1
            prec = tp / (tp + fp) if (tp + fp) else None
            rec = tp / (tp + fn) if (tp + fn) else None
            res[rev][cat] = {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec}
    return res


def format_predraft_report(predraft, observed) -> str:
    pr = precision_recall(predraft, observed)
    L = [f"=== PreDraft Review 校准 (books={len(predraft)}) ==="]
    for rev in REVIEWERS:
        if rev not in pr:
            continue
        L.append(f"[{rev}] 精度/召回 per 类目:")
        for cat, m in sorted(pr[rev].items(), key=lambda kv: -(kv[1]["tp"])):
            if m["tp"] + m["fp"] + m["fn"] == 0:
                continue
            L.append(f"  {cat}: P={m['precision']} R={m['recall']} (tp{m['tp']}/fp{m['fp']}/fn{m['fn']})")
    # DeepSeek 自审 vs 跨族(crossfamily=opus∪gpt55): 按类目 精度/召回 对比(spec 要召回/精度差)
    L.append("[DeepSeek 自审 vs 跨族(opus∪gpt55)] 各类目 精度/召回:")
    ds_pr = pr.get("deepseek", {})
    cf_pr = pr.get("crossfamily", {})
    for c in sorted(set(ds_pr) | set(cf_pr)):
        d = ds_pr.get(c, {}); f = cf_pr.get(c, {})
        L.append(f"  {c}: DeepSeek P={d.get('precision')}/R={d.get('recall')}  跨族 P={f.get('precision')}/R={f.get('recall')}")
    L.append("[诚实边界] n 小→方向非精度阈值; 精度量'预测末态兑现'非'纸面自洽'; hard 拦只认高置信。")
    return "\n".join(L)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("vdir")
    ap.add_argument("--labels", default=None)
    a = ap.parse_args(argv)
    observed = {}
    if a.labels and Path(a.labels).exists():
        import yaml
        observed = yaml.safe_load(Path(a.labels).read_text(encoding="utf-8")) or {}
    print(format_predraft_report(load_predraft(a.vdir), observed))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试验证 pass**

Run: `python -m pytest tests/test_predraft_tabulate.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add scripts/predraft_tabulate.py tests/test_predraft_tabulate.py
git commit -m "feat(predraft): 校准 tabulator(精度/召回 per reviewer×类目 + DeepSeek-vs-跨族)"
```

---

## 终检
- [ ] 全量 `python -m pytest -m 'not api'` 绿(报确切 passed/deselected)。
- [ ] predraft_checks 在真 bible(`output_archive/*/bible.json` 或 B 档产物)上 smoke 跑不崩。
- [ ] 全程不调 API、不改 produce.run/gate/冻结向量。

<!-- codex-peer-reviewed: 2026-06-30T14:35:42Z rounds=2 verdict=approved -->
