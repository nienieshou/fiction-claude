# PreDraft Review v0.5(部分接线预起草门 + regen 根因回路)设计

> 2026-07-01 · A/B/C(n=8)+ v0 校准证据(`docs/design/e3-validation-{A,B,C}-results.md`)+ codex v1 设计评共识。
> **不上全 v1 硬门**(n=5 精度是烟雾信号、regen 未证)。**v0.5 = 部分接线**:只硬拦已证的 det `章节复制`,LLM 类目仍隔离/校准。
> **核心新证据目标(codex)**:门拦了,管线**能不能修对工件产出更好的书**,还是 churn 到把缺陷藏过检测器。基于 `master`。

## 已核实的管线事实(grounded)
- `_stage_mine` 产 `scenes`(源场景清单)**在 plan 之前冻结**;`plan.chapters[].scenes[].source_scene_index` 是**索引进 mined `scenes`**(`_stage_draft`:`scenes[idx]`)→ **source 出处不可变**(codex 的 Goodhart 核心地雷天然满足:planner 不能改源场景本身,只能选引用哪个 index)。
- `_stage_plan(..., force=True)` 重生 plan(现有 resume/force 机制)。`run()`:mine(1336)→plan(1346)→draft(1355) → **在 plan 与 draft 间插预起草门**。

## 目标 / 范围(v0.5)
在 plan 冻结后、draft 前,**接线**一个预起草门:**只硬拦 det `章节复制`**(带出处硬化)→ 触发**根因 regen 回路**(plan-rooted:重生 plan ≤2 次;仍不过 → **搁置**,跳过 60 章起草省钱)。**跨族 LLM 审仍是隔离/主动校准(D/E 上跑,不接线硬拒)**。产**审计数据**回答"regen 是否真修好"。

## 非目标(codex 地雷规避)
- **不硬拦 LLM 类目**(混名/人设崩/境界乱序 等)——精度仅 n=5,留 D/E 升格;v0.5 里它们**只隔离+进 watchlist**,不阻断管线。
- **不做 bible-rooted regen**(留 v1,需规范实体图)。注:`_stage_plan` 本就会 `enrich_places` 改 bible(现状行为),v0.5 regen 靠**每次从 mined bible 干净副本**重规划来隔离失败次的 enrich 累积、保 plan-rooted——不是"不碰 bible",而是"不新增 bible 级修复"。
- **不动 happy-path 字节**:不触发 `章节复制` 的书**照常 plan→draft**(与现状字节同)。
- 不接 10k 量产、不动冻结向量/gold 夹具。

## 架构

### 1) 预起草门检查 `predraft_gate_check(plan, scenes)`(接线,只 det 章节复制 + 出处硬化)
在 `predraft_checks.py` 加(复用 `duplicate_chapter_intent` 核):
- **同源复用**:不同 plan 章共享同一 `source_scene_index`(排除 -1)→ hard finding(现有逻辑)。
- **出处硬化(codex,防 Goodhart)**:coverage 账 —— 
  - **过度引用**:同一 mined 源场景被 >1 章引用(= 同源复用,上条)。
  - **躲避信号**:`source_scene_index` **缺失/None/-1/越界(<0 或 ≥len(scenes))全计 unsourced**(codex:v0 现有检查忽略缺失+-1);某章 unsourced 占比过高(阈 `unsourced_ratio_max`)→ warn(防 planner 用 -1/越界躲检测,不硬拦,记 watchlist)。
  - (语义级重复/typed-reason 例外[flashback/recap/POV] 留 v1;v0.5 只做 index 级 + coverage。)
- 返回 `{"blocked": bool, "findings":[...], "evidence": {...}}`;`blocked` = 有 `章节复制` hard finding。**schema 容错**:plan 缺 scenes/source_scene_index → 不 blocked、不崩。

### 2) 接线 `run()`:预起草门 + plan-regen 回路(codex regen 策略)
**codex 实证修正**:`_stage_plan(cli, bible, ...)` **原地 mutate bible**(`audit.enrich_places(bible, ordered)`)+ 重写 bible.json;`_stage_draft` `not force` 时**复用旧 `draft/ch_NN.md`**。故 regen 需 ① 从 **mined bible 干净副本**重规划(隔离 enrich 累积,保 plan-rooted)② regen 后 **draft 强制重跑**(否则旧草稿拼新 plan)③ refresh **所有** run() locals。

`_stage_mine` 后、首个 `_stage_plan` 前,快照 `bible_mined = copy.deepcopy(mine["bible"])`。`_stage_plan` 后、`_stage_draft` 前插:
```
gate = predraft_gate_check(plan, scenes)
regens = 0
while gate["blocked"] and regens < PREDRAFT_MAX_PLAN_REGEN:   # 默认 2
    regens += 1
    log(f"预起草门拦(章节复制) → 重生 plan 第{regens}次")
    bible = copy.deepcopy(bible_mined)                        # 干净副本 → 隔离上次 enrich, 保 plan-rooted
    pl = await _stage_plan(cli, bible, scenes, out_dir, n_ch, force=True)   # 原地 enrich 到该副本 + 重写 plan.json
    plan, beats, ordered = pl["plan"], pl["beats"], pl["ordered"]   # refresh 全部 locals(codex)
    n_scenes, macro = pl["n_scenes"], pl["macro"]; _ps = pl.get("stats", {})
    gate = predraft_gate_check(plan, scenes)
if gate["blocked"]:   # 达上限仍拦 → 搁置(source-rooted/顽固), 跳起草省钱
    return _predraft_shelved_report(out_dir, src, bible, gate, regens, cli)
draft_force = force or regens > 0    # codex#1: regen 后必重起草, 否则复用旧 draft/ch_NN.md 拼新 plan
d = await _stage_draft(cli, bible, scenes, p, plan, ordered, beats, n_scenes, n_cand, ..., force=draft_force)
```
- **根因(v0.5)**:det `章节复制` = **plan-rooted**(bible 不决定章-场景分配)→ plan-regen 对症。**每次从 bible_mined 干净副本**重规划,通过的那次的 enriched bible 进 draft;失败次的 enrich 不累积(codex#2)。bible-rooted 分类留 v1。
- **draft_force**:`force or regens>0`(codex#1)——保证 regen 通过后**重起草**,不复用旧草稿。
- **搁置 report 完整字段(codex rec,batch/web/normalize 容忍)**:`_predraft_shelved_report` 返 `{rejected:true, deliverable:false, "交付门":["预起草门:章节复制顽固(regen×N 未净)"], reject_why:同, predraft_blocked:true, predraft_regens:N, predraft_shelved:true, source:str, grade:mine 的 grade, cost_cny:cli.cost_cny, seconds:...}`;**不落 final.md**(normalize 见缺 final 跳过);产物落 `_rejected/` 同构。

### 3) 跨族审核 = 隔离/主动校准(D/E,编排,不接线)
D/E 档跑时,续 B/C 编排(det + Opus + GPT5.5 读 bible/macro/plan,冻结 prompt)→ 落 `output/validation/predraft/`。**语义变化**:
- **单评委 hard-fire = 隔离(quarantine)**:记 log + 证据包 + 根因标(plan/bible/source/unclear),**不阻断**。
- **双评委一致 hard-fire = 升硬拦候选**(供将来接线判据),仍不在 v0.5 阻断。
- `predraft_tabulate` 续算精度;**类目升硬门判据(codex)**:每类 ~20-30 例审计硬命中 + 双评委一致/或单评委+det 证据 + 逐类阈——**留 D/E 积累,v0.5 不升**。

### 4) 审计 / 统计(补"regen 是否真修好"的缺证据)
report 加字段 + 批量统计:
- `predraft_blocked`(bool)、`predraft_regens`(int)、`predraft_shelved`(bool)。
- **regen 成功率** = (regen 后 gate 不再 blocked 的本数) / (被拦本数)。
- **搁置率**、被拦本的**末态对照**(搁置的书没末态;regen 通过的书看末态 jury 是否比"若不 regen"更好——需 A/B 或影子对照,v0.5 记录 regen 前后 gate 状态 + 通过后末态 jury)。
- **关键审计**:regen 通过的书,det 是否真无 `章节复制`(硬检)+ 末态 jury 是否仍报注水(= regen 藏过检测器 vs 真修)。

### 5) 与末端门组合(codex:末端门降残余验证器)
- 末端门**不变**(仍查末态);predraft warn(躲避/LLM 类目)→ 末端门 **watchlist**(记录,不改末端门逻辑,v0.5 不接)。
- **分开统计**(codex):predraft 拦率/精度、regen 成功率、末端门 predraft 后拒率/假阳率、残余归因(bible/plan/draft/reviewer-miss)。
- **盲评 jury 路保留**(watchlist 不污染校准)。

## 验证
- **`predraft_gate_check` 纯函数单测**(`tests/test_predraft_checks.py` 扩):
  - 两章共享 source_scene_index → blocked=true + 章节复制 finding;无共享 → blocked=false。
  - 某章全 -1 占比超阈 → warn(不 blocked)。
  - plan 缺 scenes/source_scene_index → blocked=false 不崩。
- **`run()` 接线测**(`tests/test_stages.py` 或新,monkeypatch `_stage_plan` 桩):
  - gate 不 blocked → 照常进 `_stage_draft`(happy-path,不改行为)。
  - gate blocked→regen 后不 blocked → 进 draft,`predraft_regens=1`。
  - gate blocked 持续 → 达 `PREDRAFT_MAX_PLAN_REGEN` → 搁置(rejected report,**不调 `_stage_draft`**),断言 draft 桩未被调。
  - **happy-path 守卫**:gate 不 blocked 时,插入的门是 no-op → 与接线前同一路径进 `_stage_draft`(同 plan/bible/force)。**注(codex):gold/装配回归网不端到端跑 `run()`**(只测 gate 夹具 + 事实表装配)→ happy-path 保真靠**本 run() 接线测**(断言 gate 不 blocked 时 `_stage_draft` 入参与接线前一致),非 gold/装配网。
- **regen 幂等/成本**:regen 用 force,不复用旧 plan;搁置省 draft(断言 draft 未调)。
- 全量 `pytest -m 'not api'` 绿;SDD(逐任务 TDD + 两段复核 + opus 终审)。

## 风险 / 地雷(codex)
- **Goodhart(det 出处)**:source 出处不可变(mined scenes 冻结)已挡"重排 ID";残留=planner 用 -1 躲 → coverage 账(躲避信号 warn)。语义级重复留 v1。
- **regen churn**:上限 2 + 搁置(不无限重掷);审计 regen 是否真修(det 硬检 + 末态 jury 对照)防"藏过检测器"。
- **plan-rooted 假设**:v0.5 只对 det `章节复制` 接线,它确 plan-rooted(bible 无关章-场景分配)→ plan-regen 对症。LLM 类目(可能 bible-rooted)不接线,规避"在坏 bible 上重 plan 复现"。
- **行为改变(有意)**:被拦顽固书从"起草+末端拒"变"预起草搁置"(省钱、对症);happy-path 字节不变(守卫测)。
- **末端门双拒混淆**:predraft warn + 末端拒同一类 = predraft 未拦/regen 失败,不算末端缺陷(分开统计)。
- **升格纪律**:LLM 类目**不在 v0.5 硬拦**(精度 n=5 薄);D/E 积累 ~20-30 例 + 双评委一致才升。

## 诚实边界
v0.5 = **只硬拦 det 章节复制 + 建/测 regen 回路 + 跨族隔离校准**。产出=**"门拦→plan-regen→是否真修好"的首批证据** + D/E 校准续。LLM 类目接线硬门、bible-rooted regen、规范实体图 = **v1**,需 v0.5 的 regen-成功证据 + D/E 精度支撑,另立 spec。

<!-- codex-peer-reviewed: 2026-07-01T01:58:14Z rounds=2 verdict=approved -->
