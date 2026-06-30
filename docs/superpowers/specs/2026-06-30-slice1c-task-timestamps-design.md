# Slice 1c(部分)— 任务概览开始/结束时间戳 设计

> 2026-06-30 · web 产线监视台:任务概览显示每本任务的开始/结束时间戳(含进行中/排队"暂定"态)。codex 跨模型评审已过(救下 contract.py 字段静默丢弃坑)。基于 `master`。**纯 web 层 + 1 处 producer 无关**(不碰 pipeline/门/建模)。

## 目标
任务概览(侧栏书卡 + 概览 tab)对每本书/任务显示**开始时间**与**结束时间**;对进行中/排队任务显示开始 + "进行中/排队"(暂定)。

## 背景(已核实)
- 每本 output 目录有 `_timing.json` = `{"started_at": <epoch float>}`(`produce._started_at` 在生产首次 ingest 写一次,持久化,resume 不覆盖);`report.json` 有 `seconds`(float 总时长 = 停点 − started_at,停点:通过→Assemble末/门拒→Evaluate/早拒→判定点)。**无显式 finished_at**。
- **关键(codex 救下):`/api/books` 用 `response_model=list[Book]`,`Book`(`web/backend/contract.py`)只声明 `seconds/calls`,无 `started/finished`** → 不在 Book 加字段,`dir_to_book` 加的时间戳会被 FastAPI **静默过滤**。`bestof` 现已因此被悄悄丢(前端 `bestofChip` 拿不到 = 潜伏 bug)。
- `runner.py` 的 `JOBS`(在跑/排队任务,内存)**无任何时间字段**;排队中(信号量后)任务**无 output 目录、无 `_timing.json`** → 其开始时间只能来自 JOBS。

## 设计(5 处,后端 4 + 前端 1)

### 1) `contract.py` — Book 加字段(否则字段进不了 API)
`Book` 增:`started: float | None = None`、`finished: float | None = None`、`queued: float | None = None`;**顺手补** `bestof: dict | None = None`(修潜伏丢弃,同文件一行)。

### 2) `adapters.dir_to_book` — 真实目录的 started/finished
- `started`:读 `(d/"_timing.json").started_at`(数值则取,否则 None;**不**用 dir mtime 猜老书)。
- `finished`:仅**终态**(status∈{certified,rejected})且 `started` 与 `seconds` 均数值时 = `report.get("finished_at")` 若存在否则 `started + seconds`;否则 None(running/idle/无 started)。
- (resume 语义:`started`=首次生产开始,`seconds`=生命周期墙钟含停机 → 展示为"开始→结束",非活跃算力。)

### 3) `runner.py` JOBS — 排队/在跑任务的时间
- `enqueue` 记 `JOBS[slug]["queued_at"]=time.time()`;job 真正启动(`_run_job` 切 running 处)记 `JOBS[slug]["started_at"]=time.time()`。
- `job_status` 返回 `queued_at`/`started_at`。

### 4) `app.py` / `_books()` — job 时间进书目
构 job stub(供 `list_books(job_books=...)` 合并未落盘的排队/在跑任务)时,stub 带 `started`(=JOBS `started_at`)+ `queued`(=JOBS `queued_at`)。真实目录书的 `started` 仍由 dir_to_book 读 `_timing`(在跑书 `_timing` 已在盘);仅"排队未起跑"靠 JOBS stub。`list_books`/`dir_to_book` 不需要 active 之外的额外 job map —— 时间随 stub 进入。

### 5) 前端 `index.html`
- **书卡 `renderSide` row2**:加相对 badge,如 `开 2h前`(started 有则显;无则不显)。
- **概览 `ovHtml`**:加一项「时间」= `开始 <abs> ~ 结束 <abs>`;running→`开始 <abs> ~ 进行中`;queued(有 queued 无 started)→`排队中(<abs> 入队)`。
- 加 `fmtTime(epoch)` helper(`new Date(epoch*1000).toLocaleString("zh-CN",{hour12:false})`),复用现有 `fmtDur`。queued 与 started 文案区分(queued_at≠生产开始)。

## 验证
- **后端 `tests/test_web_timestamps.py`**(TestClient;**monkeypatch `paths.OUTPUT`→tmp**,因 `paths.ROOT/OUTPUT` 在 import 时定):
  - 造 tmp 终态书(`_timing.json`+`report.json` 带 seconds)→ `GET /api/books` 该书 `started`==_timing.started_at、`finished`≈started+seconds(且字段**真出现在响应**里 = 验证 contract.Book 已声明)。
  - 造在跑书(_timing 有、无 seconds)→ `finished`==None、`started` 有值。
  - 老书(report 有 seconds、无 _timing)→ `started`==None、`finished`==None(优雅)。
  - `runner`:enqueue 后 `JOBS[slug]` 有 `queued_at`;`job_status` 返回 `queued_at`/`started_at`。
  - `report.finished_at` 若存在 → 优先于 derive。
  - **断 `bestof` 也出现在 `/api/books`**(同片补的 Book 字段)。
  - **测试坑(codex)**:合成书目录须带 `source/` 或 ARTIFACT_FILES 之一,否则 `paths.output_dirs()` **不收录**(只放 `_timing.json` 会被忽略 → 测试看到 0 本)。stub 在 `runner.JOB_BOOKS`(非 JOBS)→ 排队时间补到 JOB_BOOKS 条目。
- **前端**:无 FE 测试框架 → 手验(书卡 badge + 概览项 + queued/running/done 三态)。
- **回归**:现有 `tests/test_web_adapters.py` 全绿(Book 加可选字段向后兼容);金标/装配网无关(纯 web)。
- 全量 `pytest -m 'not api'` 绿。SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- **不**在 producer 写 `finished_at`(本片 derive;读显式优先仅为前向兼容,producer 改另案)。
- **不**加鉴权/多用户/时区库;**不**碰 pipeline/门/建模/Slice1c 的评分写入路径(那是另一块)。
- **不**用 mtime 猜时间。

## 风险
- **contract.py 字段丢弃**(codex 救下):新字段必须同时进 `Book` 模型,否则 `response_model` 静默过滤 —— 测试断言"字段出现在响应"即守此。
- **resume 语义**:`seconds` 含停机墙钟 → 仅作"开始→结束"展示,不标"算力耗时"。
- **queued vs started**:排队任务只有 `queued_at`(非生产开始)→ 文案标"排队",不冒充开始。
- 老书无 `_timing` → started/finished 优雅 None(回退现有 `总历时 seconds` 展示)。

<!-- codex-peer-reviewed: 2026-06-30T02:36:16Z rounds=1 verdict=approved -->
