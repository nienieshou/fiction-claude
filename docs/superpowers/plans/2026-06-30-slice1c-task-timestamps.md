# 任务概览开始/结束时间戳 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** web 产线监视台对每本任务显示开始/结束时间戳(含进行中/排队"暂定"态)。

**Architecture:** 4 文件:`contract.py`(Book 加字段,否则 response_model 静默过滤)→ `adapters.dir_to_book`(真实目录 started/finished)→ `runner.py`(JOBS/JOB_BOOKS 加 queued_at/started_at,支撑排队任务)→ 前端 `index.html`(书卡 badge + 概览项 + fmtTime)。`app._books()` 已把 `runner.job_books()` 喂 `list_books` → **无需改 app.py**。

**Tech Stack:** FastAPI + pydantic v2(后端)、vanilla JS(前端)、pytest + `fastapi.testclient.TestClient`。无新依赖。

配套 spec:`docs/superpowers/specs/2026-06-30-slice1c-task-timestamps-design.md`(codex approved)。

## Global Constraints

- **`contract.Book` 必须声明 `started`/`finished`/`queued`(+`bestof`)** —— 否则 `/api/books` 的 `response_model=list[Book]` **静默过滤**掉这些键(codex 救下的命门;测试须断言字段真出现在 `/api/books` 响应)。
- **`finished` 仅终态**(`status in ("certified","rejected")`)且 `started` 与 `report.seconds` 均数值(非 bool)时 = `report.get("finished_at")` 若为数值否则 `started + seconds`;否则 `None`。
- **`started`** = `_timing.json.started_at`(数值,否则 None);**不**用 dir mtime 猜。
- **`runner`**:`enqueue`+`resume` 记 `JOBS[slug]["queued_at"]`;`_run_job` 切 running 处记 `JOBS[slug]["started_at"]`;`JOB_BOOKS` stub 在 enqueue 记 `queued`、running 处记 `started`;`job_status` 返回 `queued_at`/`started_at`。`time.time()`(epoch 秒)。
- **前端**:`fmtTime(epoch)` = `new Date(epoch*1000).toLocaleString("zh-CN",{hour12:false})`;queued 文案标"排队"(`queued_at`≠生产开始,不冒充)。
- **测试**:`monkeypatch.setattr(paths, "OUTPUT", <tmp>)`(OUTPUT 在 import 时定);合成书目录须含 `report.json` 或 `source/`(否则 `paths.output_dirs()` 不收录,看到 0 本);`TestClient(web.backend.app.app)`。
- **范围**:纯 web。**不**碰 producer(`finished_at` 不写,仅 derive)/ 门 / 建模 / 鉴权。现有 `tests/test_web_adapters.py`、`tests/test_runner.py` 保持绿;金标/装配网无关。
- **提交** trailer:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EoVNZMK1aq3D44jknQ18bq
  ```

---

### Task 1: `contract.Book` 加时间戳字段(+修 bestof 潜伏丢弃)

**Files:**
- Modify: `web/backend/contract.py`(Book 类,`calls` 字段后)
- Test: `tests/test_web_timestamps.py`(新建)

**Interfaces:**
- Consumes: 无。
- Produces: `Book` 新增可选字段 `started: float|None`、`finished: float|None`、`queued: float|None`、`bestof: dict|None`(均默认 None)。后续任务/前端依赖这些键能过 `/api/books`。

- [ ] **Step 1: 写失败测试**

`tests/test_web_timestamps.py`:
```python
"""Slice1c: 任务时间戳 —— Book 契约 + dir_to_book + runner JOBS。零 API。"""
from web.backend.contract import Book


def test_book_declares_timestamp_and_bestof_fields():
    b = Book(id="x_full", title="t", src="s", slug="x", genre="g", grade="A", comp="—",
             stage=5, status="certified", mode=0,
             started=1000.0, finished=1060.0, queued=999.0, bestof={"throws": 1})
    d = b.model_dump()
    for k in ("started", "finished", "queued", "bestof"):
        assert k in d, f"Book 未声明 {k} → response_model 会静默过滤"
    assert d["started"] == 1000.0 and d["finished"] == 1060.0
    assert d["queued"] == 999.0 and d["bestof"] == {"throws": 1}
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_web_timestamps.py::test_book_declares_timestamp_and_bestof_fields -v`
Expected: FAIL — pydantic v2 默认丢弃未声明字段(`extra='ignore'`)→ `model_dump()` 不含 `started` → `assert "started" in d` 失败(或构造即报未知字段)。

- [ ] **Step 3: 加字段**

`web/backend/contract.py`,在 `Book` 类 `calls: int | None = None` 行**之后**加:
```python
    started: float | None = None
    finished: float | None = None
    queued: float | None = None
    bestof: dict | None = None
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_web_timestamps.py -v`
Expected: PASS(1 passed)。

- [ ] **Step 5: 提交**

```bash
git add web/backend/contract.py tests/test_web_timestamps.py
git commit -m "feat(web): Book 加 started/finished/queued + 修 bestof 潜伏丢弃(response_model 字段)"
```

---

### Task 2: `adapters.dir_to_book` — 真实目录 started/finished

**Files:**
- Modify: `web/backend/adapters.py`(`dir_to_book`)
- Test: `tests/test_web_timestamps.py`(追加)

**Interfaces:**
- Consumes: `Book` 已声明 started/finished/bestof(Task 1);`paths.load_json`、`paths.output_dirs`、`_status_from_report`(现有)。
- Produces: `dir_to_book` 返回 dict 增 `started`/`finished`;`/api/books` 每本含这两键 + `bestof`。

- [ ] **Step 1: 写失败测试(追加)**

追加到 `tests/test_web_timestamps.py`:
```python
import json
import pytest
from fastapi.testclient import TestClient
from web.backend import app as appmod, paths


def _mkbook(out, slug, *, report=None, timing=None, source=False, bestof=None):
    d = out / f"{slug}_full"
    d.mkdir(parents=True)
    if report is not None:
        (d / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    if timing is not None:
        (d / "_timing.json").write_text(json.dumps(timing), encoding="utf-8")
    if source:
        (d / "source").mkdir(); (d / "source" / "clean.txt").write_text("x", encoding="utf-8")
    if bestof is not None:
        (d / "_bestof.json").write_text(json.dumps(bestof, ensure_ascii=False), encoding="utf-8")
    return d


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT", tmp_path)   # OUTPUT 在 import 时定 → 必须 patch 属性
    return TestClient(appmod.app)


def _book(client, bid):
    return next(b for b in client.get("/api/books").json() if b["id"] == bid)


def test_certified_book_started_and_finished(client, tmp_path):
    _mkbook(tmp_path, "cert", report={"deliverable": True, "交付门": ["通过"], "seconds": 60},
            timing={"started_at": 1000.0}, bestof={"throws": 1, "classification": "T1直接交付"})
    b = _book(client, "cert_full")
    assert b["status"] == "certified"
    assert b["started"] == 1000.0 and b["finished"] == 1060.0
    assert b["bestof"] is not None and b["bestof"]["throws"] == 1   # 字段过 response_model


def test_nonterminal_has_started_no_finished(client, tmp_path):
    _mkbook(tmp_path, "idle", timing={"started_at": 2000.0}, source=True)  # 无 report → 非终态
    b = _book(client, "idle_full")
    assert b["started"] == 2000.0 and b["finished"] is None


def test_old_book_no_timing_graceful_none(client, tmp_path):
    _mkbook(tmp_path, "old", report={"deliverable": True, "交付门": ["通过"], "seconds": 30})  # 无 _timing
    b = _book(client, "old_full")
    assert b["started"] is None and b["finished"] is None


def test_explicit_finished_at_preferred(client, tmp_path):
    _mkbook(tmp_path, "exp", report={"deliverable": True, "交付门": ["通过"], "seconds": 60,
            "finished_at": 9999.0}, timing={"started_at": 1000.0})
    b = _book(client, "exp_full")
    assert b["finished"] == 9999.0   # 显式优先于 started+seconds(=1060)
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_web_timestamps.py -v`
Expected: 4 新测 FAIL — `b["started"]`/`b["finished"]` KeyError 或 None(dir_to_book 还没读 _timing/derive)。

- [ ] **Step 3: 实现**

`web/backend/adapters.py` 的 `dir_to_book`,在 `bof = paths.load_json(d / "_bestof.json")` 行**之前**(或紧邻 return 之前)加:
```python
    timing = paths.load_json(d / "_timing.json")
    started = timing.get("started_at") if isinstance(timing, dict) else None
    if isinstance(started, bool) or not isinstance(started, (int, float)):
        started = None
    finished = None
    secs = (report or {}).get("seconds")
    if status in ("certified", "rejected") and isinstance(started, (int, float)) \
            and isinstance(secs, (int, float)) and not isinstance(secs, bool):
        fin = (report or {}).get("finished_at")
        finished = fin if (isinstance(fin, (int, float)) and not isinstance(fin, bool)) else started + secs
```
在 return 的 dict 里(`"seconds": ...` 一带)加:
```python
        "started": started, "finished": finished,
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_web_timestamps.py -v`
Expected: PASS(5 passed)。

- [ ] **Step 5: 回归 + 提交**

Run: `python -m pytest tests/test_web_adapters.py -q`
Expected: PASS(Book 加可选字段向后兼容)。
```bash
git add web/backend/adapters.py tests/test_web_timestamps.py
git commit -m "feat(web): dir_to_book 暴露 started(_timing)/finished(derive, 终态+显式优先)"
```

---

### Task 3: `runner.py` — JOBS/JOB_BOOKS 时间戳(排队/在跑"暂定")

**Files:**
- Modify: `web/backend/runner.py`(`enqueue`/`resume`/`_run_job`/`job_status`)
- Test: `tests/test_web_timestamps.py`(追加)

**Interfaces:**
- Consumes: `runner.JOBS`/`JOB_BOOKS`/`_run_job`(现有;`_run_job(slug, src, run_fn=None)` 可注入 fake run_fn);`import time`(需新增到 runner.py)。
- Produces: `JOBS[slug]` 含 `queued_at`(enqueue/resume)、`started_at`(running);`JOB_BOOKS[<id>]` stub 含 `queued`(enqueue)、`started`(running);`job_status` 返回 `queued_at`/`started_at`。

- [ ] **Step 1: 写失败测试(追加)**

追加到 `tests/test_web_timestamps.py`:
```python
import asyncio
from web.backend import runner


def test_job_status_returns_timestamps():
    runner.JOBS["js0"] = {"status": "running", "stage": 1, "log": [], "error": None,
                          "queued_at": 111.0, "started_at": 222.0}
    try:
        s = runner.job_status("js0")
        assert s["queued_at"] == 111.0 and s["started_at"] == 222.0
    finally:
        runner.JOBS.pop("js0", None)


def test_run_job_records_started_at(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.paths, "OUTPUT", tmp_path)
    slug = "rj0"
    runner.JOBS[slug] = {"status": "queued", "stage": 0, "log": [], "error": None, "queued_at": 5.0}
    runner.JOB_BOOKS[f"{slug}_full"] = {"id": f"{slug}_full", "status": "running", "stage": 0}

    async def fake_run(src, **kw):
        return {"deliverable": True, "交付门": ["通过"], "cost_cny": 1}
    try:
        asyncio.run(runner._run_job(slug, tmp_path / "s.txt", run_fn=fake_run))
        assert isinstance(runner.JOBS[slug].get("started_at"), float)
        assert isinstance(runner.JOB_BOOKS[f"{slug}_full"].get("started"), float)
    finally:
        runner.JOBS.pop(slug, None); runner.JOB_BOOKS.pop(f"{slug}_full", None)


def test_enqueue_records_queued_at(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.paths, "OUTPUT", tmp_path)
    monkeypatch.setattr(runner.paths, "SOURCES", tmp_path / "src")
    monkeypatch.setattr(runner, "UPLOAD_DIR", tmp_path / "src" / "_uploads")  # import 时定, 不patch会写真库
    async def noop(*a, **k):
        return None
    monkeypatch.setattr(runner, "_run_job", noop)   # 不真跑 produce
    try:
        res = asyncio.run(runner.enqueue("书.txt", "书", b"content"))
        slug = res["job_slug"]
        assert isinstance(runner.JOBS[slug].get("queued_at"), float)
        assert isinstance(runner.JOB_BOOKS[res["book"]["id"]].get("queued"), float)
    finally:
        for s in list(runner.JOBS): runner.JOBS.pop(s, None)
        for b in list(runner.JOB_BOOKS): runner.JOB_BOOKS.pop(b, None)
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_web_timestamps.py -k "timestamps or started_at or queued_at" -v`
Expected: FAIL — `job_status` 不返回 queued_at;`_run_job`/`enqueue` 不记时间戳。

- [ ] **Step 3: 实现**

`web/backend/runner.py`:
1. 顶部 import 块(`import os` 一带)加 `import time`(若未导入)。
2. `enqueue` 的 `JOBS[slug] = {...}` 加 `"queued_at": time.time()`;`stub = {...}` 加 `"queued": JOBS[slug]["queued_at"]`(在 stub 字典里加 `"queued": ...`,用刚设的值或 `time.time()`)。
3. `resume` 的 `JOBS[slug] = {...}` 加 `"queued_at": time.time()`。
4. `_run_job` 内 `job["status"] = "running"` 行**之后**加:
   ```python
           job["started_at"] = time.time()
           _stub = JOB_BOOKS.get(f"{slug}_full")
           if _stub is not None:
               _stub["started"] = job["started_at"]
   ```
5. `job_status` 返回 dict 加 `"queued_at": j.get("queued_at"), "started_at": j.get("started_at"),`。

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_web_timestamps.py -v`
Expected: PASS(全部,含 3 新 runner 测)。

- [ ] **Step 5: 回归 + 提交**

Run: `python -m pytest tests/test_runner.py -q`
Expected: PASS(JOBS 加键向后兼容)。
```bash
git add web/backend/runner.py tests/test_web_timestamps.py
git commit -m "feat(web): runner JOBS/stub 记 queued_at/started_at + job_status 返回(排队/在跑暂定时间)"
```

---

### Task 4: 前端 — fmtTime + 书卡 badge + 概览时间项

**Files:**
- Modify: `web/frontend/index.html`(`fmtDur` 旁加 `fmtTime`;`renderSide` row2;`ovHtml`)
- Test: 无 FE 测试框架 → 手验 + 全量后端套件绿。

**Interfaces:**
- Consumes: `/api/books` 的 `b.started`/`b.finished`/`b.queued`(Tasks 1-3);现有 `fmtDur`(line ~126)。
- Produces: 书卡相对时间 badge + 概览"时间"项。

- [ ] **Step 1: 加 `fmtTime` helper**

在 `web/frontend/index.html` 的 `const fmtDur = ...`(约 line 126)**下一行**加:
```javascript
const fmtTime = e => e==null ? "—" : new Date(e*1000).toLocaleString("zh-CN",{hour12:false});
const fmtAgo = e => { if(e==null) return ""; const s=Date.now()/1000-e; const h=Math.floor(s/3600),m=Math.floor(s%3600/60); return h?`${h}h前`:`${m}m前`; };
```

- [ ] **Step 2: 书卡相对 badge**

`renderSide` 的 row2 行(约 line 251,`<span class="genre">${esc(b.genre)} · ...`),在 `${bestofChip(b)}` 之后、该 `</span>` 之前插入开始相对时间:
```javascript
${b.started?`<span class="note"> · 开 ${fmtAgo(b.started)}</span>`:(b.queued?`<span class="note"> · 排队</span>`:"")}
```

- [ ] **Step 3: 概览"时间"项**

`ovHtml` 的 g2 grid 里,「当前阶段」item(约 line 333)**之后**加一个 item:
```javascript
    <div class="item"><div class="lab">时间</div><div class="val">${
      b.started ? `${fmtTime(b.started)} ~ ${b.finished?fmtTime(b.finished):"进行中"}`
      : (b.queued ? `排队中(${fmtTime(b.queued)} 入队)` : "—")
    }</div></div>
```

- [ ] **Step 4: 手验**

Run(若服务未跑):`$env:PYTHONPATH='src'; .venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000`
开 `http://127.0.0.1:8000`,确认:① 已完成书卡显示"开 Xh前",概览"时间"显示 `开始 ~ 结束`;② stage0 三本(终态)有开始~结束;③ (若有在跑/排队任务)显示"进行中"/"排队"。截图或描述确认。

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -m pytest -m "not api" -q`
Expected: 全 PASS;报确切 passed/deselected。
```bash
git add web/frontend/index.html
git commit -m "feat(web): 前端书卡开始相对时间 + 概览开始~结束/进行中/排队 时间项"
```

---

## Self-Review

**1. Spec 覆盖:** contract.Book 字段=Task1✅;dir_to_book started/finished(终态+显式优先+老书None)=Task2✅;runner queued_at/started_at/job_status/stub=Task3✅;前端 badge+概览项+fmtTime+queued标排队=Task4✅;bestof 修复+断言=Task1+Task2✅;测试坑(monkeypatch OUTPUT/source或report才被收录)=Task2 fixture✅;回归(test_web_adapters/test_runner)=Task2/3 Step5✅;非目标(不碰 producer/门)=全计划无相关改动✅。

**2. 占位扫描:** 无 TBD;每 code step 全代码;命令具体;前端用锚串定位(无 FE 测试,手验步具体)。✅

**3. 类型一致:** `started`/`finished`/`queued`(float|None)在 contract(T1)/dir_to_book(T2)/runner stub(T3)/前端(T4)一致;`bestof`(dict|None)T1 声明、dir_to_book 现有 `bestof` 键消费、T2 断言;`queued_at`/`started_at`(JOBS 内部键)T3 内部一致,经 stub 映射成书级 `queued`/`started`(对齐 Book 字段名)。✅

<!-- codex-peer-reviewed: 2026-06-30T02:52:50Z rounds=2 verdict=approved -->
