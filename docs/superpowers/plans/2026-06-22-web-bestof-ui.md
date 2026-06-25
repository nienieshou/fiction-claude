# 前端展示 best-of-N 稿次/分类 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仪表盘展示 best-of-N:运行中显示"第 N/M 稿"徽章(解释阶段条为何重置)、完成态显示分类标签(直接交付/重掷救回·N稿/系统性拒·N稿)、详情显示逐稿历史。**稿次是壳不是阶段**——徽章在阶段条之上,阶段条照常显示当前稿进度。

**Architecture:** 后端已写 `_bestof.json`(best_of/throws/classification/history)。本计划:① `runner.job_status` 暴露 `best_of`(throws 已有)供运行中实时徽章;② `adapters` 读 `_bestof.json`,给书目加 `bestof`(列表标签)、详情加 `bestof.history`(逐稿表);③ 前端 `pollJobs` 存 `S.jobs[slug]` 供运行中徽章,侧栏卡片加稿次徽章+分类标签,详情加历史表。仅 throws>1 才露出稿次 UI(一次过的本不打扰)。

**Tech Stack:** Python(后端 TDD)+ 单文件 `web/frontend/index.html`(原生 JS,无测试框架→冒烟验证)。零新依赖。

**关键文件：**
- `web/backend/runner.py` — `_run_job` 存 `job["best_of"]`、`job_status` 暴露 `best_of`
- `web/backend/adapters.py` — `dir_to_book` 加 `bestof`(紧凑)、`book_detail` 加 `bestof`(含 history)
- `web/frontend/index.html` — `pollJobs` 存 S.jobs、`renderSide` 卡片徽章+标签、`renderMain` 详情徽章+历史表
- `tests/test_runner.py` / `tests/test_web_adapters.py` — 后端 TDD

**数据形状（全程一致）：**
- `_bestof.json`(已存在): `{best_of:int, throws:int, classification:str, history:[{throw,deliverable,rejected,reason,cost_cny}]}`
- `dir_to_book` 加: `"bestof": {"throws":int, "classification":str} | None`
- `book_detail` 加: `"bestof": {best_of,throws,classification,history} | None`
- `job_status` 加: `"best_of": int`(throws 已有)

---

### Task 1: `runner` 暴露 best_of（运行中实时徽章用）

**Files:**
- Modify: `web/backend/runner.py`（`_run_job` 存 best_of；`job_status` 返回 best_of）
- Test: `tests/test_runner.py`（APPEND）

- [ ] **Step 1: 写失败测试（APPEND 到 tests/test_runner.py 末尾；先 Read）**

```python


def test_job_status_exposes_best_of():
    runner.JOBS["bo"] = {"status": "running", "stage": 2, "log": [], "error": None,
                         "throws": 2, "best_of": 3}
    s = runner.job_status("bo")
    assert s["best_of"] == 3 and s["throws"] == 2
    runner.JOBS.pop("bo", None)
```

- [ ] **Step 2: 跑确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_runner.py -k best_of -q`
Expected: FAIL — `KeyError: 'best_of'`

- [ ] **Step 3: 实现**

(a) 在 `_run_job` 里,`best_of = max(1, int(os.environ.get("HIKI_WEB_BEST_OF", "3")))` 那行**之后**加：
```python
    job["best_of"] = best_of
```
(b) 在 `job_status` 的 return dict 末尾加 `"best_of"`：
```python
    return {"slug": slug, "status": j["status"], "stage": j.get("stage", 0),
            "log": j.get("log", [])[-12:], "error": j.get("error"),
            "throws": j.get("throws", 1), "best_of": j.get("best_of", 1)}
```

- [ ] **Step 4: 跑确认通过 + 全套**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add web/backend/runner.py tests/test_runner.py
git commit -m "feat(bestof-ui): runner 暴露 best_of(运行中稿次徽章用)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `adapters` 读 `_bestof.json` → 书目/详情 `bestof`

**Files:**
- Modify: `web/backend/adapters.py`（`dir_to_book` 约 L109-119；`book_detail` 约 L304-）
- Test: `tests/test_web_adapters.py`（APPEND）

- [ ] **Step 1: 写失败测试（APPEND 到 tests/test_web_adapters.py 末尾；先 Read 文件头确认 fixture 风格如 `fake_output`/`_write`）**

```python
def test_dir_to_book_bestof(fake_output):
    d = fake_output / "bo_full"
    _write(d, "report.json", {"deliverable": True, "cost_cny": 8})
    _write(d, "_bestof.json", {"best_of": 3, "throws": 2, "classification": "重掷救回",
                               "history": [{"throw": 1, "deliverable": False, "reason": "死人复活"},
                                           {"throw": 2, "deliverable": True}]})
    b = adapters.dir_to_book(d, {})
    assert b["bestof"]["throws"] == 2 and b["bestof"]["classification"] == "重掷救回"


def test_dir_to_book_bestof_absent(fake_output):
    d = fake_output / "nob_full"
    _write(d, "report.json", {"deliverable": True})
    assert adapters.dir_to_book(d, {}).get("bestof") is None


def test_book_detail_bestof_history(fake_output):
    d = fake_output / "boh_full"
    _write(d, "report.json", {"deliverable": False, "交付门": ["死人复活"]})
    _write(d, "_bestof.json", {"best_of": 3, "throws": 3, "classification": "系统性拒(全稿交付门拒)",
                               "history": [{"throw": i, "deliverable": False, "reason": "死人复活"} for i in (1, 2, 3)]})
    det = adapters.book_detail("boh_full")
    assert det["bestof"]["classification"].startswith("系统性拒")
    assert len(det["bestof"]["history"]) == 3
```

- [ ] **Step 2: 跑确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_web_adapters.py -k bestof -q`
Expected: FAIL — `KeyError: 'bestof'` / `b["bestof"]` 不存在

- [ ] **Step 3: 实现**

(a) `dir_to_book`：在 `return { ... }` 的 dict 里(`"seconds":...,"calls":...,` 之后,闭合 `}` 之前)加一项。先在 return 之前算：
```python
    bof = paths.load_json(d / "_bestof.json")
    bestof = ({"throws": bof.get("throws"), "classification": bof.get("classification")}
              if isinstance(bof, dict) and bof.get("throws") else None)
```
然后在 return dict 末尾加 `"bestof": bestof,`：
```python
        "seconds": (report or {}).get("seconds"), "calls": (report or {}).get("calls"),
        "bestof": bestof,
    }
```

(b) `book_detail`：在 `if d is not None:` 块内(real overlay 区,任意位置如 report 处理之后)加：
```python
        bof = paths.load_json(d / "_bestof.json")
        if isinstance(bof, dict) and bof.get("throws"):
            base["bestof"] = {"best_of": bof.get("best_of"), "throws": bof.get("throws"),
                              "classification": bof.get("classification"),
                              "history": bof.get("history") or []}
```
(注:`paths.load_json` 不存在文件时返回非 dict→兜底 None;`base` 来自 fixture 深拷贝,默认无 bestof 键→详情无此本时 `base.get("bestof")` 为 None,前端容忍。)

- [ ] **Step 4: 跑确认通过 + 全套**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add web/backend/adapters.py tests/test_web_adapters.py
git commit -m "feat(bestof-ui): adapters 读 _bestof.json → 书目bestof标签 + 详情history

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 前端 — pollJobs 存 S.jobs + 稿次/分类 helper

**Files:**
- Modify: `web/frontend/index.html`（`S` state 约 L115；`pollJobs` 约 L462-475；新增 helper 近 `statusInfo` L127）

无 JS 单测→**冒烟验证**(服务起着,改 index.html 即时生效:`/` 无缓存直吐)。

- [ ] **Step 1: 在 `S` 状态对象加 `jobs:{}`**

L115 `const S = { books:[], sel:null, tab:"overview", stats:{}, calib:{}, stages:[], detail:null, mode:{} };`
改为(末尾加 `jobs:{}`):
```javascript
const S = { books:[], sel:null, tab:"overview", stats:{}, calib:{}, stages:[], detail:null, mode:{}, jobs:{} };
```

- [ ] **Step 2: `pollJobs` 存每个 job 的 throws/best_of/stage**

把 `pollJobs` 的 tick 内循环改为存 job：
```javascript
    for(const s of active){
      try{ const j=await jget("/api/jobs/"+encodeURIComponent(s));
        S.jobs[s]=j;
        if(j.status==="running"||j.status==="queued") next.push(s); }catch(e){}
    }
```
(只加了 `S.jobs[s]=j;` 一行。)

- [ ] **Step 3: 加稿次/分类 helper**（插在 `statusInfo` 函数之后，约 L133）

```javascript
// best-of-N 稿次徽章:运行中且重掷>1时显示"⟳N/M稿"(解释阶段条重置);否则空
function throwBadge(b){
  const j=S.jobs[b.slug]; if(!j) return "";
  const n=j.throws||1, m=j.best_of||1;
  if((b.status==="running"||b.status==="idle") && (n>1 || m>1))
    return `<span class="tbadge" title="best-of-${m}:第${n}稿(交付门拒会重掷,阶段条随之重走)" style="color:#d2a8ff;background:rgba(210,168,255,.12);padding:1px 6px;border-radius:6px;font-size:11px">⟳ ${n}/${m}稿</span>`;
  return "";
}
// 完成态 best-of 分类标签(仅 throws>1:救回/系统性才显示;一次过不打扰)
function bestofChip(b){
  const bo=b.bestof; if(!bo || (bo.throws||1)<=1) return "";
  const col = bo.classification && bo.classification.indexOf("救回")>=0 ? "#3fb950" : "#f0883e";
  return `<span class="bochip" title="${bo.classification||''}" style="color:${col};background:rgba(255,255,255,.04);padding:1px 6px;border-radius:6px;font-size:11px">${esc(bo.classification||'')}·${bo.throws}稿</span>`;
}
```

- [ ] **Step 4: 冒烟验证**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "print(open('web/frontend/index.html',encoding='utf-8').count('throwBadge'), open('web/frontend/index.html',encoding='utf-8').count('bestofChip'))"`
Expected: `2 2`(各定义1次+待 Task4 引用;此步先只定义→输出 `1 1` 也可接受,Task4 会引用)。
浏览器开 http://127.0.0.1:8000/ 按 F12 看 Console **无报错**(JS 语法 OK)。

- [ ] **Step 5: Commit**

```bash
git add web/frontend/index.html
git commit -m "feat(bestof-ui): 前端 S.jobs 存job状态 + throwBadge/bestofChip helper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 前端 — 侧栏卡片 + 详情面板渲染

**Files:**
- Modify: `web/frontend/index.html`（`renderSide` 卡片 row2 约 L215-216；`renderMain` 详情 约 L296）

- [ ] **Step 1: 侧栏卡片 row2 加稿次徽章 + 分类标签**

`renderSide` 里 row2 那行(L215-216):
```javascript
      <div class="row2"><span class="genre">${esc(b.genre)} · <span style="color:${si.c}">${si.t}</span></span>
        <span class="hbadge" style="color:${humanColor(b.human)}">${b.human==null?"—":b.human}</span></div>
```
改为(状态文字后追加 throwBadge + bestofChip)：
```javascript
      <div class="row2"><span class="genre">${esc(b.genre)} · <span style="color:${si.c}">${si.t}</span> ${throwBadge(b)}${bestofChip(b)}</span>
        <span class="hbadge" style="color:${humanColor(b.human)}">${b.human==null?"—":b.human}</span></div>
```

- [ ] **Step 2: 详情面板加稿次徽章 + 逐稿历史**

在 `renderMain` 的"当前阶段"item(约 L297)**之后**插入一个 best-of item(读 S.jobs 实时稿次 + detail.bestof 历史)。在 `renderMain` 里找到 `S.detail` 用法;详情对象是 `const d=S.detail||{}`(或类似)。在阶段条/item 区加：
```javascript
    <div class="item"><div class="lab">best-of 稿次</div><div class="val">${(()=>{const j=S.jobs[b.slug],bo=(S.detail&&S.detail.bestof);if(j&&(j.throws>1||j.best_of>1))return `第${j.throws||1}/${j.best_of||1}稿(进行中)`;if(bo)return `${bo.classification||''} · ${bo.throws}/${bo.best_of}稿`;return "—";})()}</div>
      <div class="note">${(()=>{const bo=S.detail&&S.detail.bestof;if(!bo||!bo.history)return "";return bo.history.map(h=>`稿${h.throw} ${h.deliverable?'✓':'✗'}${h.reason?(' '+esc(h.reason)):''}`).join(' · ');})()}</div></div>
```
> 注:`b` 是 renderMain 当前书(确认 renderMain 顶部有 `const b=...` 选中书;若变量名不同,用实际名)。`S.detail` 由 loadBook 填(详情接口返回 `{sel,detail,...}`,前端存 `S.detail=detail`)。若 renderMain 里详情变量名不是 `S.detail`,用实际持有 detail 的变量。先 Read renderMain 确认。

- [ ] **Step 3: 冒烟验证**

- 浏览器 http://127.0.0.1:8000/ 刷新,Console 无报错。
- 选一本**已完成**的真实本(若其 `_bestof.json` 存在)→ 侧栏应见分类标签、详情见逐稿历史。无 _bestof.json 的旧本→不显示(优雅降级)。
Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/ -q` → 后端测试仍全绿(本任务纯前端,不应影响)。

- [ ] **Step 4: Commit**

```bash
git add web/frontend/index.html
git commit -m "feat(bestof-ui): 侧栏卡片稿次徽章+分类标签;详情逐稿历史

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 文档

**Files:**
- Modify: `web/README.md`（§4 R17 段落补一句 UI）

- [ ] **Step 1: 补 UI 说明**

在 `web/README.md` §4 的 R17 段落末尾加：
```markdown
仪表盘:运行中重掷的本显示"⟳ N/M稿"徽章(解释阶段条重走);完成态显示分类标签(重掷救回·N稿 / 系统性拒·N稿);详情面板显示逐稿历史(稿N ✓/✗ 拒因)。一次过的本不显示稿次,保持干净。
```

- [ ] **Step 2: Commit**

```bash
git add web/README.md
git commit -m "docs(bestof-ui): README 补仪表盘稿次/分类展示说明

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 执行顺序
Task 1 → 2 → 3 → 4 → 5（前端 3 先于 4：helper 先定义再引用）。

## 验证总则
- 后端(Task1-2):pytest TDD,全绿。
- 前端(Task3-4):无 JS 测试框架→**冒烟**(服务起着、`/` 无缓存即时生效、F12 Console 无报错、选真实本目视)。**本计划改完需重启 web 服务?** 否——`/` 每次直吐最新 `index.html`(no-cache),前端改**刷新即生效**;但**后端改(runner/adapters)需重启**才生效。故合并后**重启一次 web 服务**再上传 10 本。

## 后续（不在本计划内）
- 实时进度条把"当前稿的阶段"和"稿次"并排动画化(本计划用静态徽章足够)。

## Self-Review
- **Spec 覆盖**:运行中徽章=Task3 helper+Task4 卡片;完成分类标签=Task2 adapters+Task3 chip+Task4 卡片;详情历史=Task2 book_detail+Task4 详情;实时稿次=Task1 job_status best_of+Task3 S.jobs。✅
- **占位符**:各步真实代码/命令/期望;前端因无测试用冒烟,已明确标注。⚠️ Task4 Step2 依赖 renderMain 的选中书变量名/detail 变量名——已标"先 Read 确认"(非占位,是现场对齐真实变量)。
- **类型一致性**:`bestof` 形状在 Task2 定义(dir_to_book 紧凑 / book_detail 含history),Task3/4 前端读 `b.bestof.{throws,classification}` 与 `S.detail.bestof.{classification,throws,best_of,history}` 一致;`job_status` 加 `best_of`(Task1)被 `S.jobs[s]`(Task3)读、`throwBadge`(Task3)用——一致。✅
