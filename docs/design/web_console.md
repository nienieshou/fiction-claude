# HIKI 产线监视台 · 前后端化设计（Web Console）

> 版本 v0.1 ｜ 2026-06-16
> 定位：把 `prototype/HIKI 产线监视台.html`（纯前端 mock 原型）拆成**真实前端 + FastAPI 后端**，
> 后端把真实流水线产物（`output/<slug>/*.json`、`funnel_report.json`、`batch_summary.json`）映射到原型隐含的数据契约，缺失字段回退 fixture。
> 决策：单文件自包含 HTML 前端（fetch 驱动）＋ FastAPI 后端（真实产物 + fixture 兜底）。

---

## 0. 一句话

原型已经定义了一套**只读监视 + 上传入队 + 产物下载**的 UI 契约；本设计保留那套 UI，把硬编码 mock 换成后端 API，后端从真实 `output/` 产物适配，产物缺失则用原型 mock 兜底，保证 UI 永远有数据。

---

## 1. 原型分析（事实基线）

`prototype/HIKI 产线监视台.html` 是 Design-Companion bundler 打包的单文件 React 应用（gzip+base64 manifest + `<x-dc>` 模板 + `DCLogic` 组件）。已解包到 `prototype/_unpacked/`（`markup.html`=DOM 结构 / `component.js`=组件逻辑+mock 数据 / `props.json`=预览参数）。**全部数据硬编码，无网络。**

原型隐含的数据契约：

| 区块 | 字段 |
|---|---|
| 书目（sidebar） | `id,title,src,slug,genre,grade(S/A/B/C/D/Q),comp,stage(0-5),status(certified/running/rejected),mode(0-4),human,cost` + 6 段进度点 |
| 6 段流水线 | `Ingest→Extract→Plan→Draft→Evaluate→Assemble`，每段 model 路由（flash/pro），状态 done/active/fail/pending |
| 概览 | grade/comp/mode/status/cost/cap%/human/认证语/stage 语/spine 状态 |
| DNA | `dna[]{label,v,note}`（脊柱/钩子/情感/弧/伏笔/爽点/人名/语域/题材） |
| 场景 | `scenes{total,drafted,peaks[],list[]{n,type,beat,status,cand,pk}}` |
| 闸门 | `gate{mech[]{k,v,pass,note}, pk[]{vs,verdict,score,pass}, book[]{k,pass,note}}` |
| 成本 | `cost[]{k,usd,note}` → 条形 + 合计 + cap% |
| 人评 | `dims[]{k,v}` + `review{total,version,mode,text,snapshot[]}` |
| Spine | `spine[]{group,items[]{name,attr,lock}}` + 冲突计数 |
| 校准 | `calib{note,points[]{label,auto,human}}`（承重 auto vs human 近零相关） |
| 交互 | 选书/选 tab；批量 .txt 上传+命名；下载 final.md/acceptance.json/cost_ledger.json/diagnostic.json |

---

## 2. 真实产物 → 契约映射（核心）

真实 schema（取自代码，权威）：

- **`output/<slug>/report.json`**（`produce.py` 组装）：`deliverable, 交付门[], source, wan_zi, out_chapters, scenes, grade{grade,mode,...}, central_conflict, final_chars, avg_chapter_chars, 暗黑比, final_consistent, cost_cny, seconds`，及大量 audit/advisory 字段；`_stage_finalize` 再补 title/output/craft。拒收本：`{rejected:true, reject_why, grade, cost_cny}`。
- **`bible.json`**：`protagonist, characters, setting, genre, voice, arc, hooks…` → DNA。
- **`scenes.json` / `plan.json` / `macro.json`** → 场景列表/beat/高点。
- **`grade.json`**：`grade, mode, …` → 准入档/压缩性/模式。
- **`fact_table.json`** → Spine（实体冻结/承重对账）。
- **`funnel_report.json`**（`funnel.py`）：`入池,pregrade成功/失败,存活,改写,keep档,可交付,拒收,改写失败,*成本_cny,pregrade分布,dry_run,墙钟_秒`。
- **`batch_summary.json`**（`batch.py`）：`任务数,成功,失败,可交付,拒收/不可交付,总成本_cny,墙钟_秒,均成本_cny,results[]{slug,ok,out_dir,grade,wan_zi,out_chapters,deliverable,交付门,final_consistent,cost_cny,seconds,rejected,error}`。

**映射规则**（`adapters.py`）：

| 契约字段 | 来源 | 缺失兜底 |
|---|---|---|
| books[] | 扫描 `output/*/`（+ `batch_summary.results`） | 无任何 output → 原型 8 本 fixture |
| status | `rejected/deliverable`→rejected；有 report→certified；有目录无 report→running | running |
| stage(0-5) | 按产物存在性推断：source=0, bible/grade=1-2, plan=3, 章草稿=3-4, report=5 | 0 |
| grade/comp/mode | `grade.json` | fixture |
| cost | `report.cost_cny` | 0 |
| human | `assets/hfl.jsonl` / `docs/evidence/human_eval*`（按 slug） | null |
| dna[] | `bible.json` 投影 | fixture |
| scenes{} | `plan.json`+`report` 计数 | fixture/null |
| gate{} | `report` 的 mechanical/audit/交付门/final_consistent | fixture（PK 等无真实值的字段恒兜底） |
| cost[] 分段 | **真实只有总额**；按 calls 估或 fixture 分段 | fixture |
| dims[]/review{} | 无真实来源（人评未结构化） | fixture |
| spine[] | `fact_table.json` | fixture/null |
| calibration | `docs/evidence/human_eval5_calibration.md` 解析或常量 | 原型常量 |

> 诚实标注：PK 胜率、per-stage USD、dims、review 文本在当前产线**无结构化真值**，UI 显示的是 fixture，acceptance.json 里标 `source:"fixture"`。这与「机器门信号≠人类真值」的既有结论一致，不伪造认证。

---

## 3. 后端（FastAPI）

```
web/backend/
  app.py          # FastAPI 实例 + 路由 + CORS（dev）
  contract.py     # pydantic 响应模型（= §1 契约）
  paths.py        # 定位 output/ 子目录、funnel/batch 报告、源目录
  adapters.py     # 真实产物 → 契约（§2）
  fixtures.py     # 原型 mock（从 component.js 移植）= 兜底数据源
  requirements.txt
```

端点：

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/api/stats` | `{total,certified,rejectRate,avgCost,budgetCap}`（+ funnel/batch 汇总若有） |
| GET | `/api/books` | 书目数组（含 6 段 states） |
| GET | `/api/books/{id}` | 选中本详情：sel/dna/scenes/gate/cost/dims/review/spine |
| GET | `/api/calibration` | `{note,points[]}` |
| POST | `/api/uploads` | 接收 .txt（multipart），落 `fictions_source/`，**后台触发 `hiki run`**，返回入队 stub（status=running,stage=0） |
| GET | `/api/books/{id}/artifacts/{name}` | 下载 final.md / acceptance.json / cost_ledger.json / diagnostic.json（真实优先，否则后端按原型逻辑生成） |
| GET | `/api/jobs/{slug}` | 轮询后台改写任务状态（queued/running/done/failed + 当前阶段 + 最近日志行） |

- 预算 cap 读 `config/pipeline.yaml`（单本 ¥50），无则 50。
- **改写触发（runner.py）**：`POST /uploads` 落盘后，用 `asyncio.create_task` 在后台跑 `produce.run(...)`（out=`output/<slug>_full`），任务状态存内存表 `JOBS[slug]`；`GET /api/jobs/{slug}` 轮询。需 `DEEPSEEK_API_KEY`，缺则任务直接 failed 并回写原因（不崩后端）。**真实花钱**——前端上传弹窗显式提示成本（~¥0.4–5/本）。
- 失败隔离：runner 内 try/except，traceback 落 `output/<slug>_full/_crash.txt`，job 标 failed。
- 启动：`uvicorn web.backend.app:app --reload`，默认 `127.0.0.1:8000`。

---

## 4. 前端（单文件自包含 HTML）

`web/frontend/index.html`：移植原型的 markup + 样式 + 交互，但：

- 删除硬编码 `BOOKS()/DETAILS()/CALIB()`，改为启动 `fetch('/api/...')`。
- 保留原型的暗色主题、6 段流水线、7 tab、sidebar、上传弹窗、下载菜单 UI。
- 用原生 JS（无构建）或 React-via-CDN 重建（倾向原生 JS + 模板字符串，零依赖，双击即开；连后端时配 `API_BASE`）。
- loading / error / 空态：API 不可达时顶部红条提示（沿用原型 error sink 风格）。
- 上传走 `POST /api/uploads`；下载走 `GET /artifacts/...`。

构建产物 `prototype/HIKI 产线监视台.html` 原样保留作设计参照，不删。

---

## 5. 数据流

```
浏览器(index.html)
  GET /api/books ───────────► adapters.list_books()
                                ├─ scan output/*/ + batch_summary.results
                                └─ 空 → fixtures.BOOKS
  GET /api/books/{id} ──────► adapters.book_detail(id)
                                ├─ report/bible/plan/fact_table/grade.json
                                └─ 逐字段缺失 → fixtures.DETAILS[id] / null
  POST /api/uploads ───────► 落 fictions_source/<name>.txt → 入队 stub
  GET /artifacts/{name} ───► 真实文件 || 后端生成(final/acceptance/ledger)
```

---

## 6. 测试

- 后端纯函数：`adapters` 映射（造 1 个真实 report.json fixture + 1 个空目录 → 断言 status/stage/字段兜底）、`select` 统计、上传命名 slug。
- 契约：每端点 200 + pydantic 模型校验。
- 前端：手测（双击开 / 连后端），不引前端测试框架。

---

## 7. 边界与非目标（YAGNI）

- 不做鉴权/多用户/持久队列/WebSocket 实时（后续 10k dashboard 再说）。
- `POST /uploads` 触发改写，但任务状态仅存**内存**（后端重启即丢；持久队列留作 10k 阶段）。轮询而非推送。
- 不重写原型 bundler 格式；前端是全新单文件，原型仅作参照。
- per-stage 成本/PK/dims/review 无真值 → fixture，并在产物里诚实标注。

---

## 8. 文件清单（落地）

```
web/
  backend/{app,contract,paths,adapters,fixtures,runner}.py, requirements.txt
  frontend/index.html
  README.md           # 起后端 + 开前端的两条命令
tests/test_web_adapters.py
docs/design/web_console.md   # 本文
```
