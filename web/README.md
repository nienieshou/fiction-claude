# HIKI 产线监视台 · Web Console（前后端）

把 `prototype/HIKI 产线监视台.html`（纯前端 mock 原型）拆成**真实前端 + FastAPI 后端**。
后端把真实流水线产物映射到原型契约，缺失字段回退 fixture，保证 UI 永远有数据。
架构与映射详见 [`docs/design/web_console.md`](../docs/design/web_console.md)。

```
web/
  backend/   FastAPI：app(路由) / adapters(产物→契约) / fixtures(原型兜底)
             paths(定位) / runner(上传→后台 hiki run) / contract(pydantic)
  frontend/  index.html  单文件自包含仪表盘（fetch 驱动，零构建）
```

## 1. 装依赖

```powershell
# 项目根 E:\Project_Python\hiki-fiction-cli\claude
.venv\Scripts\python.exe -m pip install -r web\backend\requirements.txt
```

（上传后触发改写还需 hiki 自身依赖与 `.env` 里的 `DEEPSEEK_API_KEY`，见 `docs/USAGE.md`。）

## 2. 起后端（同时服务前端）

```powershell
$env:PYTHONPATH = "src"          # runner 触发改写时要 import hiki
.venv\Scripts\python.exe -m uvicorn web.backend.app:app --reload
```

浏览器开 **http://127.0.0.1:8000/** —— 后端 `/` 直接吐 `frontend/index.html`。

也可不连后端直接双击 `web/frontend/index.html`：它会回退打 `http://127.0.0.1:8000` 的 API；
后端没起则顶部红条提示，UI 空。

## 3. 数据来源

- 有真实 `output/<slug>/` 产物 → 显示真实书目（`report/bible/grade/fact_table.json` 等）。
- 没有任何产物 → 回退原型 8 本 demo，便于先看 UI。
- per-stage 成本 / PK 胜率 / dims / review 文本在当前产线**无结构化真值** → 这些字段是 fixture，
  `acceptance.json` 里标 `source:"fixture"`，不伪造认证。

## 4. 上传 → 后台改写

侧栏「＋ 批量上传」选 `.txt` → 落 `fictions_source/` → 后台 `hiki run`（**真实花钱** ~¥0.4–5/本）。
任务状态内存轮询（`GET /api/jobs/{slug}`），后端重启即丢。缺 `DEEPSEEK_API_KEY` → 任务 failed，不崩后端。

**中断与续跑**：重启后端会打断在跑的改写 → 任务显示 `中断·可续跑(stalled)`。两种续跑：
手动点「▶ 续跑」，或**启动时自动续跑**所有 stalled（默认开，`HIKI_WEB_AUTORESUME=0` 关闭）。
续跑从已有产物 B2 继续（省钱）。列表按最新活动倒序，最新任务置顶。

**中断 vs 崩溃**：进程被打断（无 `_crash.txt`）显示 `中断·可续跑(stalled)`，会被自动续跑。改写**崩溃**（落 `_crash.txt`，如 DeepSeek 余额不足/401·402·403 致命错误）显示 `失败·可续跑(failed)`——**可手动续跑但不自动续跑**（避免确定性崩因被反复重拉烧钱；修因/充值后手点「▶ 续跑」）。永久性 API 错误判致命、0 重试（不浪费退避）。

**best-of-3 + 并发闸（R17）**：上传后每本默认 **best-of-3**——交付门拒(死人复活/章缝/双版本等随机型)→ force 重掷,首个可交付即停,3 稿全拒则归类拒收(系统性);源头致命(Q/暗黑)不重掷。每稿信息落 `output/<slug>_full/_bestof.json`(逐稿 deliverable/拒因/¥ + 分类:T1直接交付/重掷救回/系统性拒)。`HIKI_WEB_BEST_OF` 覆盖次数。job 并发闸 `HIKI_WEB_CONCURRENCY`(默认 2)→ 多本上传排队,避免齐发撞 DeepSeek 限流(APITimeout)。成本:可交付本 1×、拒收本至多 3×。仪表盘:运行中重掷的本显示"⟳ N/M稿"徽章(解释阶段条重走);完成态显示分类标签(重掷救回·N稿 / 系统性拒·N稿);详情面板显示逐稿历史(稿N ✓/✗ 拒因)。一次过的本不显示稿次,保持干净。

## 5. API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/stages` | 6 段流水线定义 |
| GET | `/api/stats` | 全局：总数/认证/拒收率/均成本/budgetCap（+ funnel/batch 若有） |
| GET | `/api/books` | 书目数组 |
| GET | `/api/books/{id}` | 选中本：sel + detail(dna/scenes/gate/cost/dims/review/spine) |
| GET | `/api/calibration` | 承重 auto vs human 散点 |
| POST | `/api/uploads` | multipart .txt + `?new_name=` → 落盘 + 后台改写 |
| GET | `/api/jobs/{slug}` | 后台任务状态 |
| GET | `/api/books/{id}/artifacts/{name}` | final.md / acceptance.json / cost_ledger.json / diagnostic.json |

## 6. 测试

```powershell
.venv\Scripts\python.exe -m pytest tests\test_web_adapters.py -q
```

纯函数（映射/兜底/统计/slug），不起服务、不打 API、不烧改写钱。
