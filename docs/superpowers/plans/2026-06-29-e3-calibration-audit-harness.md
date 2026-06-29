# E3 Slice 1 — HFL 校准数据审计 + 对齐 harness 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一个只读纯模块 `src/hiki/calibration.py` + 审计脚本,审计 `assets/hfl.jsonl` 人评数据:出兼容性报告、假阳性透镜(门放行但编辑判承重<50)、溯源分歧审计(证当前 0 条可拟合对齐)。

**Architecture:** 6 个纯函数 + 1 frozen dataclass,全部 0 LLM / 0 网络 / 只读,不碰 pipeline/门/web/hfl 写入。`load_hfl` 解析+派生分类(fail-closed),三个分析函数(compat_report/false_accept_lens/provenance_divergence)各产结构化 dict,`format_report` 拼人读摘要,`scripts/calibration_audit.py` 是只读入口。

**Tech Stack:** Python 3,stdlib only(json/dataclasses/collections/pathlib);pytest;无新依赖。

配套 spec:`docs/superpowers/specs/2026-06-29-e3-calibration-audit-harness-design.md`(codex-approved rounds=2)。

## Global Constraints

- **纯/只读**:全模块 0 LLM、0 网络、只读文件;**不碰** pipeline / `gate` / web / `hfl.jsonl` 写入 / `/api/calibration`。
- **ground truth** = `scorer=="网文编辑"` → `truth_space=="editor"`;常量 `GROUND_TRUTH="editor"`。其余 scorer(fable/运营评委1/总编辑)各为独立真值空间,**不可混池**。
- **承重 floor** = `CHENGZHONG_FLOOR = 50`(可调,默认值)。
- **`LEGACY_TO_FROZEN`**(逐字,8 键):`代入感分→opening_immersion, 控制面重演→reenact_hits, 章缝检出→seam_detected, deliverable→deliverable, 暗黑比→dark_ratio, final_consistent→final_consistent, 过短章数→too_short_chapters, 章内双版本→intra_repeat_chapters`。
- **`n_provenance_matched` 结构性恒 0**:gold fixture 无 version/commit 溯源字段,**绝不**由 legacy 键巧合相等推断 matched(codex landmine:子集巧合会喂 Slice2 错位训练对)。
- **fail-closed**:畸形(非法 JSON / 非 dict)行进 `errors` 不进 `rows`,绝不当合法行流下去;缺特征绝不默认 0。
- **代码约定**:模块导入 `from hiki import calibration`;测试用 `from hiki import calibration`;`ROOT = Path(__file__).resolve().parents[1]`;一律 `encoding="utf-8"`;测试落 `tests/`。
- **脚本 PYTHONPATH**:repo root 下 `from hiki import ...` 会 `ModuleNotFoundError`(pyproject 仅给 pytest 加 src 到 pythonpath)→ 脚本须 `sys.path.insert(0, str(ROOT/"src"))` 再 import。
- **回归网**:`pytest tests/test_gold_regression.py tests/test_assembly_regression.py` 全程绿(本片无相交路径,应平凡通过)。
- **提交**:每个 commit 末尾附标准 trailer:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EoVNZMK1aq3D44jknQ18bq
  ```

---

### Task 1: HflRow + load_hfl(解析 + 派生分类 + fail-closed)

**Files:**
- Create: `src/hiki/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: 无(本片起点)。
- Produces:
  - 常量 `TRUTH_SPACE: dict`, `GROUND_TRUTH="editor"`, `STANDARD4: frozenset`, `STORY4: frozenset`, `CHENGZHONG_FLOOR=50`, `LEGACY_TO_FROZEN: dict`。
  - `@dataclass(frozen=True) class HflRow` 字段:`line_no:int, scorer:str, title:str|None, source:str|None, truth_space:str, dims:dict, dims_schema:str, total:float|None, slug:str|None, version:str|None, auto_signals:dict, signal_compat:str, deliverable:bool|None`。
  - `load_hfl(path) -> tuple[list[HflRow], list[dict]]`(errors 元素 = `{"line_no":int,"error":str,"raw":str}`)。

- [ ] **Step 1: 写失败测试**

`tests/test_calibration.py`:
```python
"""E3 Slice1 校准审计 harness 单测(合成 fixture, 不依赖真 assets)。"""
import json
from pathlib import Path

from hiki import calibration


def _write_jsonl(tmp_path, rows_and_blanks):
    p = tmp_path / "hfl.jsonl"
    p.write_text("\n".join(rows_and_blanks) + "\n", encoding="utf-8")
    return p


def test_load_hfl_parses_and_derives(tmp_path):
    lines = [
        json.dumps({"scorer": "网文编辑", "title": "甲", "slug": "S1", "version": "v1",
                    "dims": {"拉力": 60, "笔力": 70, "人": 60, "承重": 30},
                    "total": 56.5, "auto_signals": {"deliverable": True, "章缝检出": 29}}, ensure_ascii=False),
        json.dumps({"scorer": "运营评委1", "slug": "S2",
                    "dims": {"故事性": 85, "笔力": 90, "人": 80, "承重": 40},
                    "auto_signals": {"grade": "A"}}, ensure_ascii=False),
        json.dumps({"scorer": "fable", "source": "src", "version": "r7",
                    "dims": {"拉力": 70}, "auto_signals": {"schema_version": 1, "deliverable": False}}, ensure_ascii=False),
        json.dumps({"scorer": "总编辑", "title": "丁",
                    "dims": {"拉力": 70, "笔力": 80, "人": 65, "承重": 50},
                    "auto_signals": {"note": "report被覆盖"}}, ensure_ascii=False),
    ]
    rows, errors = calibration.load_hfl(_write_jsonl(tmp_path, lines))
    assert errors == []
    assert len(rows) == 4
    r0 = rows[0]
    assert r0.line_no == 1 and r0.truth_space == "editor" and r0.dims_schema == "standard4"
    assert r0.signal_compat == "legacy" and r0.deliverable is True and r0.title == "甲" and r0.total == 56.5
    assert rows[1].truth_space == "ops" and rows[1].dims_schema == "story4" and rows[1].signal_compat == "none"
    assert rows[2].truth_space == "proxy" and rows[2].signal_compat == "frozen" and rows[2].deliverable is False
    assert rows[3].truth_space == "chief_editor" and rows[3].signal_compat == "none" and rows[3].deliverable is None


def test_load_hfl_failclosed_and_blanks(tmp_path):
    lines = [
        "",  # 空行 → 跳过
        '{"scorer": "网文编辑", "dims": {}, "auto_signals": {}}',  # 合法但空 → none
        "{not valid json",  # 畸形 → errors
        "[1,2,3]",  # 合法 JSON 但非 dict → errors
    ]
    rows, errors = calibration.load_hfl(_write_jsonl(tmp_path, lines))
    assert len(rows) == 1 and rows[0].signal_compat == "none"
    assert {e["line_no"] for e in errors} == {3, 4}
    assert all("error" in e and "raw" in e for e in errors)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_calibration.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiki.calibration'` 或 `AttributeError`。

- [ ] **Step 3: 写最小实现**

`src/hiki/calibration.py`:
```python
"""E3 Slice1: HFL 校准数据审计 + 对齐 harness(纯函数, 0 LLM/0 网络/只读)。

见 docs/superpowers/specs/2026-06-29-e3-calibration-audit-harness-design.md。
只读 assets/hfl.jsonl + assets/gold_regression,产兼容性报告/假阳性透镜/溯源分歧审计。
不碰 pipeline/门/web/hfl 写入。门永不消费本模块(程序级影子)。
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TRUTH_SPACE = {"网文编辑": "editor", "fable": "proxy", "运营评委1": "ops", "总编辑": "chief_editor"}
GROUND_TRUTH = "editor"
STANDARD4 = frozenset({"拉力", "笔力", "人", "承重"})
STORY4 = frozenset({"故事性", "笔力", "人", "承重"})
CHENGZHONG_FLOOR = 50
# hfl 旧 auto_signals 键 → 冻结向量键(仅用于溯源分歧比对, 非建模)
LEGACY_TO_FROZEN = {
    "代入感分": "opening_immersion", "控制面重演": "reenact_hits",
    "章缝检出": "seam_detected", "deliverable": "deliverable",
    "暗黑比": "dark_ratio", "final_consistent": "final_consistent",
    "过短章数": "too_short_chapters", "章内双版本": "intra_repeat_chapters",
}


@dataclass(frozen=True)
class HflRow:
    line_no: int
    scorer: str
    title: str | None
    source: str | None
    truth_space: str          # editor/proxy/ops/chief_editor/unknown
    dims: dict
    dims_schema: str          # standard4 / story4 / other
    total: float | None
    slug: str | None
    version: str | None
    auto_signals: dict
    signal_compat: str        # frozen / legacy / none
    deliverable: bool | None


def _truth_space(scorer):
    return TRUTH_SPACE.get(scorer or "", "unknown")


def _dims_schema(dims):
    keys = frozenset((dims or {}).keys())
    if keys == STANDARD4:
        return "standard4"
    if keys == STORY4:
        return "story4"
    return "other"


def _signal_compat(auto):
    if not isinstance(auto, dict) or not auto:
        return "none"
    if "schema_version" in auto:
        return "frozen"
    if any(k in LEGACY_TO_FROZEN for k in auto):   # 有可映射旧键 → 可参与溯源比对
        return "legacy"
    return "none"                                  # 仅文字(note/era)或纯一次性键 → 建模无用


def load_hfl(path):
    """逐行解析 jsonl(跳空行)。畸形(非法JSON/非dict)行 fail-closed → errors, 不进 rows。
    每行派生 truth_space/dims_schema/signal_compat/deliverable。"""
    rows, errors = [], []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            raw = json.loads(s)
        except json.JSONDecodeError as e:
            errors.append({"line_no": i, "error": str(e), "raw": s[:200]})
            continue
        if not isinstance(raw, dict):
            errors.append({"line_no": i, "error": "not a JSON object", "raw": s[:200]})
            continue
        auto = raw.get("auto_signals")
        auto = auto if isinstance(auto, dict) else {}
        dims = raw.get("dims") if isinstance(raw.get("dims"), dict) else {}
        scorer = raw.get("scorer")
        total = raw.get("total")
        deliv = auto.get("deliverable")
        rows.append(HflRow(
            line_no=i, scorer=scorer or "",
            title=raw.get("title"), source=raw.get("source"),
            truth_space=_truth_space(scorer), dims=dims, dims_schema=_dims_schema(dims),
            total=total if isinstance(total, (int, float)) and not isinstance(total, bool) else None,
            slug=raw.get("slug"), version=raw.get("version"),
            auto_signals=auto, signal_compat=_signal_compat(auto),
            deliverable=deliv if isinstance(deliv, bool) else None,
        ))
    return rows, errors
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_calibration.py -q`
Expected: PASS(2 passed)。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/calibration.py tests/test_calibration.py
git commit -m "feat(calibration): HflRow + load_hfl 解析+派生分类(fail-closed)"
```
(commit 末尾附标准 trailer,见 Global Constraints。)

---

### Task 2: compat_report(兼容性分桶聚合)

**Files:**
- Modify: `src/hiki/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `load_hfl` 的 `rows`/`errors`(Task 1)。
- Produces: `compat_report(rows, errors) -> dict`,键:`n_rows, n_errors, n_ground_truth, by_truth_space(dict), buckets(dict[str,int])`;bucket key 格式 `"{truth_space}|{dims_schema}|{signal_compat}|{version}"`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_calibration.py`:
```python
def test_compat_report_counts(tmp_path):
    import json
    lines = [
        json.dumps({"scorer": "网文编辑", "slug": "A", "version": "v1",
                    "dims": {"拉力": 1, "笔力": 1, "人": 1, "承重": 1},
                    "auto_signals": {"deliverable": True}}, ensure_ascii=False),
        json.dumps({"scorer": "网文编辑", "slug": "B", "version": "v1",
                    "dims": {"拉力": 1, "笔力": 1, "人": 1, "承重": 1},
                    "auto_signals": {"deliverable": True}}, ensure_ascii=False),
        json.dumps({"scorer": "fable", "version": "r7", "dims": {},
                    "auto_signals": {"schema_version": 1}}, ensure_ascii=False),
    ]
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows, errors = calibration.load_hfl(p)
    rep = calibration.compat_report(rows, errors)
    assert rep["n_rows"] == 3 and rep["n_errors"] == 0 and rep["n_ground_truth"] == 2
    assert rep["by_truth_space"] == {"editor": 2, "proxy": 1}
    assert rep["buckets"]["editor|standard4|legacy|v1"] == 2
    assert rep["buckets"]["proxy|other|frozen|r7"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_calibration.py::test_compat_report_counts -q`
Expected: FAIL — `AttributeError: module 'hiki.calibration' has no attribute 'compat_report'`。

- [ ] **Step 3: 写最小实现**

追加到 `src/hiki/calibration.py`:
```python
def compat_report(rows, errors):
    """兼容性报告: 按 (truth_space, dims_schema, signal_compat, version) 分桶计数。纯聚合。"""
    buckets = Counter((r.truth_space, r.dims_schema, r.signal_compat, r.version) for r in rows)
    return {
        "n_rows": len(rows),
        "n_errors": len(errors),
        "n_ground_truth": sum(1 for r in rows if r.truth_space == GROUND_TRUTH),
        "by_truth_space": dict(Counter(r.truth_space for r in rows)),
        "buckets": {
            f"{ts}|{ds}|{sc}|{ver}": n
            for (ts, ds, sc, ver), n in sorted(buckets.items(), key=lambda kv: (-kv[1], str(kv[0])))
        },
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_calibration.py -q`
Expected: PASS(3 passed)。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/calibration.py tests/test_calibration.py
git commit -m "feat(calibration): compat_report 兼容性分桶聚合"
```

---

### Task 3: false_accept_lens(假阳性透镜)

**Files:**
- Modify: `src/hiki/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `load_hfl` rows(Task 1)。
- Produces: `false_accept_lens(rows, floor=CHENGZHONG_FLOOR) -> dict`,键:`flagged(list[dict{slug,title,承重,total,version,auto_signals}]), n_editor_with_deliverable(int), rate(float), floor(int)`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_calibration.py`:
```python
def _editor_row(slug, cz, deliv, total=60.0):
    import json
    return json.dumps({"scorer": "网文编辑", "slug": slug, "title": f"T-{slug}", "version": "v1",
                       "dims": {"拉力": 60, "笔力": 60, "人": 60, "承重": cz},
                       "total": total, "auto_signals": {"deliverable": deliv}}, ensure_ascii=False)


def test_false_accept_lens(tmp_path):
    import json
    lines = [
        _editor_row("LOW", 30, True),        # 命中: deliverable=True ∧ 承重<50
        _editor_row("EDGE", 50, True),       # 不命中: 50 不 <50
        _editor_row("HIGH", 70, True),       # 不命中: 承重≥floor
        _editor_row("REJECT", 20, False),    # 不命中: deliverable=False
        json.dumps({"scorer": "fable", "slug": "PX", "dims": {"承重": 10},
                    "auto_signals": {"deliverable": True}}, ensure_ascii=False),  # 非 editor 不计入
    ]
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows, _ = calibration.load_hfl(p)
    fa = calibration.false_accept_lens(rows)
    assert fa["floor"] == 50
    assert fa["n_editor_with_deliverable"] == 4          # 4 个 editor 带 deliverable(PX 是 fable)
    assert [f["slug"] for f in fa["flagged"]] == ["LOW"]
    assert fa["flagged"][0]["title"] == "T-LOW" and fa["flagged"][0]["承重"] == 30
    assert abs(fa["rate"] - 0.25) < 1e-9

    fa70 = calibration.false_accept_lens(rows, floor=70)
    assert {f["slug"] for f in fa70["flagged"]} == {"LOW", "EDGE"}  # 70 下 30/50 均命中
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_calibration.py::test_false_accept_lens -q`
Expected: FAIL — `AttributeError: ... 'false_accept_lens'`。

- [ ] **Step 3: 写最小实现**

追加到 `src/hiki/calibration.py`:
```python
def false_accept_lens(rows, floor=CHENGZHONG_FLOOR):
    """ground-truth(editor)行中 deliverable==True ∧ 承重<floor → 假阳性候选。
    仅看 hfl 行自身 deliverable, 不依赖 gold。"""
    editors = [r for r in rows if r.truth_space == GROUND_TRUTH and r.deliverable is not None]
    flagged = []
    for r in editors:
        cz = r.dims.get("承重")
        if r.deliverable is True and isinstance(cz, (int, float)) and not isinstance(cz, bool) and cz < floor:
            flagged.append({"slug": r.slug, "title": r.title, "承重": cz,
                            "total": r.total, "version": r.version, "auto_signals": r.auto_signals})
    n = len(editors)
    return {"flagged": flagged, "n_editor_with_deliverable": n,
            "rate": (len(flagged) / n) if n else 0.0, "floor": floor}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_calibration.py -q`
Expected: PASS(4 passed)。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/calibration.py tests/test_calibration.py
git commit -m "feat(calibration): false_accept_lens 假阳性透镜(editor deliverable=true∧承重<50)"
```

---

### Task 4: load_gold_signal_vectors + provenance_divergence(溯源分歧审计)

**Files:**
- Modify: `src/hiki/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `load_hfl` rows(Task 1);`LEGACY_TO_FROZEN`/`GROUND_TRUTH`(Task 1)。
- Produces:
  - `load_gold_signal_vectors(gold_dir) -> dict[str, dict]`(slug → fixture["signals"])。
  - `provenance_divergence(rows, gold_vectors) -> dict`,键:`books(list[dict{slug,shared_keys,diffs,status}]), n_overlap, n_divergent, n_inconclusive, n_provenance_matched`;status ∈ {"divergent","inconclusive"};`n_provenance_matched` 恒 0。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_calibration.py`:
```python
def test_load_gold_signal_vectors(tmp_path):
    import json
    (tmp_path / "S1").mkdir()
    (tmp_path / "S1" / "fixture.json").write_text(
        json.dumps({"slug": "S1", "signals": {"deliverable": True, "seam_detected": 25}}), encoding="utf-8")
    (tmp_path / "S2").mkdir()
    (tmp_path / "S2" / "fixture.json").write_text(
        json.dumps({"slug": "S2", "signals": {"deliverable": False}}), encoding="utf-8")
    gv = calibration.load_gold_signal_vectors(tmp_path)
    assert set(gv) == {"S1", "S2"} and gv["S1"]["seam_detected"] == 25


def test_provenance_divergence_classifies(tmp_path):
    import json
    # gold 冻结向量(直接构造,不落盘)
    gold = {
        "DIV": {"deliverable": False, "seam_detected": 25, "dark_ratio": 0.07},
        "INC": {"deliverable": True, "seam_detected": 29},
        "NOGOLD_IGNORED": {"deliverable": True},
    }
    lines = [
        # DIV: 共享 deliverable(True vs False)+ seam(29 vs 25) → divergent
        json.dumps({"scorer": "网文编辑", "slug": "DIV", "dims": {"承重": 30},
                    "auto_signals": {"deliverable": True, "章缝检出": 29, "暗黑比": 0.07}}, ensure_ascii=False),
        # INC: 共享 deliverable(True==True)+ seam(29==29),全等且无溯源 → inconclusive
        json.dumps({"scorer": "网文编辑", "slug": "INC", "dims": {"承重": 70},
                    "auto_signals": {"deliverable": True, "章缝检出": 29}}, ensure_ascii=False),
        # slug 不在 gold → 不入 overlap
        json.dumps({"scorer": "网文编辑", "slug": "MISSING", "dims": {"承重": 60},
                    "auto_signals": {"deliverable": True}}, ensure_ascii=False),
        # 非 editor → 不入 overlap
        json.dumps({"scorer": "fable", "slug": "DIV", "dims": {"承重": 50},
                    "auto_signals": {"deliverable": False}}, ensure_ascii=False),
    ]
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows, _ = calibration.load_hfl(p)
    prov = calibration.provenance_divergence(rows, gold)
    assert prov["n_overlap"] == 2 and prov["n_divergent"] == 1 and prov["n_inconclusive"] == 1
    assert prov["n_provenance_matched"] == 0
    by = {b["slug"]: b for b in prov["books"]}
    assert by["DIV"]["status"] == "divergent"
    assert "deliverable" in by["DIV"]["diffs"] and "seam_detected" in by["DIV"]["diffs"]
    assert by["INC"]["status"] == "inconclusive" and by["INC"]["diffs"] == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_calibration.py::test_provenance_divergence_classifies -q`
Expected: FAIL — `AttributeError: ... 'provenance_divergence'`。

- [ ] **Step 3: 写最小实现**

追加到 `src/hiki/calibration.py`:
```python
def load_gold_signal_vectors(gold_dir):
    """slug -> fixture['signals'](冻结向量)。只读 <gold_dir>/<slug>/fixture.json。"""
    out = {}
    for fx in sorted(Path(gold_dir).glob("*/fixture.json")):
        data = json.loads(fx.read_text(encoding="utf-8"))
        sigs = data.get("signals")
        if isinstance(sigs, dict):
            out[fx.parent.name] = sigs
    return out


def _comparable(a, b):
    """两值是否类型可比: bool 仅与 bool 比; 数值(非bool)互比; 其余不可比。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool)
    return isinstance(a, (int, float)) and isinstance(b, (int, float))


def provenance_divergence(rows, gold_vectors):
    """editor∩slug∩gold 的书: hfl auto_signals 经 LEGACY_TO_FROZEN 映射后逐可比较共享键比 gold。
    divergent=任一键不等(证不同次跑); inconclusive=全等但 gold 无溯源字段(不算 matched)。
    n_provenance_matched 结构性恒 0(gold 无溯源元数据, 绝不由 legacy 巧合相等推断)。"""
    books, n_div, n_inc = [], 0, 0
    for r in rows:
        if r.truth_space != GROUND_TRUTH or not r.slug or r.slug not in gold_vectors:
            continue
        gv = gold_vectors[r.slug]
        mapped = {LEGACY_TO_FROZEN[k]: v for k, v in r.auto_signals.items() if k in LEGACY_TO_FROZEN}
        shared = [k for k in sorted(set(mapped) & set(gv)) if _comparable(mapped[k], gv[k])]
        diffs = {k: [mapped[k], gv[k]] for k in shared if mapped[k] != gv[k]}
        status = "divergent" if diffs else "inconclusive"
        n_div += status == "divergent"
        n_inc += status == "inconclusive"
        books.append({"slug": r.slug, "shared_keys": shared, "diffs": diffs, "status": status})
    return {"books": books, "n_overlap": len(books), "n_divergent": n_div,
            "n_inconclusive": n_inc, "n_provenance_matched": 0}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_calibration.py -q`
Expected: PASS(6 passed)。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/calibration.py tests/test_calibration.py
git commit -m "feat(calibration): gold 向量加载 + provenance_divergence(divergent/inconclusive, matched恒0)"
```

---

### Task 5: format_report + 只读审计脚本

**Files:**
- Modify: `src/hiki/calibration.py`
- Create: `scripts/calibration_audit.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `compat_report`/`false_accept_lens`/`provenance_divergence` 的返回 dict(Tasks 2-4)。
- Produces: `format_report(compat, fa, prov) -> str`(纯字符串,无副作用)。脚本 `scripts/calibration_audit.py` 提供 `main()` 入口。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_calibration.py`:
```python
def test_format_report_is_pure_string():
    compat = {"n_rows": 3, "n_errors": 1, "n_ground_truth": 2,
              "by_truth_space": {"editor": 2, "proxy": 1},
              "buckets": {"editor|standard4|legacy|v1": 2, "proxy|other|frozen|r7": 1}}
    fa = {"flagged": [{"slug": "LOW", "title": "甲", "承重": 30, "total": 56.5, "version": "v1",
                       "auto_signals": {}}],
          "n_editor_with_deliverable": 2, "rate": 0.5, "floor": 50}
    prov = {"books": [{"slug": "DIV", "shared_keys": ["seam_detected"],
                       "diffs": {"seam_detected": [29, 25]}, "status": "divergent"}],
            "n_overlap": 1, "n_divergent": 1, "n_inconclusive": 0, "n_provenance_matched": 0}
    out = calibration.format_report(compat, fa, prov)
    assert isinstance(out, str)
    assert "LOW" in out and "承重=30" in out
    assert "divergent" in out and "DIV" in out
    assert "0 条可拟合对齐" in out          # matched==0 → 结论行
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_calibration.py::test_format_report_is_pure_string -q`
Expected: FAIL — `AttributeError: ... 'format_report'`。

- [ ] **Step 3: 写最小实现**

追加到 `src/hiki/calibration.py`:
```python
def format_report(compat, fa, prov):
    """三段人读摘要(纯字符串, 供脚本打印)。"""
    L = []
    L.append("=== HFL 校准数据审计 (E3 Slice1) ===")
    L.append(f"总行 {compat['n_rows']} | 解析错误 {compat['n_errors']} | ground-truth(editor) {compat['n_ground_truth']}")
    L.append("truth_space: " + ", ".join(f"{k}={v}" for k, v in sorted(compat["by_truth_space"].items())))
    L.append("兼容性桶 (truth_space|dims|signal|version):")
    for k, v in compat["buckets"].items():
        L.append(f"  {v:3d}  {k}")
    L.append("")
    L.append(f"=== 假阳性透镜 (editor: deliverable=True ∧ 承重<{fa['floor']}) ===")
    L.append(f"editor 带 deliverable {fa['n_editor_with_deliverable']} | 命中 {len(fa['flagged'])} | 分歧率 {fa['rate']:.0%}")
    for f in fa["flagged"]:
        L.append(f"  ⚠ {f['slug']} 「{f['title']}」 承重={f['承重']} total={f['total']} (v={f['version']})")
    L.append("")
    L.append("=== 溯源分歧审计 (editor ∩ gold by slug) ===")
    L.append(f"重叠 {prov['n_overlap']} | divergent {prov['n_divergent']} | "
             f"inconclusive {prov['n_inconclusive']} | provenance_matched {prov['n_provenance_matched']}")
    for b in prov["books"]:
        L.append(f"  {b['status']:12s} {b['slug']}  diffs={b['diffs']}")
    L.append("")
    if prov["n_provenance_matched"] == 0:
        L.append("结论: 0 条可拟合对齐 → Slice1b(评分时落冻结 report['signals']+scorer) 是 Slice2 建模硬前置。")
    else:
        L.append(f"结论: {prov['n_provenance_matched']} 条 provenance-matched 对齐可用。")
    return "\n".join(L)
```

`scripts/calibration_audit.py`:
```python
"""E3 Slice1 只读审计入口: 打印 HFL 兼容性/假阳性/溯源分歧报告。零写入。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 报告含中文 + ⚠/∧/→ 等非 GBK 符号; Windows 控制台默认 GBK 编码会 UnicodeEncodeError
# (codex 实证 print('⚠') 即崩) → 强制 UTF-8 stdout。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from hiki import calibration  # noqa: E402


def main():
    rows, errors = calibration.load_hfl(ROOT / "assets" / "hfl.jsonl")
    gold = calibration.load_gold_signal_vectors(ROOT / "assets" / "gold_regression")
    compat = calibration.compat_report(rows, errors)
    fa = calibration.false_accept_lens(rows)
    prov = calibration.provenance_divergence(rows, gold)
    print(calibration.format_report(compat, fa, prov))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试 + 手验脚本**

Run: `python -m pytest tests/test_calibration.py -q`
Expected: PASS(7 passed)。

Run: `python scripts/calibration_audit.py`
Expected: UTF-8 stdout 下正常打印三段报告(无 UnicodeEncodeError);末行含「0 条可拟合对齐」;假阳性段列出 BPBXS00052/CPBXN00188/CPBXN00233/ZYGGY02079/ZYGGY03052。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/calibration.py scripts/calibration_audit.py tests/test_calibration.py
git commit -m "feat(calibration): format_report + 只读审计脚本 calibration_audit.py"
```

---

### Task 6: 真数据不变量 smoke 测试

**Files:**
- Create: `tests/test_calibration_realdata.py`

**Interfaces:**
- Consumes: 全部 Task 1-5 函数 + 真 `assets/hfl.jsonl` + `assets/gold_regression`。
- Produces: 无(纯断言)。

**说明:** 这是 characterization 测试,钉死**当前** hfl 快照(60 行)的审计事实。hfl 增长时这些精确计数需有意识更新——这正是 characterization 的用途(强制人复核新数据)。

- [ ] **Step 1: 写测试(直接对真数据)**

`tests/test_calibration_realdata.py`:
```python
"""E3 Slice1 真数据不变量 smoke: 对真 assets/hfl.jsonl + gold_regression。
characterization 性质: 钉当前快照(hfl=60行); hfl 增长时更新计数。"""
from pathlib import Path

from hiki import calibration

ROOT = Path(__file__).resolve().parents[1]
HFL = ROOT / "assets" / "hfl.jsonl"
GOLD = ROOT / "assets" / "gold_regression"


def test_realdata_structure_and_snapshot():
    rows, errors = calibration.load_hfl(HFL)
    # 结构不变量(对数据增长稳健)
    assert errors == [], f"hfl 有解析错误行: {errors}"
    assert all(r.truth_space == "editor" for r in rows if r.scorer == "网文编辑")
    # 当前快照(hfl=60 行; 增长时更新以下精确值)
    assert len(rows) == 60
    compat = calibration.compat_report(rows, errors)
    assert compat["n_ground_truth"] == 14
    assert compat["by_truth_space"]["editor"] == 14

    fa = calibration.false_accept_lens(rows)
    assert fa["n_editor_with_deliverable"] == 14
    assert {f["slug"] for f in fa["flagged"]} == {
        "BPBXS00052", "CPBXN00188", "CPBXN00233", "ZYGGY02079", "ZYGGY03052"}

    gold = calibration.load_gold_signal_vectors(GOLD)
    prov = calibration.provenance_divergence(rows, gold)
    assert prov["n_overlap"] == 5
    assert prov["n_divergent"] == 5
    assert prov["n_inconclusive"] == 0
    assert prov["n_provenance_matched"] == 0   # 核心发现: 0 可拟合对齐

    # format_report 不崩且给结论
    out = calibration.format_report(compat, fa, prov)
    assert "0 条可拟合对齐" in out
```

- [ ] **Step 2: 跑测试**

Run: `python -m pytest tests/test_calibration_realdata.py -q`
Expected: PASS(1 passed)。若某精确计数不符,**先核对真数据**(可能 hfl 已增长)再决定改测试还是修代码——不要盲改断言。

- [ ] **Step 3: 跑全量 + 回归网确认无回归**

Run: `python -m pytest tests/test_calibration.py tests/test_calibration_realdata.py tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全 PASS(回归网平凡绿——本片无相交路径)。

Run: `python -m pytest -m "not api" -q`
Expected: 全绿;报确切 passed/deselected 数。

- [ ] **Step 4: 提交**

```bash
git add tests/test_calibration_realdata.py
git commit -m "test(calibration): 真数据不变量 smoke(快照: 60行/14editor/5假阳性/5divergent/0matched)"
```

---

## Self-Review

**1. Spec coverage:**
- 兼容性报告 → Task 2 ✅;假阳性透镜 → Task 3 ✅;溯源分歧审计 → Task 4 ✅;`load_hfl` fail-closed + 派生分类 → Task 1 ✅;gold 加载 → Task 4 ✅;`format_report` + 脚本 → Task 5 ✅;纯函数单测 → Tasks 1-5 ✅;真数据 smoke → Task 6 ✅;金标/装配网绿 → Task 6 Step 3 ✅。
- 非目标(不建模/不碰门/web/hfl写入/不混池/不盲配)→ 全计划无任何相关改动,Global Constraints 显式约束 ✅。

**2. Placeholder scan:** 无 TBD/TODO;每个 code step 有完整代码;commit 命令具体。✅

**3. Type consistency:** `HflRow` 字段名(Task1)在 Tasks 2-6 一致使用(`truth_space/dims/slug/auto_signals/deliverable/title`);`load_hfl` 返回 `(rows, errors)` tuple 在 Task2/6 一致解包;`provenance_divergence` 的 `n_provenance_matched` 键在 Task4 定义、Task5 format_report / Task6 断言一致引用;`false_accept_lens` 的 `flagged[].slug/title/承重` 在 Task3 定义、Task5/6 一致。✅

<!-- codex-peer-reviewed: 2026-06-29T09:55:50Z rounds=2 verdict=approved -->
