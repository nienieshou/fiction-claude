# Best-of-N 拒收即重掷 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给批量产线加 best-of-N：一本被**交付门**拒收（非源头致命）时自动重掷（force 重跑）最多 N 次，取首个可交付稿——把"draft 随机造死亡"那类随机拒收救回，抬交付率。

**Architecture:** 在 `batch._one`（单本任务包装器）外套一层重掷循环。每次重掷 = `produce.run(force=True)`（全量重画，与已验证的 (b) 实验同形），`force` 覆盖同一 `out_dir` → 首个可交付即停、否则保留最后一稿（first-deliverable-wins，无需临时目录/晋升）。只重掷**交付门拒**（`deliverable is False` 且非源头致命 `rejected`）；源头致命（Q/暗黑/低于 min-grade）重掷无用，不重。

**Tech Stack:** Python 3.11, asyncio, pytest。零新依赖。

**实证依据（本会话 (b) 实验）：** 偏执男主主跑被死人复活拒、2 次重掷全 ✅（随机型，best-of-N 必救）；第一符术师 3 稿都拒但换角色（系统性，best-of-N 救不了——留给后续"反造死亡预防"，不在本计划）。故 best-of-N 是"随机半"的便宜杠杆。

**范围（Scope）：** 只覆盖 `hiki run`（batch 路径：`load_tasks` + 单本）。`hiki funnel` 的 `run_funnel` 走不同构造，留作后续。

**关键文件：**
- `src/hiki/batch.py` — `_should_retry` 判定、`Task.best_of` 字段、`_one` 重掷循环、`load_tasks` 透传、summary 记重掷次数
- `src/hiki/__main__.py` — `--best-of` CLI 开关 + 透传 defaults/单本
- `tests/test_batch.py` — 新建，TDD `_should_retry` + `_one` 重掷循环
- `docs/USAGE.md` — 登记 `--best-of`

---

### Task 1: `_should_retry` 判定 + `Task.best_of` 字段

**Files:**
- Modify: `src/hiki/batch.py`（`Task` dataclass 约 L20-30；新增 `_should_retry`）
- Test: `tests/test_batch.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_batch.py`：
```python
"""batch.py 纯函数 + best-of-N 重掷循环。零 API(用 fake run_fn)。"""
import asyncio
from hiki import batch


def test_should_retry_gate_reject():
    # 交付门拒(deliverable False, 非源头致命) → 重掷
    assert batch._should_retry({"deliverable": False}) is True


def test_should_retry_delivered():
    # 已交付 → 不重
    assert batch._should_retry({"deliverable": True}) is False


def test_should_retry_source_fatal():
    # 源头致命(Q/暗黑/min-grade: rejected=True) → 重掷无用,不重
    assert batch._should_retry({"rejected": True}) is False
    assert batch._should_retry({"deliverable": False, "rejected": True}) is False


def test_should_retry_no_signal():
    # 既非 deliverable False 也非 rejected(异常/缺字段) → 不重(保守)
    assert batch._should_retry({}) is False


def test_task_best_of_default():
    t = batch.Task(slug="x", source=__import__("pathlib").Path("a"), out_dir=__import__("pathlib").Path("o"))
    assert t.best_of == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_batch.py -q`
Expected: FAIL — `AttributeError: module 'hiki.batch' has no attribute '_should_retry'`

- [ ] **Step 3: 实现 `_should_retry` + `Task.best_of`**

在 `src/hiki/batch.py` 的 `Task` dataclass 末尾加字段（在 `force: bool = False` 之后）：
```python
    best_of: int = 1
```

在 `_pick` 函数**之前**（约 L67）插入：
```python
def _should_retry(rep: dict) -> bool:
    """best-of-N:仅"交付门拒"(deliverable is False 且非源头致命)值得重掷——draft随机造死亡那类。
    源头致命(rejected=True:Q/暗黑/低于min-grade)重掷无用;已交付/无信号 不重。"""
    return rep.get("deliverable") is False and not rep.get("rejected")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_batch.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add src/hiki/batch.py tests/test_batch.py
git commit -m "feat(best-of-n): _should_retry 判定 + Task.best_of 字段

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `_one` 重掷循环（核心）

**Files:**
- Modify: `src/hiki/batch.py`（`_one`，约 L76-90）
- Test: `tests/test_batch.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/test_batch.py` 追加：
```python
from pathlib import Path


def _task(tmp_path, best_of):
    src = tmp_path / "s.txt"; src.write_text("x", encoding="utf-8")
    return batch.Task(slug="t", source=src, out_dir=tmp_path / "o", best_of=best_of)


def test_one_retries_until_deliverable(tmp_path):
    # best_of=3, 前两稿交付门拒、第三稿可交付 → 3 throws, 终态可交付; 重掷用 force=True
    reps = [{"deliverable": False}, {"deliverable": False}, {"deliverable": True, "title": "ok"}]
    forces = []
    async def fake_run(*a, force=False, **k):
        forces.append(force); return reps[len(forces) - 1]
    res = asyncio.run(batch._one(asyncio.Semaphore(1), _task(tmp_path, 3), run_fn=fake_run))
    assert res["throws"] == 3 and res["rejected"] is False
    assert forces == [False, True, True]      # 首稿用 task.force(False), 重掷强制 force


def test_one_stops_on_first_deliverable(tmp_path):
    reps = [{"deliverable": True, "title": "ok"}]
    async def fake_run(*a, **k): return reps[0]
    res = asyncio.run(batch._one(asyncio.Semaphore(1), _task(tmp_path, 3), run_fn=fake_run))
    assert res["throws"] == 1 and res["rejected"] is False


def test_one_no_retry_on_source_fatal(tmp_path):
    calls = []
    async def fake_run(*a, **k): calls.append(1); return {"rejected": True}
    res = asyncio.run(batch._one(asyncio.Semaphore(1), _task(tmp_path, 3), run_fn=fake_run))
    assert res["throws"] == 1 and len(calls) == 1   # 源头致命不重掷


def test_one_exhausts_best_of_all_rejected(tmp_path):
    async def fake_run(*a, **k): return {"deliverable": False, "交付门": ["死人复活"]}
    res = asyncio.run(batch._one(asyncio.Semaphore(1), _task(tmp_path, 2), run_fn=fake_run))
    assert res["throws"] == 2 and res["rejected"] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_batch.py -k one_ -q`
Expected: FAIL — `_one()` 不接受 `run_fn` 参数 / 无 `throws` 键

- [ ] **Step 3: 实现重掷循环**

把 `src/hiki/batch.py` 的 `_one` 整个替换为：
```python
async def _one(sem: asyncio.Semaphore, task: Task, run_fn=run) -> dict:
    async with sem:                                   # 外层限并行本数(账号上限内)
        t0 = time.time()
        if not task.source.exists():
            return {"slug": task.slug, "ok": False, "error": f"源不存在: {task.source}"}
        try:
            rep, throws = None, 0
            for attempt in range(1, max(1, task.best_of) + 1):   # best-of-N: 拒收即重掷
                throws = attempt
                rep = await run_fn(task.source, task.n_ch, task.n_chunks, task.n_cand,
                                   task.refine_rounds, min_grade=task.min_grade,
                                   out_dir=task.out_dir, force=(task.force if attempt == 1 else True))
                if not _should_retry(rep):            # 已交付 或 源头致命 → 停(致命重掷无用)
                    break
            return {"slug": task.slug, "ok": True, "out_dir": str(task.out_dir),
                    "throws": throws, **_pick(rep)}
        except Exception as e:                        # 单本失败隔离:落 traceback,不拖累其余
            task.out_dir.mkdir(parents=True, exist_ok=True)
            (task.out_dir / "_crash.txt").write_text(traceback.format_exc(), encoding="utf-8")
            return {"slug": task.slug, "ok": False, "error": f"{type(e).__name__}: {e}"[:200],
                    "seconds": round(time.time() - t0, 1)}
```

> 说明：重掷用 `force=True` 全量重画（与 (b) 实验同形）；`force` 覆盖同一 `out_dir`，循环在首个可交付（`_should_retry`→False）即停，否则保留最后一稿。`run_fn=run` 默认注入真 produce，测试注入 fake。

- [ ] **Step 4: 跑测试确认通过 + 全套回归**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 全部通过（含本任务 4 条 + Task1 的 5 条）。

- [ ] **Step 5: Commit**

```bash
git add src/hiki/batch.py tests/test_batch.py
git commit -m "feat(best-of-n): _one 拒收即重掷循环(首个可交付即停,force重掷)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `load_tasks` 透传 best_of

**Files:**
- Modify: `src/hiki/batch.py`（`load_tasks`，约 L56-64）
- Test: `tests/test_batch.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/test_batch.py` 追加：
```python
def test_load_tasks_best_of(tmp_path):
    y = tmp_path / "t.yaml"
    y.write_text("tasks:\n  - slug: a\n    source: x.txt\n    best_of: 3\n  - slug: b\n    source: y.txt\n",
                 encoding="utf-8")
    defaults = {"out": "output", "chapters": 60, "chunks": 12, "candidates": 3,
                "refine_rounds": 5, "min_grade": None, "force": False, "best_of": 2}
    tasks = batch.load_tasks(y, defaults)
    assert tasks[0].best_of == 3      # per-task 覆盖
    assert tasks[1].best_of == 2      # 取 default
```

- [ ] **Step 2: 跑确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_batch.py -k load_tasks_best_of -q`
Expected: FAIL — `tasks[0].best_of` 恒为 1（未透传）

- [ ] **Step 3: 实现透传**

在 `load_tasks` 里构造 `Task(...)` 的 `force=...` 那一行**之后**加一行参数：
```python
            force=bool(t.get("force", defaults["force"])),
            best_of=int(t.get("best_of", defaults.get("best_of", 1))),
```

- [ ] **Step 4: 跑确认通过**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_batch.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hiki/batch.py tests/test_batch.py
git commit -m "feat(best-of-n): load_tasks 透传 best_of(per-task覆盖+default)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: CLI `--best-of` 开关

**Files:**
- Modify: `src/hiki/__main__.py`（`_add_run_opts` 约 L17-28；`_cmd_run` 约 L30-53）

无独立单测（CLI argparse）；由 Step 2 的 argparse 解析 + Task5 的真跑 smoke 验证。

- [ ] **Step 1: 加 `--best-of` 到 `_add_run_opts`**

在 `_add_run_opts` 函数里（`--force` 那行之后）加：
```python
    p.add_argument("--best-of", type=int, default=1,
                   help="拒收即重掷N次取首个可交付(只重交付门拒,非源头致命;每次重掷=一次全量¥)")
```

- [ ] **Step 2: 透传进 defaults 与单本 Task**

在 `_cmd_run` 里，`defaults = {...}` 字典加一项 `best_of`：
```python
    defaults = {"out": a.out, "chapters": a.chapters, "chunks": a.chunks,
                "candidates": a.candidates, "refine_rounds": a.refine_rounds,
                "min_grade": a.min_grade, "force": a.force, "best_of": a.best_of}
```
并在单本分支构造 `batch.Task(...)` 时加 `best_of=a.best_of`（在 `force=a.force` 之后）：
```python
        tasks = [batch.Task(slug=Path(a.src).stem, source=Path(a.src), out_dir=single_out,
                            n_ch=a.chapters, n_chunks=a.chunks, n_cand=a.candidates,
                            refine_rounds=a.refine_rounds, min_grade=a.min_grade, force=a.force,
                            best_of=a.best_of)]
```

- [ ] **Step 3: 验证 argparse + import**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m hiki run --help`
Expected: 输出含 `--best-of`，无报错。
Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "import hiki.__main__; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 全套回归**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/hiki/__main__.py
git commit -m "feat(best-of-n): CLI --best-of 开关 + 透传 run defaults/单本

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 汇总记录重掷次数

**Files:**
- Modify: `src/hiki/batch.py`（`write_summary`，约 L98-123）
- Test: `tests/test_batch.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/test_batch.py` 追加：
```python
def test_summary_counts_rethrows(tmp_path):
    results = [{"ok": True, "rejected": False, "throws": 1, "cost_cny": 8},
               {"ok": True, "rejected": False, "throws": 3, "cost_cny": 24},  # 救回:重掷2次
               {"ok": True, "rejected": True, "throws": 2, "cost_cny": 16}]
    s = batch.write_summary(results, 100.0, out_dir=tmp_path)
    assert s["重掷总次数"] == (1 + 3 + 2)
    assert s["重掷救回本数"] == 1     # throws>1 且最终可交付
```

- [ ] **Step 2: 跑确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_batch.py -k rethrows -q`
Expected: FAIL — summary 无 `重掷总次数` 键

- [ ] **Step 3: 实现**

在 `write_summary` 的 `summary = {...}` 字典里（`"results": results` 之前）加两项：
```python
    rethrown = [r for r in ok if (r.get("throws") or 1) > 1]
    summary_extra = {"重掷总次数": sum(r.get("throws", 1) for r in ok),
                     "重掷救回本数": sum(1 for r in rethrown if not r.get("rejected"))}
```
把 `summary = {...}` 改为在末尾合并 `**summary_extra`：
```python
    summary = {"任务数": len(results), "成功": len(ok), "失败": len(fail),
               "可交付": len(delivered), "拒收/不可交付": len(ok) - len(delivered),
               "总成本_cny": cost, "墙钟_秒": wall,
               "均成本_cny": round(cost / max(1, len(ok)), 2),
               **summary_extra, "results": results}
```
（把 `rethrown`/`summary_extra` 两行放在 `cost = ...` 之后、`summary = ...` 之前。）

- [ ] **Step 4: 跑确认通过 + 全套**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/hiki/batch.py tests/test_batch.py
git commit -m "feat(best-of-n): 汇总记重掷总次数+重掷救回本数

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 文档

**Files:**
- Modify: `docs/USAGE.md`（`run` 选项表，约 L73-83）

- [ ] **Step 1: 登记 `--best-of`**

在 `run` 选项表（`| --force | ... |` 那行之后）加一行：
```markdown
| `--best-of` | 1 | 拒收即重掷N次取首个可交付。**只重"交付门拒"**(死人复活/章缝/双版本等随机型),源头致命(Q/暗黑/低于min-grade)不重。每次重掷=一次全量¥。实证:随机型重掷必救,系统性源(每稿都造死人复活)救不了——后者待"反造死亡预防"。 |
```

- [ ] **Step 2: Commit**

```bash
git add docs/USAGE.md
git commit -m "docs(best-of-n): 登记 --best-of 开关与适用边界

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 后续（不在本计划内）
- **更便宜的 from-draft 重掷**：当前重掷 = `force=True` 全量重画（~¥8/次）。方差主要在 draft；可加"force-from-draft"模式（保 bible/plan，只删 draft/final/report 后续跑）→ ~半价。需 produce 支持分阶段 force。
- **funnel 路径**：`run_funnel` 同样透传 best_of。
- **系统性源的反造死亡预防**：第一符术师那类（每稿都造死人复活，best-of-N 救不了）→ 强化"源 never_dies → 禁 draft 写其死亡"（项2 的 never_dies 变体，比现有 alive-baseline 狠）。

## Self-Review
- **Spec 覆盖**：判定+字段=Task1；重掷循环=Task2；yaml透传=Task3；CLI=Task4；汇总=Task5；文档=Task6。funnel/from-draft/系统性预防明确划为后续。✅
- **占位符扫描**：各步含真实代码+命令+期望;无 TBD/“类似上文”。✅
- **类型一致性**：`_should_retry(rep)->bool`（Task1 定义，Task2 调用一致）；`Task.best_of:int`（Task1 定义，Task2/3/4 一致引用）；`_one(sem,task,run_fn=run)` 返回含 `throws`（Task2 定义，Task5 summary 读 `r["throws"]` 一致）；`best_of` 键在 defaults（Task3 `defaults.get("best_of",1)` 与 Task4 `defaults[...]="best_of"` 一致）。✅
