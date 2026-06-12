# 15 系统设计调研(2026-06-12,5 agent 并行,详证据见各仓库出处)

带着 R11/R12 定论读:版本互斥根因=plan brief 抽象+起草忠于 brief;读和修路径净收益≈0。

## 一览(按对我们的参考价值排序)

| 系统 | 架构一句话 | 对版本互斥/事实状态的核心机制 | 可借鉴度 |
|---|---|---|---|
| **inkos** | Planner→Composer(控制面编译)→Writer→Auditor→状态结算 | **章级 context.json 控制面**:写作前代码从权威 state 显式选入本章事实(每条带 source/excerpt,protected tier);intent 含"章尾必须发生的改变"+2-4条章级硬禁令;Observer 9类事实抽取→Reflector schema 校验 immutable 结算 | ★★★ 主刀范本 |
| **NovelForge** | Schema 卡片树+工作流引擎 | `entity_snapshot`(阶段末实体状态快照)+`dynamic_info`带id事实条目(增量upsert);**consistency.CheckRequest{text, facts_structured}→定位修复**=检测从"文本对文本"换轨"文本对事实清单" | ★★★ 检测换轨范本 |
| **WriteHERE** | 异质递归规划(EMNLP25) | 任务节点带 **inclusion/exclusion 字段**+依赖节点的已完成 result 注入(非抽象goal);COMPOSITION 任务强制按依赖串行 | ★★★ plan schema |
| **ai-book-writer** | AutoGen 群聊流水线 | 大纲硬约束"每章≥3条具体 Key Events 禁占位符";Memory Keeper 标签化状态(EVENT:/CONTINUITY ALERT:) | ★★ brief 反抽象的最简实现 |
| **AI_NovelGenerator** | 四步+人工定稿 | **"定稿即结算"闸门**:只有已裁决版本的事实进 character_state/global_summary/向量库——下游永远读单一权威版本 | ★★ 结算闸门 |
| **novelWriter**(人用) | 文档树+元数据索引 | 场景级 keyword 行 schema:@pov/@char/@location/@time/@plot/@mention 与梗概分离,机读 | ★★ 事实前提的字段设计 |
| **autonovel** | foundation→串行起草→对抗编辑 | 前章末 2000 字符**原文**硬注入(开场物理上无法另起版本)+canon 400+条修订期对账;**结构性漏洞实锤:canon.md 加载却不注入起草 prompt**——和我们"仪器全在事后"同病 | ★★ 含一个对照病例 |
| **AIStoryWriter** | 串行+阈值修订(已借鉴) | 新发现:**摘要-对-摘要**的大纲符合度判定(章摘要 vs 该章大纲摘要比对)——可改造为同事件互斥判定 | ★★ |
| **Long-Novel-GPT** | 三层扩写+对齐(已借鉴) | **段级互斥分区映射**(每段正文唯一锚定一条剧情,JSON 可校验,改后重对齐) | ★★ |
| **libriscribe** | PM 编排串行 | 实体跨章共现索引(cross_reference)可作互斥廉价信号 | ★ |
| **gpt-author** | 串行+前文全文拼接 | 反面教材:串行全文回避互斥但牺牲并行——证明"抽象brief+并行"必须补结构化前提 | ★(诊断价值) |
| **wfcz10086** | 人机协作编辑器 | 知识库五类结构化数据全量注入(最朴素事实对象) | ★ |
| **storycraftr** | RAG k=6 检索 | 反面教材:被动语义检索拿不到开场事实前提(与我们已证伪路径同构) | 反例 |
| **gemini-writer** | 单 agent 1M 上下文硬扛 | 反面教材:纯长上下文+不指定压缩保留=互斥温床(我们 M0 已证) | 反例 |
| **AI-Writer** | RWKV 逐字续写 | 无规划层,不同代 | 无 |

## 收敛:防版本互斥的三种被验证机制(15 系统只此三种)

1. **字面续写锚定**(autonovel prev-2000字符/gpt-author 全文拼接):开场物理上接前章原文。代价=串行;我们 M0 已证"上下文参考式注入"不够——区别在他们把前文当**续写起点**而非参考资料。
2. **plan 层事实硬化**(inkos 控制面/WriteHERE inclusion-exclusion/ai-book-writer Key Events 禁占位/novelWriter keyword 行/NovelForge entity_snapshot):本章开场前提+必含+必不含,由**代码**从权威状态编译,不靠模型回忆。
3. **结算闸门+唯一权威状态**(AI_NovelGenerator 定稿即结算/inkos Reflector immutable/NovelForge 章后回写实体卡):事实只在裁决后入库,下游读单一版本。

诊断性对照:autonovel 的 canon 不进起草 prompt=结构洞,与我们"事实仪器全在事后跑"同构——**事实必须前置进起草输入,事后对账治不了源头**(我们两轮数据+它的病例双重证实)。
