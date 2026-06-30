# PreDraft Review v0(上游跨族预起草审核 · 校准门)设计

> 2026-06-30 · A 档证据(`docs/design/e3-validation-A-results.md`:**~85% 实测硬伤可从 bible/plan 预测**,唯性别错/复活是起草新引入)+ codex 设计评共识。
> **本设计 = 校准门 v0,不是生产级 auto-reject,不是 auto-fix canon。** 目的:学到**哪些上游 findings 精到可拦**(而非证"85%真不真")。折进验证块 **B 档**跑。基于 `master`。

## 目标 / 范围
在 bible/macro/plan 冻结后、**起草 60 章前**,对这些工件跑**预起草审核**,产**结构化 findings**(带证据/引用/置信/严重度)。v0 重点 = **校准**:量各类 finding 的**精度**(尤其硬拦类),为将来真接入管线门提供依据。
**折进 B 档**:B 档(+2~3 本)跑时,每本在 plan 冻结后跑本审核;**v0 不改 produce.run 起草流**(候选工件照常进起草),只**旁路产 findings + 校准数据**——避免在精度未知前做破坏性管线手术。

## 非目标(codex 地雷规避)
- **不 auto-fix bible/plan**(LLM 改 canon 会引新错 + 掩盖 planner 是否真在改善)。
- **不纯 advisory**(10k 下成人力瓶颈)——但 v0 阶段尚不真硬拦管线,先校准。
- **不替代末端门**(15% 起草新引入硬伤——性别错/复活措辞——上游看不出,仍需末端门)。
- **不判文笔/taste**——只判**结构性、可引用、闭类**的矛盾(否则沦为又一个 pseudo-detector)。
- 不接入 10k 量产、不动冻结向量/gold。

## 架构

### 1) 确定性预检 `predraft_checks`(新纯函数 · **启发式解析已知 prose 模式**,非 typed schema)
**codex 实证更正**:真 bible **无 typed 亲属/血型字段** —— 亲属在 prose `characters[].key_relation`(如 `"苏媚禧生母"`),血型在松散 `facts[]`(如 `{"item":"苏媚禧血型","value":"AB"}`),境界引用多在自由文本。故确定性层 = **对这些已知 prose 模式做保守正则解析**(命中即高精度,但召回受措辞限制),**不是闭类 typed 机判**。v0 只收**两个最可解析、最高精度**的:
- **亲属唯一性**:正则扫 `characters[].key_relation` 抽 `(本名)(生母|生父|亲生母亲|亲生父亲)` → 按 (目标人, 角色) 归并 → **同一人同一唯一角色被 ≥2 个不同角色声称** → 硬伤(A 误嫁豪门:方欣+李诗蕊 都 key_relation~"生母")。
- **重复章意图**:聚合 `plan.chapters[].scenes[].source_scene_index`(**codex 更正:在 scene 级,非 chapter 顶层**)到每章 → **不同章共享同一源场景集** → 硬伤。
- 每命中产 finding:`{category, severity:"hard", evidence_path(JSON路径), contradiction(具体矛盾), confidence:"det", parse_pattern(命中的正则/字段)}`。
- **schema 容错**:`key_relation`/`scenes`/`source_scene_index` 缺失 → 跳过该检查不崩(镜 A3/loader 教训)。
- **诚实**:这是启发式解析,**精度高但召回受 prose 措辞限制**;血型 Punnett、境界阶梯完整性因需跨 `facts[]`+亲属 join / 自由文本抽取,**移到 LLM 层**(下条),不冒充确定性。

### 2) LLM 预起草审核(编排,非管线;3 路)
对每本 bible/macro/plan(JSON),各自独立审,产结构化 findings。**LLM 层负责确定性层接不住的**(需跨 `facts[]`+亲属 join 或自由文本抽取):**血型 Punnett 不可能**、**境界阶梯完整性**(plan/macro 引用境界全在阶梯内 + "封顶/最高"声明与已现等级不矛盾;可把 `audit.power_order_from_bible` 解析出的阶梯喂给 LLM 作锚)、**时间线/身世链矛盾**、混名/认亲、现代腔等。
- **DeepSeek 自审**(消融对照):验同族能否抓到——若 DeepSeek 自审召回≈跨族,则跨族非必需(省钱);否则跨族保留为权威。
- **跨族 Opus 4.8** + **跨族 GPT 5.5**(各一):权威。
- 提示词冻结(`docs/superpowers/specs/predraft-review-prompt.md`):**只判结构性矛盾,必须引用 bible/plan 的具体路径/字段**;含糊无引用的 finding 拒收。
- **题材例外**(codex):修真阶梯/重生/血缘秘密/别名/女扮男装/变身 等**可解释例外**不得当矛盾报——提示词列例外白名单 + finding 须排除"已被设定解释"的情形。
- findings schema(同确定性):`{category∈失败类目, severity:"hard|warn", evidence_path, contradiction, confidence:"高|中|低", recommended_action}`。

### 3) 严重度分级(codex)
- **hard(硬拦候选)**:闭类、带证据的结构矛盾(亲属/血型/境界阶梯/重复章/时间线/身世互斥)。**调精度**。
- **warn(警告/watchlist)**:软风险(现代腔、软人设、可解释题材惯例)。**担召回**,传末端门 watchlist。
- v0 **不真拦**(候选工件照进起草);severity 只标注,供校准。

## 校准协议(v0 核心产出,折进 B 档)
对 B 档每本:
1. 跑确定性预检 + 3 路 LLM 审 → 全 findings 落 `output/validation/predraft/<slug>__<reviewer>.json`。
2. **候选工件照常起草**(不因 findings 改 plan)→ 末态 jury(同 A 流程)。
3. **对照**:pre-draft 预测的硬伤 vs 末态 jury 实测硬伤(复用 A 的"上游可拦率" + 按类目)。
4. **精度量化(关键)**:对每个 hard finding,看其预测的硬伤**末态是否真兑现** → 该类目**精度**(真阳/(真阳+假阳))。**反事实盲规避**:因 v0 不改 plan 照跑,每个 flagged plan 都有"未改的末态"可量假阳(= codex 的 audit holdout,这里天然全 holdout)。
   - **caveat(codex)**:此精度量的是"**预测了末态实际兑现的硬伤**",非"plan 内部是否自洽"——一个真实的 plan 矛盾可能被起草/精修意外掩盖而末态不现,会被记为假阳(保守低估精度)。这正是 v0 要的:**对管线门有用的是"末态会出事"的预测力**,不是"plan 纸面矛盾"本身。
5. **DeepSeek 自审 vs 跨族**:按类目比召回/精度,判跨族是否必需。

产出表(扩 `validation_tabulate` 或新 `predraft_tabulate`):
- 各类目 hard finding **精度**(按 reviewer:det / deepseek / opus / gpt55)。
- DeepSeek-自审 vs 跨族 召回/精度差。
- 上游可拦率(承 A)+ 风险寄存器(每本 invariants + warn watchlist + 引用)。

## 与末端门组合(codex,v0 只产数据不接线)
- 风险寄存器 schema 定义好(`{invariants:[...], watchlist:[...], citations:[...]}`),**v0 产出但不喂门**;待精度校准够再接。
- 末态硬伤**归因**:每个标 `上游源 / 起草引入 / 门漏`(扩失败模式表)。

## 验证(本设计自身怎么算对)
- **`predraft_checks` 纯函数单测**(`tests/test_predraft_checks.py`)——只测确定性层(亲属+重复章):
  - 亲属唯一性:两角色 `key_relation` 同含 "X生母" → 命中;唯一 → 不命中;`key_relation` 缺失 → 跳过不崩。
  - 重复章意图:plan 两章的 `scenes[].source_scene_index` 集合相交 → 命中;`scenes`/`source_scene_index` 缺 → 跳过不崩。
  - findings schema 合法(category/severity/evidence_path/confidence/parse_pattern 齐)。
  - (血型 Punnett / 境界阶梯完整性 已移 LLM 层,**不在确定性单测内**。)
- **LLM 审无单测**(真 API/编排):靠提示词 schema 校验(finding 须带 evidence_path,否则落盘拒收)。提示词工件 `docs/superpowers/specs/predraft-review-prompt.md` 为**本设计交付物,实现时建**(含结构性-only 纪律 + 题材例外白名单 + 强制引用 + findings JSON schema)。
- **校准 tabulator 纯函数单测**:精度计算(真阳/假阳)、按 reviewer/类目聚合、缺数据不崩。
- 全量 `pytest -m 'not api'` 绿;tooling 走 SDD。

## 风险 / 地雷(codex)
- **反事实盲**:v0 不改 plan 照跑 → 天然全 holdout,直接可量假阳(本设计已规避)。
- **LLM 幻觉 finding**:强制引用 JSON 路径 + 拒含糊 + 确定性检查兜高精度类。
- **题材例外误报**:白名单 + "已被设定解释"排除;按类目跟精度,例外多的类目(重生/变身)默认 warn 不 hard。
- **planner 写"满足评审的解释"而不真修**:v0 不回流改 plan,无此回路;**末态 jury 结果始终为准**。
- **缓存/版本漂移**:v0 旁路不改工件,不触缓存;若将来接管线,缓存键须含工件版本+审核状态(留给 v1)。
- **模型/提示词漂移**:pin 模型版本 + 冻结提示词。
- **并集标注偏乐观**:精度按 reviewer 分别算,不混并集;hard 拦只认高置信。
- **n 小**:B 档 n 仍小 → v0 出的是"哪些类目精度高"的方向,不是终局阈值;精度坐实需 C/D/E 累积。

## 诚实边界
v0 = **校准门,不接管线、不 auto-fix**。产出 = "哪些上游 finding 类目精到可作硬拦"的证据 + 跨族 vs DeepSeek 必要性。真接入管线门(候选工件→过审才起草)是 **v1**,需 v0 精度证据支撑,另立 spec。

<!-- codex-peer-reviewed: 2026-06-30T14:21:55Z rounds=2 verdict=approved -->
