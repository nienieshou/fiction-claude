# E3 验证块(真书阶梯)设计 — 用证据替代推测性检测器

> 2026-06-30 · 上帝视角复盘共识(拉 codex)结论:#1 power 修复后继续建 2a/2b/2c 检测器相对头号风险(测不准)是"假性努力"。**本设计 = 战略转向的落地**:冻结 #1 后管线 → 跑分层真书阶梯 → 产"失败模式 频率×严重度"表 → 由表决定建哪个检测器(而非拍脑袋)。基于 `master`(#1 已合,engine 含 power 修复)。`assets/hfl.jsonl` 已起种(opus×3 + gpt55×3 = 6 条可拟合跨族行,见末尾"已落地")。

## 目标 / 范围
拿**决策级证据**回答四问,据此决定后续检测器优先级(或停建):
1. **#1 修复后的门还假阳吗、为什么** —— gate `deliverable=true` 但跨族 judge 判 `deliver=no`/低分 = 假阳候选。
2. **门-质量分离度** —— 门放行的书是否真比门拒的书在 judge 眼里更好(分差)。
3. **失败模式 频率×严重度表** —— 跨真书统计每类硬伤(境界乱序/修为倒退/性别错/混名/复活/注水重复/认亲矛盾…)的出现频率 + 严重度 + 门是否抓到。
4. **首批可拟合校准行 + judge 可靠性** —— 每跑一本 emit 冻结 signals → ingest 喂飞轮;同时量 Opus vs GPT5.5 的离散与系统偏置。

**非目标**:不建任何新检测器(2a/2b/2c 暂停,2a spec 留档);不改 gate/检测器/冻结向量/gold/装配网;不引入人评(本阶段 AI-only);不下单一"交付合议"判(见下)。

## 阶梯 + 梯间 go/no-go(累积,非独立批)
| 档 | n(累积) | 角色 | 选书 |
|---|---|---|---|
| A | 3 | pipeline 烟雾 + 直验 #1 | 重跑 Stage-0 三本(误嫁豪门/危险关系/第一符术师)于 #1-修复引擎 |
| B | 5 | 烟雾续 | A + 2 本预登记鲜书 |
| C | 8 | **首决策门** | B + 3 本预登记鲜书 |
| D | 13 | 中检 | C + 5 本 |
| E | 21 | **频率估计目标**(≈codex 战略 20) | D + 8 本 |

**梯间 go/no-go**(每档评分后判一次,决定停/升):
- **A/B(烟雾)不下频率结论**,只验:① #1 是否治了 edge(符术师)的境界乱序/修为倒退 — 修前门放行+jury 拒,修后期望境界硬伤减少;② 管线 + jury harness 端到端跑通。A 若 #1 未见改善 → 记录,仍可升(detector 残留推后判),但触发对 #1 边界的复盘。
- **C(n=8)首决策门(codex 规则)**:门放行书中若 **≥2 本** 被**任一**跨族 judge 判 deliver=no/显著低分(假阳)→ **门非交付安全 → 停止升档,转去修门/上游**(而非继续烧 13/21)。否则升 D。
- **D→E**:若某失败类已在 ≥20% 本出现或已致一次假阳 → 标记该类为"建检测器/上游修候选"。E 出齐 21 本的频率×严重度表。
- **任何档**出现决定性证据(门清晰不安全 / 某硬伤压倒性高频)即可早停,省 API。**早停或截断必须 `log` 记录丢了什么**(codex:别静默截断成"看似全覆盖")。

## 选书 / 分层(预登记)
- **A/B/烟雾**:重跑 Stage-0 三本(现言×2 + 玄幻灵气×1);B 的 +2 见预登记表。
- **C/D/E 鲜书**:从 `fictions_source/`(51 本池,已按题材归 9 个文件夹,见 `fictions_source/README.md`)**预登记**抽,约**一半 production-随机** + **一半风险富集**。风险富集 ≈ 玄幻仙侠/传统武侠/末世科幻 + 部分种田基建(境界梯/大世界观/长连续性弧/大角色群);production-典型 ≈ 现代言情/年代纪实/都市异能。风险标签按上述跨题材特征单独打,不等同题材文件夹。
- **预登记纪律**:选书清单(slug→source)在**看到任何产物前**冻结进 `validation_tasks.yaml` 并提交;**不挑讨好门的书**(codex)。本 spec 附预登记表(实现时填池内确定性抽样:按题材前缀分层 + 固定序,不用随机数避免不可复现)。
- 重跑 Stage-0 三本是有意复用(直验 #1),非"挑好书"——它们本就是 Stage-0 预登记的分层样本。

## 跑书 harness(复用现有,零新管线)
- 入口:`python -m hiki run --tasks-file validation_tasks.yaml --parallel N --spine`。
- 每本参数对齐 Stage-0:`chapters: 60, refine_rounds: 3, best_of: 1`。引擎 = 当前 master(含 #1)。
- 每本产 `report.json`(含冻结 `signals` + `engine_commit`)、`final`/`scenes`、`fact_table.json`、`grade.json`。门判 = `report.signals.deliverable` —— **评分前先冻结门判**(记录下来,judge 不可见)。

## 评分(盲评 · 双跨族评委 · 各自独立报)
- **评委**:Opus 4.8 + GPT 5.5(**弃 deepseek** — 同族自评 +30 偏,已验)。
- **运行方式**(非纯脚本,由编排执行):
  - Opus 4.8:派一个**子代理**(Agent),喂"成品文本 + story4 rubric prompt",返回 story4 JSON。
  - GPT 5.5:`codex exec --sandbox read-only`,同 prompt + 文本,返回 story4 JSON。
  - **盲**:judge 只见成品文本,**不见**门判 / 检测器命中 / 模型身份 / 先验期望。
- **rubric**:`story4` 四维(故事性 0.3 / 笔力 0.25 / 人 0.25 / 承重 0.2,0–100)+ `deliver`(yes/no)+ `reject_reason` + `comments`(致命点要带证据/章号)。schema 与现有 jury JSON 逐字一致(`calibration.RUBRIC_WEIGHTS['story4']`)。
- **合议规则 = 无(本阶段)**(用户 2026-06-30 拍板):GPT5.5 系统性比 Opus 严 ~18–25 分(Stage-0 实测),强行合议过早。每本**独立**记 {门判, Opus 分+deliver, GPT5.5 分+deliver, 失败模式},不塌缩成单一交付判。`|Opus−GPT5.5|>15` 的本**单列"分歧桶"**。
- **存储**:每 (book, judge) 落 `output/validation/jury/<slug>__<judge>.json`(对齐 Stage-0 格式);scorecard YAML → `hfl_ingest.py` 入 `assets/hfl.jsonl`(冻结 signals 内联 → 可拟合;dedup 幂等)。

## 产出指标(tabulator,新工具)
新增 `scripts/validation_tabulate.py`(手动跑,纯读盘 report.json + jury JSON,不调 API):
- **假阳候选表**:门 deliverable=true 但某 judge deliver=no 或分<阈 的 (book, judge, 分, reject_reason)。
- **门分离度**:门放行组 vs 门拒组的 judge 分均值/分布差;若放行组不显著高于拒组 → 门无分离力。
- **失败模式 频率×严重度表**:从所有 reject_reason/comments 归类硬伤(初始类目:境界乱序、修为倒退、性别错、混名/认亲矛盾、死人复活、章节复制/注水、DNA/身世互斥、人设崩、现代腔出戏),统计 {出现本数/总本数=频率, 平均承重扣分=严重度代理, 门是否抓到}。归类由人/编排读 comments 打标(本阶段 advisory,不求自动化)。
- **judge 可靠性**:每本 `Opus−GPT5.5` 分差(IRR)、系统偏置(均值差)、方向一致率(deliver 同判率)。
- 每档输出一张快照(A→E),go/no-go 判据见上。

## 验证(本设计自身怎么算对)
- **tabulator 纯函数单测**(`tests/test_validation_tabulate.py`):
  - 假阳判定:门=true + judge deliver=no → 进假阳表;门=true + judge yes → 不进。
  - 分离度:构造放行组分>拒组分 → 正分离;反之/无差 → 标无分离力。
  - 频率×严重度:给定多本 reject_reason 标签 → 正确计频率 + 严重度聚合。
  - 边界:0 本门放行 → 假阳率 N/A 不崩;judge JSON 缺字段 → 跳过不崩。
- **jury 编排无单测**(涉真 API/子代理),靠盲评协议 + schema 校验(story4 四维齐、0–100、deliver∈{yes,no})在落盘时把关;不合规的 judge 输出拒收并记录。
- **ingest 复用** `hfl_ingest.py` 既有路径(已验:本 spec 落地段 6 条已入,0 跳过)。
- 全量 `pytest -m 'not api'` 绿。tooling 走 SDD(逐任务 TDD + 两段复核 + opus 终审)。

## 诚实边界(写进最终报告)
- **AI-only + 无人锚**:deliverable 是 AI judge 口径,非 ground-truth;Stage-0 网文编辑 14 行仍不可拟合(评的是无冻结向量旧产物)→ "信号↔真值"桥本阶段仍空。
- **小 n + ~20 分 judge 分歧**:频率估计在 n=8 噪声大(20% 率≈1.6 本),n=21 才勉强可排序;分离度/假阳率结论带宽误差带。报告须标每个指标能下多硬的结论,不夸大。
- **引擎版本**:Stage-0 6 条种子行的 signals 来自 #1 前引擎(`541727e0`),与本块(#1 后)不同版本 → 种子行作"信号↔评分"起点,不混入"当前门相关性"判定。

## 风险
- **judge 偏置主导**:GPT5.5 偏严 → 若误用 both≥80 会假性高拒;本阶段不合议规避,只报分布。
- **选书偏置**:不预登记/挑好书 → 假阳率虚低。预登记 + 半风险富集规避。
- **归类主观**:失败模式标签靠读 comments 人工打 → advisory,留作后续校准;不进门。
- **成本**:21 本全 60 章 ~¥150 + jury(Opus 子代理 + GPT5.5 codex)。阶梯 go/no-go 早停控成本。
- **harness 偏差**:验证块用与 Stage-0 同参(60/3/1)→ 与 10k 量产参数若不同需另标;本块结论限定在该参数。
