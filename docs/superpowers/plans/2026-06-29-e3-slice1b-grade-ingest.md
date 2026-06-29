# E3 Slice 1b — 人评回流落冻结信号(grade-ingest 升级)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让人评回流(`scripts/hfl_ingest.py`)产出的 hfl 行内联携带该书的冻结 `report["signals"]`(→ `signal_compat=="frozen"`、可拟合),并给 `report.json` 加引擎 commit 溯源,纯逻辑收进 `calibration.py`。

**Architecture:** 三处改动:(1) `produce.py` 加 best-effort `engine_commit` top-level 字段;(2) `calibration.py` 加纯构造/校验助手(rubric 权重/总分、signals_hash、build_hfl_row、幂等键);(3) `hfl_ingest.py` 重写为调用这些助手 + frozen-emit + 幂等 + standard4 严校。全程不碰门/web/建模。

**Tech Stack:** Python 3,stdlib(json/hashlib/subprocess/datetime/pathlib)+ PyYAML(脚本已用);pytest;无新依赖。

配套 spec:`docs/superpowers/specs/2026-06-29-e3-slice1b-grade-ingest-design.md`(codex-approved rounds=2)。

## Global Constraints

- **ground truth** = `scorer` 经 `_truth_space` 映射 == `"editor"`(即 `网文编辑`),dims = standard4 `{拉力,笔力,人,承重}`。其余真值空间不混池。
- **`engine_commit` 严格 top-level**,**绝不**进 `report["signals"]`(否则破金标/装配网冻结向量等价)。
- **`auto_signals` 逐字 = `report["signals"]`**(含 `schema_version` → Slice1 `_signal_compat` 判 `frozen`)。
- **`RUBRIC_WEIGHTS` 单源**(逐字):`standard4={拉力:0.30,笔力:0.25,人:0.25,承重:0.20}`,`story4={故事性:0.30,笔力:0.25,人:0.25,承重:0.20}`。`total` 派生自 dims,非手填。
- **幂等键(对 RAW JSON 行,非 HflRow)**:`(scorer, slug, round, signals_hash(auto_signals))`。
- **fail-closed**:校验失败/缺 report.json 的行 → 跳过 + stderr 浮现,绝不静默写半行;`build_hfl_row` 校验失败 raise `ValueError`。
- **best-effort git**:`_engine_commit` 全 except → `"unknown"`,绝不阻塞/失败 report 写盘。
- **calibration.py 纯/无 I/O**:行构造/校验在此;文件 append 由 CLI(`hfl_ingest.py`)持有。
- **代码约定**:模块/测试 `from hiki import calibration`;`encoding="utf-8"`;测试落 `tests/`;脚本 repo-root 运行须 `sys.path.insert(0, .../src)`。
- **回归网**:`pytest tests/test_gold_regression.py tests/test_assembly_regression.py` 全程绿(读 `report["signals"]` 子 dict / fact_table 计数,top-level 新键无关)。
- **不碰**:`/api/calibration`、web、门决策、建模、scorecard YAML 格式、老 60 行 hfl、`append_hfl_rX.py`。
- **提交**:每 commit 末尾附标准 trailer:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EoVNZMK1aq3D44jknQ18bq
  ```

---

### Task 1: `produce.py` — engine_commit 溯源(additive top-level)

**Files:**
- Modify: `src/hiki/produce.py`(import 块加 `subprocess`;加 `_engine_commit()`;run() 在 `report["signals"]=...` 后设 `report["engine_commit"]`)
- Test: `tests/test_produce_engine_commit.py`

**Interfaces:**
- Consumes: 无。
- Produces: `produce._engine_commit() -> str`(best-effort git HEAD,失败 `"unknown"`);run() 产出的 `report` 多一个 top-level 键 `engine_commit`。

- [ ] **Step 1: 写失败测试**

`tests/test_produce_engine_commit.py`:
```python
"""E3 Slice1b: produce._engine_commit best-effort + signals 不含 engine_commit。"""
import subprocess
from hiki import produce, signals


def test_engine_commit_success(monkeypatch):
    monkeypatch.setattr(produce.subprocess, "check_output", lambda *a, **k: b"abc123def456\n")
    assert produce._engine_commit() == "abc123def456"


def test_engine_commit_failure_returns_unknown(monkeypatch):
    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "git")
    monkeypatch.setattr(produce.subprocess, "check_output", boom)
    assert produce._engine_commit() == "unknown"


def test_signal_vector_never_carries_engine_commit():
    sv = signals.build_signal_vector(
        deliverable=True, grade="A", immersion_score=80, reenact_hits=0,
        seam_detected=1, seam_residual=0, dark_ratio=0.0, spine_num_contra=0,
        spine_id_contra=0, ft_revival_residual=0, too_short_chapters=0,
        final_consistent=True, intra_repeat_chapters=0)
    assert "engine_commit" not in sv   # 溯源必须 top-level, 绝不进冻结向量
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_produce_engine_commit.py -q`
Expected: FAIL — `AttributeError: module 'hiki.produce' has no attribute '_engine_commit'`(第三个测应已 PASS,因 build_signal_vector 本就不含该键)。

- [ ] **Step 3: 写实现**

在 `src/hiki/produce.py` 顶部 stdlib import 块(`import os` 一带)加:
```python
import subprocess
```
在模块级(任意顶层函数旁,如 `_variety` 附近)加:
```python
def _engine_commit() -> str:
    """本次跑的引擎 git commit(供信号溯源)。best-effort: 失败→'unknown', 绝不阻塞 report 写盘。"""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except Exception:
        return "unknown"
```
在 run() 中,紧接 `report["signals"] = signals.build_signal_vector(... early_repeat=early_rep["count"])` 那个赋值块**之后**、`# title/output/craft 字段...` 注释**之前**(现 `src/hiki/produce.py:1515`-`1516` 之间)插入:
```python
    report["engine_commit"] = _engine_commit()   # 本次跑引擎 commit, 供信号溯源(top-level, 不进 signals)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_produce_engine_commit.py -q`
Expected: PASS(3 passed)。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/produce.py tests/test_produce_engine_commit.py
git commit -m "feat(produce): report 加 engine_commit 溯源(top-level, best-effort, 不进 signals)"
```
(附标准 trailer。)

---

### Task 2: `calibration.py` — rubric 权重/总分 + signals_hash(纯)

**Files:**
- Modify: `src/hiki/calibration.py`(加 `import hashlib`;`RUBRIC_WEIGHTS`/`rubric_total`/`signals_hash`;更新模块 docstring)
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: 无(纯新增)。
- Produces: `RUBRIC_WEIGHTS: dict[str,dict]`;`rubric_total(dims, schema) -> float`;`signals_hash(signals) -> str`(16-hex)。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_calibration.py`:
```python
def test_rubric_total_standard4_and_story4():
    # standard4: .30*60+.25*70+.25*60+.20*30 = 56.5 (对齐 hfl 行 47 极品全能小村医)
    assert calibration.rubric_total({"拉力": 60, "笔力": 70, "人": 60, "承重": 30}, "standard4") == 56.5
    # story4: 同权重不同 slot-1 标签
    assert calibration.rubric_total({"故事性": 80, "笔力": 60, "人": 60, "承重": 40}, "story4") == 62.0


def test_signals_hash_stable_orderless_sensitive():
    a = {"schema_version": 1, "deliverable": True, "seam_detected": 25}
    b = {"seam_detected": 25, "deliverable": True, "schema_version": 1}  # 乱序
    assert calibration.signals_hash(a) == calibration.signals_hash(b)    # 键序无关
    assert len(calibration.signals_hash(a)) == 16
    c = {"schema_version": 1, "deliverable": True, "seam_detected": 26}  # 改一值
    assert calibration.signals_hash(a) != calibration.signals_hash(c)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_calibration.py::test_rubric_total_standard4_and_story4 tests/test_calibration.py::test_signals_hash_stable_orderless_sensitive -q`
Expected: FAIL — `AttributeError: ... 'rubric_total'`。

- [ ] **Step 3: 写实现**

在 `src/hiki/calibration.py`:把模块 docstring 末句由"只读"改述为"读/分类 + 行构造/校验(全纯, 无 I/O; 文件写入由 CLI 持有)"。import 块加:
```python
import hashlib
```
在常量区(`LEGACY_TO_FROZEN` 之后)加:
```python
# rubric 权重(单源; slot-1=.30: 拉力(editor standard4)/故事性(ops story4) 同槽不同标签)
RUBRIC_WEIGHTS = {
    "standard4": {"拉力": 0.30, "笔力": 0.25, "人": 0.25, "承重": 0.20},
    "story4":    {"故事性": 0.30, "笔力": 0.25, "人": 0.25, "承重": 0.20},
}
```
在文件末尾(`format_report` 之后)加两个纯函数:
```python
def rubric_total(dims, schema):
    """按 schema 权重算加权总分(四维须全 present 且数值)。schema∈RUBRIC_WEIGHTS。"""
    w = RUBRIC_WEIGHTS[schema]
    return round(sum(float(dims[d]) * wt for d, wt in w.items()), 2)


def signals_hash(signals):
    """冻结信号向量稳定指纹(json canonical, sort_keys)→ 幂等去重键之一。"""
    blob = json.dumps(signals, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_calibration.py -q`
Expected: PASS(全部 calibration 测,新增 2 个绿)。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/calibration.py tests/test_calibration.py
git commit -m "feat(calibration): RUBRIC_WEIGHTS + rubric_total + signals_hash(纯)"
```

---

### Task 3: `calibration.py` — build_hfl_row + 幂等键(纯)

**Files:**
- Modify: `src/hiki/calibration.py`(加 `build_hfl_row`/`hfl_dup_key`/`find_duplicate`)
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `_truth_space`/`_dims_schema`/`GROUND_TRUTH`/`RUBRIC_WEIGHTS`/`rubric_total`/`signals_hash`(Tasks 1-2 + Slice1)。
- Produces:
  - `build_hfl_row(*, scorer, slug, dims, comments, report, round_, output_dir, ingested_at, date=None) -> dict`(校验失败 raise `ValueError`)。
  - `hfl_dup_key(raw: dict) -> tuple`;`find_duplicate(existing_raw_rows: list[dict], new_row: dict) -> bool`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_calibration.py`:
```python
def _mk_report(signals=None, **extra):
    rep = {"title": "T", "source": "SRC", "engine_commit": "deadbeef"}
    rep["signals"] = signals if signals is not None else {
        "schema_version": 1, "deliverable": True, "seam_detected": 25}
    rep.update(extra)
    return rep


def test_build_hfl_row_happy_frozen_roundtrip(tmp_path):
    rep = _mk_report()
    row = calibration.build_hfl_row(
        scorer="网文编辑", slug="S1", dims={"拉力": 60, "笔力": 70, "人": 60, "承重": 30},
        comments="c", report=rep, round_="editor-eval-3", output_dir=str(tmp_path / "S1"),
        ingested_at="2026-06-29T00:00:00Z", date="2026-06-29")
    assert row["auto_signals"] == rep["signals"]          # 逐字内联冻结向量
    assert row["total"] == 56.5                            # 派生
    assert row["engine_commit"] == "deadbeef" and row["version"] == "deadbeef"
    assert row["signals_hash"] == calibration.signals_hash(rep["signals"])
    assert row["output_dir"] == str(tmp_path / "S1") and row["date"] == "2026-06-29"
    # 经 load_hfl 往返 → signal_compat=="frozen"
    import json
    p = tmp_path / "h.jsonl"
    p.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    rows, errs = calibration.load_hfl(p)
    assert errs == [] and rows[0].signal_compat == "frozen" and rows[0].truth_space == "editor"


def test_build_hfl_row_rejects_story4_for_editor():
    import pytest
    with pytest.raises(ValueError):
        calibration.build_hfl_row(
            scorer="网文编辑", slug="S", dims={"故事性": 80, "笔力": 60, "人": 60, "承重": 40},
            comments="", report=_mk_report(), round_="r", output_dir="d", ingested_at="t")


def test_build_hfl_row_rejects_bad_dims_and_missing_signals():
    import pytest
    rep = _mk_report()
    for bad in ({"拉力": 60, "笔力": 70, "人": 60, "承重": 130},      # >100
                {"拉力": 60, "笔力": 70, "人": 60, "承重": True},      # bool
                {"拉力": 60, "笔力": 70, "人": 60, "承重": "x"}):       # 非数值
        with pytest.raises(ValueError):
            calibration.build_hfl_row(scorer="网文编辑", slug="S", dims=bad, comments="",
                                      report=rep, round_="r", output_dir="d", ingested_at="t")
    # report 缺合法 signals
    with pytest.raises(ValueError):
        calibration.build_hfl_row(scorer="网文编辑", slug="S",
                                  dims={"拉力": 60, "笔力": 70, "人": 60, "承重": 30}, comments="",
                                  report={"signals": {"deliverable": True}},  # 无 schema_version
                                  round_="r", output_dir="d", ingested_at="t")


def test_build_hfl_row_unknown_commit_when_report_lacks_it():
    rep = _mk_report()
    del rep["engine_commit"]
    row = calibration.build_hfl_row(scorer="网文编辑", slug="S",
                                    dims={"拉力": 60, "笔力": 70, "人": 60, "承重": 30}, comments="",
                                    report=rep, round_="r", output_dir="d", ingested_at="t")
    assert row["engine_commit"] == "unknown" and row["version"] == "unknown"


def test_dup_key_over_raw_rows():
    base = {"scorer": "网文编辑", "slug": "S1", "round": "r1",
            "auto_signals": {"schema_version": 1, "seam_detected": 25}}
    same = dict(base)
    rerun = {**base, "auto_signals": {"schema_version": 1, "seam_detected": 26}}  # 重跑→signals 变
    assert calibration.find_duplicate([base], same) is True
    assert calibration.find_duplicate([base], rerun) is False   # 重跑不判重
    # 缺 auto_signals → 空 dict 指纹(稳定, 不崩)
    assert calibration.hfl_dup_key({"scorer": "x"})[3] == calibration.signals_hash({})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_calibration.py -k "build_hfl_row or dup_key" -q`
Expected: FAIL — `AttributeError: ... 'build_hfl_row'`。

- [ ] **Step 3: 写实现**

在 `src/hiki/calibration.py` 末尾加:
```python
def build_hfl_row(*, scorer, slug, dims, comments, report, round_, output_dir,
                  ingested_at, date=None):
    """构造 schema-正确的 hfl 行: auto_signals 逐字 = report['signals'](→ frozen)。纯; 校验失败 ValueError。
    output_dir 由调用方显式传(读 report.json 的 slug 目录, str)。ingested_at 调用方注入(不取时钟)。"""
    schema = _dims_schema(dims)
    if _truth_space(scorer) == GROUND_TRUTH and schema != "standard4":
        raise ValueError(f"ground-truth scorer {scorer!r} 要求 standard4 dims, 得 {sorted(dims)}")
    if schema not in RUBRIC_WEIGHTS:
        raise ValueError(f"未知 dims schema: {sorted(dims)}")
    for d, v in dims.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 <= v <= 100):
            raise ValueError(f"dim {d}={v!r} 非法(须 0-100 数值, 非 bool)")
    sig = report.get("signals")
    if not isinstance(sig, dict) or "schema_version" not in sig:
        raise ValueError("report 缺合法 signals(须 dict 且含 schema_version)——不可拟合不准入")
    commit = report.get("engine_commit", "unknown")
    return {
        "date": date, "scorer": scorer, "round": round_,
        "title": report.get("title") or slug, "source": report.get("source") or slug,
        "slug": slug, "dims": dims, "total": rubric_total(dims, schema),
        "comments": comments, "auto_signals": sig,
        "version": commit, "engine_commit": commit,
        "output_dir": str(output_dir), "signals_hash": signals_hash(sig),
        "ingested_at": ingested_at,
    }


def hfl_dup_key(raw):
    """对 RAW JSON 行(非 HflRow)的幂等键: (scorer, slug, round, signals_hash(auto_signals))。"""
    return (raw.get("scorer"), raw.get("slug"), raw.get("round"),
            signals_hash(raw.get("auto_signals") or {}))


def find_duplicate(existing_raw_rows, new_row):
    """new_row 的 dup_key 是否已在 existing_raw_rows(raw dict 列表)中。"""
    keys = {hfl_dup_key(r) for r in existing_raw_rows}
    return hfl_dup_key(new_row) in keys
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_calibration.py -q`
Expected: PASS(全部 calibration 测绿)。

- [ ] **Step 5: 提交**

```bash
git add src/hiki/calibration.py tests/test_calibration.py
git commit -m "feat(calibration): build_hfl_row(frozen内联+严校) + 幂等键(raw行)"
```

---

### Task 4: `hfl_ingest.py` 重写(frozen-emit + 幂等 + 严校)+ 往返测 + 全网验证

**Files:**
- Modify(整文件重写): `scripts/hfl_ingest.py`
- Test: `tests/test_hfl_ingest.py`(新)

**Interfaces:**
- Consumes: `calibration.RUBRIC_WEIGHTS`/`build_hfl_row`/`find_duplicate`(Tasks 2-3);各 slug 的 `report.json`(含 `signals`/`engine_commit`,Task 1)。
- Produces: CLI `python scripts/hfl_ingest.py <eval_dir> [--round R] [--write] [--allow-duplicate] [--hfl PATH]`,append schema-正确的 frozen 行到 hfl(默认真 `assets/hfl.jsonl`,`--hfl` 可改用于测试)。

- [ ] **Step 1: 写失败测试**

`tests/test_hfl_ingest.py`:
```python
"""E3 Slice1b: hfl_ingest CLI 往返 + 幂等(合成 eval_dir, 不碰真 assets/hfl.jsonl)。"""
import json
import subprocess
import sys
from pathlib import Path

from hiki import calibration

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hfl_ingest.py"


def _setup_eval(tmp_path):
    d = tmp_path / "evalX"
    (d / "S1").mkdir(parents=True)
    (d / "S1" / "report.json").write_text(json.dumps({
        "title": "甲书", "source": "SRC001", "engine_commit": "cafef00d",
        "signals": {"schema_version": 1, "deliverable": True, "seam_detected": 25,
                    "grade": "A", "opening_immersion": 80},
    }, ensure_ascii=False), encoding="utf-8")
    (d / "scorecard_ed.yaml").write_text(
        "rater: 网文编辑\ndate: 2026-06-29\nscores:\n"
        "  S1: {拉力: 60, 笔力: 70, 人: 60, 承重: 30, 追读: 高, 最致命: 衔接, 点评: ok}\n",
        encoding="utf-8")
    return d


def _run(eval_dir, hfl, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(eval_dir), "--hfl", str(hfl), *extra],
                          capture_output=True, text=True, encoding="utf-8")


def test_ingest_write_then_idempotent(tmp_path):
    d = _setup_eval(tmp_path)
    hfl = tmp_path / "hfl.jsonl"
    r1 = _run(d, hfl, "--round", "test-round", "--write")
    assert r1.returncode == 0, r1.stderr
    rows, errs = calibration.load_hfl(hfl)
    assert errs == [] and len(rows) == 1
    assert rows[0].signal_compat == "frozen" and rows[0].truth_space == "editor"
    assert rows[0].total == 56.5 and rows[0].slug == "S1"
    # 再跑同输入 → 幂等跳过, 不增行
    r2 = _run(d, hfl, "--round", "test-round", "--write")
    assert r2.returncode == 0
    rows2, _ = calibration.load_hfl(hfl)
    assert len(rows2) == 1, "幂等失败: 重复 append"


def test_ingest_preview_does_not_write(tmp_path):
    d = _setup_eval(tmp_path)
    hfl = tmp_path / "hfl.jsonl"
    r = _run(d, hfl, "--round", "test-round")   # 无 --write
    assert r.returncode == 0
    assert not hfl.exists() or hfl.read_text(encoding="utf-8").strip() == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_hfl_ingest.py -q`
Expected: FAIL(旧脚本无 `--hfl`、写 legacy auto_signals → `signal_compat!="frozen"` 或 argparse 报未知参数)。

- [ ] **Step 3: 重写脚本**

整文件替换 `scripts/hfl_ingest.py` 为:
```python
"""人工评分回流:读 <eval_dir>/scorecard_*.yaml + 各 slug report.json,
构造 schema-正确的 hfl 行(内联冻结 report['signals'] → 可拟合)+ 加权总分 + IRR,
幂等汇入 hfl.jsonl(喂校准飞轮)。
用法: PYTHONPATH=src python scripts/hfl_ingest.py <eval_dir> [--round R] [--write] [--allow-duplicate] [--hfl PATH]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:                                              # ⚠ skip 行走 stderr; Windows piped stderr 默认 gbk
    sys.stdout.reconfigure(encoding="utf-8")      # 会 UnicodeEncodeError(子进程崩)→ 同时硬化 stderr
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from hiki import calibration  # noqa: E402

DEFAULT_HFL = ROOT / "assets" / "hfl.jsonl"


def _existing_raw(path):
    """现有 hfl.jsonl 按 raw json dict 逐行读(非 load_hfl: 需保留 round/auto_signals 原 dict 算幂等键)。"""
    if not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    return out


def _extract_dims(scores_for_slug):
    """按可识别 schema 取四维(标签逐字保留, 不静默映射)。无完整 schema → 空(build_hfl_row 拒)。"""
    for w in calibration.RUBRIC_WEIGHTS.values():
        if all(k in scores_for_slug for k in w):
            return {k: scores_for_slug[k] for k in w}
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir")
    ap.add_argument("--round", default="human-eval-5")
    ap.add_argument("--write", action="store_true", help="实际追加(默认只预览)")
    ap.add_argument("--allow-duplicate", action="store_true", help="绕过幂等去重")
    ap.add_argument("--hfl", default=str(DEFAULT_HFL), help="目标 hfl.jsonl(默认 assets/hfl.jsonl)")
    a = ap.parse_args()
    d = Path(a.eval_dir)
    cards = [p for p in sorted(d.glob("scorecard_*.yaml")) if "template" not in p.name]
    if not cards:
        print(f"没找到 {d}/scorecard_<名>.yaml(template 不算)")
        return
    import yaml
    ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing = _existing_raw(a.hfl)
    records, by_book, skipped = [], {}, 0
    for c in cards:
        doc = yaml.safe_load(c.read_text(encoding="utf-8")) or {}
        rater = doc.get("rater", c.stem)
        scores = doc.get("scores") or {}
        date = str(doc.get("date", "")) or None
        for slug, s in scores.items():
            rep_path = d / slug / "report.json"
            if not rep_path.exists():
                print(f"  ⚠ 跳过 {rater}/{slug}: 无 report.json", file=sys.stderr)
                skipped += 1
                continue
            report = json.loads(rep_path.read_text(encoding="utf-8"))
            comments = f"追读{s.get('追读','')} | 最致命:{s.get('最致命','')} | {s.get('点评','')}"
            try:
                row = calibration.build_hfl_row(
                    scorer=rater, slug=slug, dims=_extract_dims(s), comments=comments,
                    report=report, round_=a.round, output_dir=d / slug,
                    ingested_at=ingested_at, date=date)
            except ValueError as e:
                print(f"  ⚠ 跳过 {rater}/{slug}: {e}", file=sys.stderr)
                skipped += 1
                continue
            if not a.allow_duplicate and calibration.find_duplicate(existing, row):
                print(f"  ⚠ 跳过 {rater}/{slug}: 重复(scorer/slug/round/signals_hash 已存在)", file=sys.stderr)
                skipped += 1
                continue
            records.append(row)
            existing.append(row)   # 防同批内重复
            by_book.setdefault(slug, []).append((rater, row["dims"], row["total"]))

    print(f"\n=== 人工评分汇总(round={a.round}) ===")
    for slug, rows in by_book.items():
        n = len(rows)
        tots = [r[2] for r in rows]
        mt = round(sum(tots) / n, 1)
        spread = round(max(tots) - min(tots), 1) if n > 1 else 0.0
        print(f"{slug:18} 评委{n} 总分{mt} IRR±{spread}")

    out = Path(a.hfl)
    if a.write:
        with out.open("a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n✓ 追加 {len(records)} 条 → {out}(跳过 {skipped})")
    else:
        print(f"\n(预览 {len(records)} 条, 跳过 {skipped}; 加 --write 落 {out})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_hfl_ingest.py -q`
Expected: PASS(2 passed)。

- [ ] **Step 5: 全网验证(无回归)**

Run: `python -m pytest tests/test_calibration.py tests/test_calibration_realdata.py tests/test_produce_engine_commit.py tests/test_hfl_ingest.py tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全 PASS(金标+装配网平凡绿——只读 `report["signals"]` 子 dict)。

Run: `python -m pytest -m "not api" -q`
Expected: 全绿;报确切 passed/deselected。

- [ ] **Step 6: 提交**

```bash
git add scripts/hfl_ingest.py tests/test_hfl_ingest.py
git commit -m "feat(hfl_ingest): frozen-emit(report.signals 内联)+ 幂等 + standard4 严校 + --hfl"
```

---

## Self-Review

**1. Spec coverage:**
- engine_commit top-level → Task 1 ✅;`report["signals"]` 不含 engine_commit 守卫 → Task 1 Step1 测 ✅。
- RUBRIC_WEIGHTS 单源 + rubric_total + signals_hash → Task 2 ✅。
- build_hfl_row(frozen 内联 / standard4 严校 / 0-100+非bool / 缺 signals 拒 / engine_commit→version / output_dir/date) → Task 3 ✅。
- 幂等键(raw 行, 4 元, 重跑不判重) → Task 3 ✅。
- hfl_ingest frozen-emit + 调 calibration 助手 + per-schema dims + 幂等 + fail-closed skip+stderr + --write 预览语义 → Task 4 ✅。
- 金标/装配网绿 → Task 4 Step5 ✅。非目标(不碰门/web/建模/老行/YAML 格式)→ 计划无相关改动 + Global Constraints 约束 ✅。

**2. Placeholder scan:** 无 TBD/TODO;每 code step 全代码;命令具体。✅(`--hfl` 为可测性新增的可选参,additive,不改既有语义。)

**3. Type consistency:** `build_hfl_row` 关键字签名(scorer/slug/dims/comments/report/round_/output_dir/ingested_at/date)在 Task3 定义、Task4 调用一致;`hfl_dup_key`/`find_duplicate` 在 Task3 定义、Task4 用一致;`rubric_total(dims,schema)`/`signals_hash(signals)` Task2 定义、Task3 内部用一致;`_engine_commit`(Task1)产 `report["engine_commit"]` → Task3 读 `report.get("engine_commit","unknown")` 一致;行字段 `auto_signals`/`signals_hash`/`output_dir` Task3 产、Task4 round-trip 经 `load_hfl` 验 `signal_compat=="frozen"` 一致。✅

<!-- codex-peer-reviewed: 2026-06-29T12:10:21Z rounds=2 verdict=approved -->
