# E3 Stage-0 系统测试协议(3 本 · 三模型陪审团)

> 2026-06-29 · codex 方法论讨论 + 源/评分机制核实后定稿。配套 memory `e3-stage0-system-test`、`e3-calibration-direction`。**定位:Stage 0 = 管线试运行 + canary + 种第一批可拟合行,不是交付验证。任何 3 本结果都不批准 10k。**

## 目标(诚实分级)
1. **管线试运行**:3 本端到端跑通,验证 Slice 1b 的 `engine_commit` + frozen `signals` 在真 `report.json` 落盘、`hfl_ingest` 干净产 fittable 行。
2. **canary**:门 `deliverable` vs 三模型陪审团判定的粗暴分歧(尤其放行坏书 = 假阳性)。
3. **种数据**:3 本 × 3 评委 = 9 条 frozen proxy 行入 `hfl.jsonl`(各模型自有 proxy 真值空间,非 `网文编辑` ground truth)。

**不是**:交付验证 / 拟合模型 / 批准 10k。真交付门 = 第二阶段 ~12–20 本新鲜盲评(排除 10% 假阳率需 ~30)。

## 评委(跨族双模型,无人评本轮)
- **Opus 4.8**(=Claude 本体,session 内 subagent 直读 final.md 评)
- **GPT-5.5**(=`codex exec` 喂 rubric + final.md)

> **2026-06-30 更新:移除 Deepseek 评委。** 本轮结果实证 deepseek(=管线作者模型)评自己写的书系统性 +30 分自评偏(全 yes/72-83 vs 跨族 27-56),= 假信号 → 同族自评不可作 proxy。陪审团只保留**跨族** Opus4.8 + GPT5.5(旧 `scripts/jury_grade.py` deepseek 腿已删)。

两个不同模型家族 = 独立盲点 + 可 scale。**局限(明确记下)**:无人锚 → 本轮不校验"陪审团是否对齐人类口味";circularity 仍在(门按人编辑旧批调,陪审团是另一口径)→ 这测"时间复制+管线健康",非独立质量证据;双评委仍有尺度差(GPT5.5 比 Opus 狠~20),需校准。

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

**③ 双模型盲评**(每本 final.md,各模型独立,**不给**门结果/signals/选书理由):用下「盲评 prompt」。产物 = `output/stage0/jury/<slug>__<model>.json`。Opus 腿=并行 subagent 直读;GPT5.5 腿=`codex exec`。(Deepseek 腿已移除,见评委节。)

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

---

## 结果(2026-06-30 跑完)

**跑**:3 本 ¥23.5 / 均 ¥7.83 / 墙钟 ~93min。门判:边缘✓ / 典型✗ / 弱✗(典型+弱栽残缝>8,边缘残缝6过)。
**评**:三模型盲评全本 final.md(各 9 评)。

| 书 | deepseek(同族·自评) | Opus(跨族) | GPT-5.5(跨族) | 门 | 陪审多数 | IRR极差 |
|---|---|---|---|---|---|---|
| 典型 误嫁豪门 | 83.0 **yes** | 53.3 no | 28.5 no | 拒 | **no (2/3)** | 54.5 |
| 弱 禁欲上司 | 72.8 **yes** | 47.4 no | 26.6 no | 拒 | **no (2/3)** | 46.2 |
| 边缘 符术师 | 82.5 **yes** | 55.8 no | 37.8 no | **过** | **no (2/3)** | 44.7 |

跨族评委查出的承重硬伤(门未拦):典型=认亲线矛盾/生父改名/生年差10岁/男主结局突变歌手/29章整段复制;弱=DNA两次99.99%互斥/胎记四变/整章注水;边缘=境界忽高忽低于灵王/修为倒退/结尾性别男变"她"/云诺楚诺混名/三年闭关重复。

## Go/No-Go 判读
- **✅ 管线通过**:3/3 `report.json` 带 `schema_version=1` frozen signals + `engine_commit=541727e`(Slice 1b 真跑验证成立)。
- **🔴 硬阻塞(命中)**:边缘 符术师 门 `deliverable=true`,陪审团多数(Opus+GPT5.5)判 **no** + 查出境界乱序/修为倒退/性别错 = **门假阳性**(放行坏书,头号风险)。门自报 2 处死人复活却"beat已渲染"降级放行,且境界/修为硬伤未拦。
- **🟠 测量阻塞(命中)**:IRR 极差 45-55 分 → 陪审团非决策级。**deepseek 同族自评全 3 本 yes/72-83,跨族 Opus/GPT5.5 全 no/27-56** → 作者模型自评 +30 分系统偏,不可作 proxy;且跨族两评彼此也差 ~15-25(GPT5.5 普遍比 Opus 狠 ~20)。

## 结论
**Stage-0 ≠ pilot-pass。不进 12-20 批,更不进 10k。先修两处:**
1. **门漏承重硬伤**:残缝门拦对了典型/弱(方向对),但边缘的境界乱序/修为倒退/改名/性别错/整章复制 = C2 PowerLedger / C1 RevivalLedger / 章内复制 域,门当前 spine/seam 检测**召回不足**,把这些放过了。
2. **AI-jury proxy 不可用同族自评**:deepseek 评 deepseek = 自我吹捧;只能用跨族(Opus/GPT5.5),且需校准两者尺度差。→ 印证 E3 测量危机:廉价同模型自动评分 = 假信号。

---

## #1 门假阳根因诊断(2026-06-30, opus 深挖 stage0_edge)

门"看见"的:signals `spine_num_contra=2 / spine_id_contra=0 / ft_revival_residual=0 / intra_repeat=0 / reenact=1 / seam_residual=6`,全低于阈值(`spine_net_min=6`/`seam_residual_max=8`)→ 0 ship_issue → 过。**评委的 5 类硬伤门信号里几乎全无体现 = 召回缺口为主,非降级误判。**

| 硬伤 | 责任检测器 | 进门 | 根因 | 性质 |
|---|---|---|---|---|
| 境界矛盾(大灵师↔灵王) | `power_order_from_bible` (audit.py:255) | 否 | **读错 bible 字段**:读 `escalation_ladder`(剧情弧)非 `power_system`(真境界梯灵徒→…→灵圣);默认梯无"灵*"词→`_power_rank` 全 -1→None→PowerLedger 永不记录 | 🔴召回(单bug) |
| 修为倒退(灵王→灵师) | 同上 + prose `cross_check` power | 否 | plan 层同上;prose 层只有 numeric 账本(`_num_of`),**无序数/境界账本**→realm 零覆盖 | 🔴召回(单bug) |
| 结尾性别错(落羽 男→她) | `continuity_check` | 否 | 三重洞:只读 `final[:8000]`(全书21万字,结尾在窗外)+ 只问主角(落羽配角)+ 即便检出也只 advisory(`block_on_final_inconsistent=False`);全角色性别一致性**无检测器** | 🟠整类无检测器 |
| 混名(云诺/楚诺同人) | 异名归一 + 身份 cross_check | 否 | 身份表按 `who` 建,检"一名多角色",**共指(多名同一人)结构上检不了**;`verify_identity` 因 `spine_net_num>=2` 短路never跑(produce.py:1119) | 🟠整类无检测器 |
| 整章/桥段重复(闭关演两遍) | `_intra_repeat`/reenact/邻章 | 否 | `_intra_repeat`=单章内逐字12-gram(跨章/语义改写重复逃逸);reenact 窗口仅前3章且 advisory | 🟠语义层逃逸 |

**根因排序(最该补在前):**
1. **🔴【最高·单bug低成本】power 序数检测器读错字段** — `audit.py:255` 读 `escalation_ladder` 应读 `power_system` + 补"灵*"梯 + prose 加序数 power 账本。**一处修同时让境界矛盾+修为倒退两条最重承重硬伤显形。** = C2 PowerLedger 召回缺口的真根因(印证 hfl 老毛病"中文境界串排不了"实为读错字段)。
2. 🟠 全角色性别一致性 — 整类无检测器(continuity 只读前8000字+只问主角)。
3. 🟠 名字共指(同人多名) — 整类无检测器 + verify_identity 短路。
4. 🟠 语义/跨章重复 — 仅单章逐字 + reenact 窗口3。
5. 🟡【调参非召回】spine_net_min=6 偏高 / verify_identity 短路 / 生死 beat 降级。

诚实:本例测不准主体 = 检测器**漏检**(尤其 #1 单 bug),非降级误判。

---

## 修复进度
- **#1 power 境界检测器(根因①)✅ 已修(2026-06-30, master 23c8f2c)**:`power_order_from_bible` 改读+解析 `power_system`(异构散文/`_NON_REALM`/<3→None)+ `_realm_rank`(default优先/custom补默认未知境界灵*)接入 check/fix。plan 层 `fix_power_monotonic` 预防对真境界梯生效(境界乱序/修为倒退现钉回);检测零退化、不误钉(codex spec r3+plan r2+opus 终审,实跑8本bible+434全量绿)。spec/plan: `docs/superpowers/{specs,plans}/2026-06-30-power-realm-detector-fix*`。**残**:#2 性别/共指/语义重复(整类无检测器)+ #2/B prose 序数门检(drafting 新引入残留)。
