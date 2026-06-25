# Web 上传路径 best-of-3 + 并发闸 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Web 上传路径(`runner._run_job`)默认 best-of-3(交付门拒→force 重掷,首个可交付即停,仍拒则归类拒收)、记录每稿信息到 `_bestof.json`,并加 job 并发闸(默认 2)防多本上传同时跑触发 APITimeout 崩。

**Architecture:** `_run_job` 当前只调一次 `produce.run`。改成 best-of-N 循环(复用已合并的 `batch._should_retry`:只重交付门拒、不重源头致命),首稿 `force=False`(续跑/新)、重掷 `force=True`(全量),首个可交付即停。整个 produce 段套模块级 `asyncio.Semaphore`(env `HIKI_WEB_CONCURRENCY` 默认 2)→ 多本上传排队而非齐发。每本落 `_bestof.json`(逐稿 deliverable/拒因/¥ + 分类),供跑完诊断。

**Tech Stack:** Python 3.11, asyncio, FastAPI/uvicorn(已在跑), pytest。零新依赖。**成本阀(¥50 硬强制)本计划不做**(留后续)。

**关键文件：**
- `src/hiki/web` 实为 `web/backend/runner.py` — 并发 Semaphore、`_run_job` best-of-N 循环、`_bestof.json` 记录、`_classify_bestof` helper、`job_status` 暴露 throws
- `tests/test_runner.py` — 新建,TDD `_classify_bestof` + `_run_job` 循环(注入 fake run_fn)

**默认值（env 可覆盖）：** `HIKI_WEB_BEST_OF=3`、`HIKI_WEB_CONCURRENCY=2`。

---

### Task 1: `_classify_bestof` 分类 helper

**Files:**
- Modify: `web/backend/runner.py`（新增 helper,放 `_run_job` 之前）
- Test: `tests/test_runner.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_runner.py`：
```python
"""web runner: best-of-N 分类 + 重掷循环。零 API(注入 fake run_fn)。"""
import asyncio
from web.backend import runner


def test_classify_t1_delivered():
    assert runner._classify_bestof([{"deliverable": True}]) == "T1直接交付"


def test_classify_rescued():
    h = [{"deliverable": False}, {"deliverable": True}]
    assert runner._classify_bestof(h) == "重掷救回"


def test_classify_systematic_reject():
    h = [{"deliverable": False}, {"deliverable": False}, {"deliverable": False}]
    assert runner._classify_bestof(h) == "系统性拒(全稿交付门拒)"


def test_classify_source_fatal():
    assert runner._classify_bestof([{"rejected": True, "deliverable": False}]) == "源头致命"


def test_classify_empty():
    assert runner._classify_bestof([]) == "none"
```

- [ ] **Step 2: 跑确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_runner.py -q`
Expected: FAIL — `AttributeError: module 'web.backend.runner' has no attribute '_classify_bestof'`

- [ ] **Step 3: 实现**

在 `web/backend/runner.py` 的 `_run_job` 函数**之前**插入：
```python
def _classify_bestof(history: list[dict]) -> str:
    """best-of-N 结果分类(供诊断):T1直接交付 / 重掷救回 / 系统性拒 / 源头致命 / none。"""
    if not history:
        return "none"
    final = history[-1]
    if final.get("deliverable"):
        return "T1直接交付" if len(history) == 1 else "重掷救回"
    if any(h.get("rejected") for h in history):
        return "源头致命"
    return "系统性拒(全稿交付门拒)"
```

- [ ] **Step 4: 跑确认通过 + 全套**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 全绿（新增 5 条）。

- [ ] **Step 5: Commit**

```bash
git add web/backend/runner.py tests/test_runner.py
git commit -m "feat(web-bestof): _classify_bestof 分类 helper(T1/救回/系统性/致命)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `_run_job` best-of-N 循环 + `_bestof.json` 记录

**Files:**
- Modify: `web/backend/runner.py`（`_run_job`，约 L118-153；顶部加 `import json` 若缺、`from hiki.batch import _should_retry`）
- Test: `tests/test_runner.py`（追加）

- [ ] **Step 1: 写失败测试（APPEND 到 tests/test_runner.py 末尾；先 Read）**

```python
import json
from pathlib import Path
from web.backend import paths


def _setup(tmp_path, monkeypatch, slug="t"):
    monkeypatch.setattr(paths, "OUTPUT", tmp_path)
    runner.JOBS[slug] = {"status": "queued", "stage": 0, "log": [], "error": None}
    runner.JOB_BOOKS[f"{slug}_full"] = {"id": f"{slug}_full", "status": "running", "stage": 0}
    return slug


def test_run_job_retries_until_deliverable(tmp_path, monkeypatch):
    slug = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("HIKI_WEB_BEST_OF", "3")
    reps = [{"deliverable": False, "交付门": ["死人复活"]},
            {"deliverable": True, "cost_cny": 8}]
    forces = []
    async def fake_run(src, **k):
        forces.append(k.get("force")); return reps[len(forces) - 1]
    asyncio.run(runner._run_job(slug, tmp_path / "s.txt", run_fn=fake_run))
    assert runner.JOBS[slug]["status"] == "done"
    assert runner.JOBS[slug]["throws"] == 2
    assert forces == [False, True]                       # 首稿不force,重掷force
    bj = json.loads((tmp_path / f"{slug}_full" / "_bestof.json").read_text(encoding="utf-8"))
    assert bj["throws"] == 2 and bj["classification"] == "重掷救回"


def test_run_job_systematic_reject(tmp_path, monkeypatch):
    slug = _setup(tmp_path, monkeypatch, "sys")
    monkeypatch.setenv("HIKI_WEB_BEST_OF", "3")
    async def fake_run(src, **k): return {"deliverable": False, "交付门": ["死人复活"]}
    asyncio.run(runner._run_job("sys", tmp_path / "s.txt", run_fn=fake_run))
    assert runner.JOBS["sys"]["status"] == "rejected"
    assert runner.JOBS["sys"]["throws"] == 3             # 3稿全拒
    bj = json.loads((tmp_path / "sys_full" / "_bestof.json").read_text(encoding="utf-8"))
    assert bj["classification"] == "系统性拒(全稿交付门拒)"


def test_run_job_no_retry_source_fatal(tmp_path, monkeypatch):
    slug = _setup(tmp_path, monkeypatch, "q")
    monkeypatch.setenv("HIKI_WEB_BEST_OF", "3")
    calls = []
    async def fake_run(src, **k): calls.append(1); return {"rejected": True, "reject_why": "暗黑"}
    asyncio.run(runner._run_job("q", tmp_path / "s.txt", run_fn=fake_run))
    assert len(calls) == 1                                # 源头致命不重掷
    assert runner.JOBS["q"]["status"] == "rejected"
```

- [ ] **Step 2: 跑确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_runner.py -k run_job -q`
Expected: FAIL — `_run_job()` 不接受 `run_fn` / 无 `throws` / 无 `_bestof.json`

- [ ] **Step 3: 实现**

(a) 顶部确保有 `import json`（`runner.py` 当前无,加在 import 区）。

(b) 把 `_run_job` 整个替换为（保留原失败隔离 except 块结构）：
```python
async def _run_job(slug: str, src_path: Path, run_fn=None) -> None:
    job = JOBS[slug]
    out_dir = paths.OUTPUT / f"{slug}_full"
    best_of = max(1, int(os.environ.get("HIKI_WEB_BEST_OF", "3")))
    async with _JOB_SEM:                                  # 并发闸:多本上传排队,不齐发(防APITimeout崩)
        job["status"] = "running"
        job["log"].append(f"start · {src_path.name} · best-of-{best_of} · 质量优先(Spine开,精修{QUALITY['refine_rounds']}轮,候选{QUALITY['n_cand']})")
        try:
            if QUALITY["spine"]:
                os.environ["HIKI_SPINE"] = "1"
            if run_fn is None:
                import hiki.produce as produce          # 延迟导入:缺依赖/key 在此暴露
                run_fn = produce.run
            from hiki.batch import _should_retry
            history, report = [], None
            for attempt in range(1, best_of + 1):
                report = await run_fn(src_path, out_dir=out_dir, n_cand=QUALITY["n_cand"],
                                      refine_rounds=QUALITY["refine_rounds"], force=(attempt > 1))
                reason = report.get("reject_why") or "；".join(report.get("交付门") or [])
                history.append({"throw": attempt, "deliverable": report.get("deliverable"),
                                "rejected": bool(report.get("rejected")), "reason": reason[:100],
                                "cost_cny": report.get("cost_cny")})
                job["log"].append(f"throw{attempt}/{best_of}: "
                                  + ("可交付" if report.get("deliverable")
                                     else ("源拒" if report.get("rejected") else "交付门拒→重掷")))
                if not _should_retry(report):
                    break
            job["report"] = report
            job["throws"] = len(history)
            cls = _classify_bestof(history)
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "_bestof.json").write_text(json.dumps(
                    {"best_of": best_of, "throws": len(history), "classification": cls,
                     "history": history}, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            if report.get("rejected") or report.get("deliverable") is False:
                job["status"] = "rejected"
                job["log"].append(f"done · rejected · {cls}")
            else:
                job["status"] = "done"
                job["log"].append(f"done · 可交付 · {cls}")
        except Exception as e:                            # 失败隔离:不崩后端
            job["status"] = "failed"
            job["error"] = f"{type(e).__name__}: {e}"[:300]
            job["log"].append(f"failed · {job['error']}")
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "_crash.txt").write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass
    # 标记 stub 终态（list_books 若已发现真实目录会用真实值覆盖）
    stub = JOB_BOOKS.get(f"{slug}_full")
    if stub:
        stub["status"] = {"done": "certified", "rejected": "rejected",
                          "failed": "rejected"}.get(job["status"], "running")
        stub["stage"] = 5 if job["status"] in ("done", "rejected") else stub.get("stage", 0)
        if job.get("report", {}).get("cost_cny"):
            stub["cost"] = round(job["report"]["cost_cny"])
```

> 注意：原 `_run_job` 的 stub 终态块（函数末尾）保持在 `async with _JOB_SEM` 之外（sem 只圈 produce 段）。`run_fn=None` 默认走真 produce；测试注入 fake。`force=(attempt>1)`:首稿尊重续跑、重掷强制全量。

- [ ] **Step 4: 跑确认通过 + 全套**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 全绿。

> 注：本任务依赖 Task 3 定义的 `_JOB_SEM`。**先做 Task 3 再做本任务**，或本步临时在文件顶部加 `_JOB_SEM = asyncio.Semaphore(2)` 占位（Task 3 会正式化为 env 可配）。执行顺序：**Task 3 → Task 2**。

- [ ] **Step 5: Commit**

```bash
git add web/backend/runner.py tests/test_runner.py
git commit -m "feat(web-bestof): _run_job best-of-N 循环 + _bestof.json 记录

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: job 并发闸（模块级 Semaphore）

**Files:**
- Modify: `web/backend/runner.py`（顶部 JOBS/JOB_BOOKS 定义附近，约 L31-34）

**执行顺序：先做本任务，再做 Task 2**（Task 2 用到 `_JOB_SEM`）。

- [ ] **Step 1: 加模块级信号量**

在 `web/backend/runner.py` 的 `JOBS: dict[str, dict] = {}` 定义**之前**加：
```python
# job 并发闸:web 上传无外层 --parallel,多本齐发会撞 DeepSeek 限流→APITimeout 崩;闸到 N(默认2)排队。
_JOB_CONCURRENCY = max(1, int(os.environ.get("HIKI_WEB_CONCURRENCY", "2")))
_JOB_SEM = asyncio.Semaphore(_JOB_CONCURRENCY)
```

- [ ] **Step 2: 验证 import + 信号量值**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "from web.backend import runner; print('sem ok', runner._JOB_SEM._value, runner._JOB_CONCURRENCY)"`
Expected: `sem ok 2 2`

- [ ] **Step 3: Commit**

```bash
git add web/backend/runner.py
git commit -m "feat(web-bestof): job 并发闸 _JOB_SEM(默认2,env HIKI_WEB_CONCURRENCY)防多本齐发崩

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `job_status` 暴露 throws

**Files:**
- Modify: `web/backend/runner.py`（`job_status`，约 L110-115）
- Test: `tests/test_runner.py`（追加）

- [ ] **Step 1: 写失败测试（APPEND）**

```python
def test_job_status_exposes_throws(monkeypatch):
    runner.JOBS["js"] = {"status": "rejected", "stage": 5, "log": ["x"], "error": None, "throws": 3}
    s = runner.job_status("js")
    assert s["throws"] == 3
    runner.JOBS.pop("js", None)
```

- [ ] **Step 2: 跑确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_runner.py -k throws -q`
Expected: FAIL — `KeyError: 'throws'`

- [ ] **Step 3: 实现**

把 `job_status` 的 return 改为带 `throws`：
```python
    return {"slug": slug, "status": j["status"], "stage": j.get("stage", 0),
            "log": j.get("log", [])[-12:], "error": j.get("error"), "throws": j.get("throws", 1)}
```

- [ ] **Step 4: 跑确认通过 + 全套**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add web/backend/runner.py tests/test_runner.py
git commit -m "feat(web-bestof): job_status 暴露 throws

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 文档

**Files:**
- Modify: `web/README.md`（§4 上传→后台改写附近）

- [ ] **Step 1: 登记 best-of-3 + 并发闸**

在 `web/README.md` 的 §4（上传→后台改写）末尾加一段：
```markdown
**best-of-3 + 并发闸（R17）**：上传后每本默认 **best-of-3**——交付门拒(死人复活/章缝/双版本等随机型)→ force 重掷,首个可交付即停,3 稿全拒则归类拒收(系统性);源头致命(Q/暗黑)不重掷。每稿信息落 `output/<slug>_full/_bestof.json`(逐稿 deliverable/拒因/¥ + 分类:T1直接交付/重掷救回/系统性拒)。`HIKI_WEB_BEST_OF` 覆盖次数。job 并发闸 `HIKI_WEB_CONCURRENCY`(默认 2)→ 多本上传排队,避免齐发撞 DeepSeek 限流(APITimeout)。成本:可交付本 1×、拒收本至多 3×。
```

- [ ] **Step 2: Commit**

```bash
git add web/README.md
git commit -m "docs(web-bestof): 登记 best-of-3 + 并发闸 + _bestof.json

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 执行顺序
**Task 1 → Task 3 → Task 2 → Task 4 → Task 5**（Task 2 依赖 Task 3 的 `_JOB_SEM`）。

## 后续（不在本计划内）
- **成本阀硬强制**：`per_book_cny_cap ¥50` 现仅显示不拦;best-of-N 叠加后可加"跨 throw 累加超则停"。
- **grade-scope best-of**:只对 A/S 源重掷,弱源(多系统性)不浪费重掷。
- **系统性源黑名单**:验证认出的系统性本降 best_of/不重掷。

## Self-Review
- **Spec 覆盖**:分类 helper=Task1;并发闸=Task3;best-of-N循环+记录=Task2;throws暴露=Task4;文档=Task5。成本阀/grade-scope/黑名单明确划后续。✅
- **占位符扫描**:各步真实代码+命令+期望;无 TBD。✅
- **类型一致性**:`_classify_bestof(history)->str`(Task1 定义,Task2 调用一致);`_JOB_SEM`(Task3 定义,Task2 `async with _JOB_SEM` 一致);`_run_job(slug,src_path,run_fn=None)` 写 `job["throws"]`(Task2 定义,Task4 `job_status` 读 `j.get("throws")` 一致);env 名 `HIKI_WEB_BEST_OF`/`HIKI_WEB_CONCURRENCY` 全程一致。✅
- **依赖顺序**:Task 2 用 `_JOB_SEM`→已在"执行顺序"标 Task3 先行。✅
