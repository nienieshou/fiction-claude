# E3 Stage-0 系统测试协议(3 本 · 三模型陪审团)

> 2026-06-29 · codex 方法论讨论 + 源/评分机制核实后定稿。配套 memory `e3-stage0-system-test`、`e3-calibration-direction`。**定位:Stage 0 = 管线试运行 + canary + 种第一批可拟合行,不是交付验证。任何 3 本结果都不批准 10k。**

## 目标(诚实分级)
1. **管线试运行**:3 本端到端跑通,验证 Slice 1b 的 `engine_commit` + frozen `signals` 在真 `report.json` 落盘、`hfl_ingest` 干净产 fittable 行。
2. **canary**:门 `deliverable` vs 三模型陪审团判定的粗暴分歧(尤其放行坏书 = 假阳性)。
3. **种数据**:3 本 × 3 评委 = 9 条 frozen proxy 行入 `hfl.jsonl`(各模型自有 proxy 真值空间,非 `网文编辑` ground truth)。

**不是**:交付验证 / 拟合模型 / 批准 10k。真交付门 = 第二阶段 ~12–20 本新鲜盲评(排除 10% 假阳率需 ~30)。

## 评委(纯三模型,无人评本轮)
- **Opus**(=Claude 本体,session 内直读 final.md 评)
- **Deepseek**(=管线 client,`scripts/jury_grade.py` 调,模型走 models.yaml)
- **GPT-5.5**(=`codex exec` 喂 rubric + final.md)

三个不同模型家族 = 独立盲点 + 可 scale。**局限(明确记下)**:无人锚 → 本轮不校验"陪审团是否对齐人类口味";circularity 仍在(门按人编辑旧批调,陪审团是另一口径)→ 这测"时间复制+管线健康",非独立质量证据。

## 选书(按质量档分层,非题材)
11 本新鲜源(不在 gold/hfl):DYBXS00073 / ZTGGY02038 / ZTGGY02336 / ZTGGY03708 / ZTGWM01838 / ZTGXY01825 / ZYGGX02936 / ZYGXN02142 / ZYGXY01824 / ZYGXY01876 / ZYGXY01893。

**选 3 规则(pregrade 后定,预登记 ID)**:
- **1 典型**:pregrade 中档(B/A,贴 10k 主体分布)。
- **1 脏/低质**:低档(D/Q 或 `protagonist_arc=无/表面`、`content_flag≠无`)—— 专钓假阳性。
- **1 边缘**:会真出现在 10k 的高风险结构(如多线/虐恋,hfl 实测 承重 偏低),但**仅当该类确属 10k 语料**,否则换另一中档(避题材混淆)。

题材**不**作分层轴(失败归因混淆:门坏/改写坏/源难/没见过的题材?)。

## 阶段命令

**① pregrade(分层,~¥1/本):**
```powershell
$env:PYTHONPATH = "src"
python -m hiki.pregrade fictions_source/DYBXS00073* fictions_source/ZTGGY02038* fictions_source/ZTGGY02336* fictions_source/ZTGGY03708* fictions_source/ZTGWM01838* fictions_source/ZTGXY01825* fictions_source/ZYGGX02936* fictions_source/ZYGXN02142* fictions_source/ZYGXY01824* fictions_source/ZYGXY01876* fictions_source/ZYGXY01893* --parallel 3
# 看 output/pregrade_map.md: grade / protagonist_arc / dark_ratio / content_flag → 按上规则挑 3,预登记到本 doc「预登记」节
```

**② 跑 3 本(~¥6–22/本,~7 分钟/本):** `tasks.yaml`(slug 用预登记 ID):
```yaml
tasks:
  - {slug: stage0_typical, source: fictions_source/<典型>.txt, out: output/stage0, chapters: 60, refine_rounds: 3, best_of: 1}
  - {slug: stage0_dirty,   source: fictions_source/<脏>.txt,   out: output/stage0, chapters: 60, refine_rounds: 3, best_of: 1}
  - {slug: stage0_edge,    source: fictions_source/<边缘>.txt, out: output/stage0, chapters: 60, refine_rounds: 3, best_of: 1}
```
```powershell
python -m hiki run --tasks-file tasks.yaml --parallel 2 --spine
# 看 output/batch_summary.md: 成功/可交付/拒收 + 成本
```
> **阈值冻结**:跑前不得改 `config/pipeline.yaml ship_gate` / `gate.SHIP_GATE_DEFAULTS`。跑完更不得"调阈值再叫验证"。

**③ 三模型盲评**(每本 final.md,各模型独立,**不给**门结果/signals/选书理由):用下「盲评 prompt」。产物 = `output/stage0/jury/<slug>__<model>.json`。`scripts/jury_grade.py`(Deepseek 腿)待 ② 后建。

**④ IRR + ingest**:三评委每本算总分极差(IRR);转 `scorecard_*.yaml`(每模型一卡)→ `python scripts/hfl_ingest.py output/stage0 --round stage0-jury --write`(产 9 条 frozen proxy 行)。

## 盲评 prompt(成品 4 维,从 rubric_260625)
```
你是网文成品质检评委。只读下方成品正文,按 4 维打分(0-100),不臆测来源、不假设任何机器判定。
维度与权重: 故事性30%(钩子/爽点/章末驱动/追读欲) 笔力25%(去AI腔/对话/画面感/辨识度)
           人25%(魅力/代入/主动性/成长弧) 承重20%(结构连续/世界观/记忆点/抗注水)
承重专项一刀: "这段重复删掉剧情有无损失?" 无损=注水(扣); 有损=良性套路(不扣)。
另给二元交付判定(不靠总分): deliver ∈ {yes, no, gray}
  yes=可直接交付编辑; no=有硬伤必须拦(前后矛盾/死人复活/暗黑越线/逻辑断裂/大段注水); gray=拿不准。
输出 JSON: {"故事性":int,"笔力":int,"人":int,"承重":int,
            "deliver":"yes|no|gray","confidence":int(0-100),"reject_reason":str(<=40字,deliver≠yes时填),
            "comments":str(<=120字: 各维一句最致命)}
只输出 JSON。
```
(权重总分由 `hfl_ingest`/`calibration.rubric_total` 用 standard4? 否 —— 本 prompt 用 rubric_260625 的「故事性」轴 → story4 权重表。ingest 时 scorer=模型名 → 非 editor → 允许 story4。)

## Go/No-Go 判据
- **管线通过**:3 本跑完 · `report.json` 有 `schema_version` frozen signals + `engine_commit` · 评分干净 ingest 成 fittable 行(零手补)。任何手补/缺信号/不可复现/源-run 链断 = **管线 fail**。
- **🔴 硬阻塞**:任何 `deliverable=true` 的书被陪审团**多数判 `deliver=no`**(放行坏书 = 头号风险)。
- **🟠 测量阻塞**:2+ 本陪审团多数 `gray`,或三评委总分极差普遍 >15(IRR 差)→ 评分协议/prompt 不够决策级。
- **🟡 门保守**(非质量阻塞):门拒但陪审团多数 `yes` → 成本/覆盖问题(质量>成本下可接受,记录)。
- **✅ pilot 通过**:无假阳 + 无管线故障 + 标签不多为 gray + IRR 可接受 → **仅授权下一批(12–20 本新鲜盲评)**,**不**授权 10k。

## 预登记(2026-06-30 锁定,跑前)
> 现实:11 本新鲜源 pregrade = 10 A + 1 B 全 `真实` 弧 → **无真低质源**(pregrade 本就是 10k 准入过滤,A 源即代表性)。故分层轴改为**结构风险 + 最低可得档**(承重崩坏 = hfl 头号失败模式),非源质量。

| 角色 | 源 ID | grade/暗黑 | 选因 |
|---|---|---|---|
| 典型 | `ZTGXY01825误嫁豪门，战神老公蓄意偏宠` | A / 0.0 | 现代军婚甜宠虐渣 = 10k 主体线性言情;代表大多数 |
| 弱/脏 | `ZYGXY01824危险关系：禁欲上司夜痴缠` | **B** / 0.0 | 唯一 sub-A;狗血虐恋套路化 + 主角初期被动 = 最弱档 |
| 边缘 | `ZYGGX02936第一符术师` | A / 0.17 | 修仙系统拆章 = hfl 实测承重头号杀手(邻章重演/修为乱序);承重假阳诱饵 |

轴:档(B vs A)× 结构(线性甜宠 vs 修仙拆章)× 暗黑(0 vs 0.17)。配置:`stage0_tasks.yaml`(chapters60/refine3/best_of1)。pregrade 全量见 `output/pregrade_map.md`(总¥9.47)。
