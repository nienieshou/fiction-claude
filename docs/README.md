# docs · 文档导航

hiki-fiction-rewrite 小说复写系统的产品与设计文档。

```
docs/
├── prd/
│   └── PRD.md                          产品需求文档 v1.0（做什么/成功是什么，需求+验收）
└── design/
    ├── system_design_final.md          ★ 权威架构 spec（Final v5.0，怎么做）
    ├── fact_spine.md                   承重专项·事前一致性架构（Fact Spine v1.0，事前根治人名/身份/时间线漂移）
    ├── tier1_whole_novel_mining.md     Tier1 全书深挖（map-reduce 取代开头切片）
    ├── tier3_fact_loop_and_seq_draft.md Tier3 prose 事实层闭环 + 顺序起草 M0（含证伪记录）
    └── archive/                        历史版本（保留决策来龙去脉）
        ├── system_design_v4.md         v4 重构版（首次按 8 公理/5 概念重组）
        └── system_design.md            v3.1 讨论演进版（含决策过程）
```

- **从这里开始**：`prd/PRD.md`（需求与验收）→ `design/system_design_final.md`（架构）。
- 二者配对演进：任一变更同步对方并 bump 版本。
- 旧系统（PR-11，人工 60–70）架构见 **项目根 `../../system_design_old.md`**；语料分析见项目根 `AI小说创作代码库深度剖析_*.md`。
- 标杆语料：40 本人工 90 分 @ `codex/fictions_source/`。
