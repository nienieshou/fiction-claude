# 技术债 sweep 路线图(C 类 + A3 + E + B1)

> 2026-06-27 起,2026-06-29 收尾。配套登记册 `docs/design/tech-debt.md`(权威状态)。
> 纪律:每项独立 spec→plan→SDD→复核→合并,项间用金标/装配回归网(`tests/test_gold_regression.py`/`test_assembly_regression.py`)守等价。绝不一锅端。

## ✅ 已落地(全部并入 `origin/master`,截至 `880c7fd`)

| 项 | 交付 | 要点 |
|---|---|---|
| **E2 金标回归网** | PR #6 | Tier-A 门决策快照网(7本)进 CI。 |
| **C4 textnum 单源** | PR #7 | 中文数字 + 章节/卷正则收口。 |
| **E2.1 装配层网** | PR #7 | `signal_counts_from_fact_table` + fact_table 入库 + cross_check 语料(等价基线)。 |
| **C5 name 谓词单源** | merged | `is_person_name`/`is_item_name` 单源,7 站点全迁。 |
| **C1 死人复活 Ledger** | PR #8 | `RevivalLedger`(char_ledger.py),P1/P2/P3 迁移收口。 |
| **C2 修为 PowerLedger** | merged | 序数/数值二引擎合并到 char_ledger.py。 |
| **A3.1 schema 校验层** | merged | `llm_validate.complete_validated`(validate→retry→None)+ 逐契约 schema。 |
| **C7.1 共享 ending_check** | merged | 逐字重复尾门检测收编。 |
| **A3 wave2 LIFE_EVENTS** | merged | 静默丢生死事件治理(callable schema 向后兼容)。 |
| **A3 wave3 detect_retry** | merged | `gate.detect_retry` 共享检测环 + 四检收编 + stderr 浮现。 |
| **C6① DIMENSIONS 注册表** | merged | `Dim.gating`/`signals` + `NON_DIM_GATE_FLOORS` + 一致性守卫。 |
| **C6② craft_audit 门控** | merged | `config.advisory_on` 单源 + produce 白烧门控(默认开)。 |
| **A3 wave4 verify_identity** | merged | 身份验证解析耗尽 `verify_failed` 标记 + stderr(可见不动门)。 |
| **A3 wave5 score_scenes** | PR #9 | 唯一 0 重试站点换 complete_validated(失软 + 可见)。 |
| **C6 残留 slice_validate** | merged | dev 工具 EXTRACT 换 complete_validated(删 `_json`)+ craft_audit 门控。 |
| **C7 余切 复活候选** | merged | `prose_facts.revival_candidates` 单源(produce + point_repair 共用)。 |
| **B1 wave2 run() 外提** | merged | `_collect_valid_names`/`_detect_intra_repeats`/`_refit_short_chapters`/`_fix_pov_outliers`;run ~230→~190。 |

## ⏸ 剩余(未做 —— 阻塞或高风险,clean-slice 已稭干)

| 项 | 状态 | 原因 |
|---|---|---|
| **C3 id_map 删除** | **阻塞(产品决策)** | 删 legacy `id_map` 渲染器依赖「HIKI_SPINE(Fact Spine 特性)是否转默认」的决策,非代码。注:`_spine_block`(名钉死)与 `_spine_roster`(身份钉死)是**两个不同**渲染器(非同数据异格式),不可合;共享 `_pin_block` 已是单源。 |
| **B1 wave3 sig/report dict** | **延后(高churn/高风险)** | `run()` 末 `sig`(~11 locals)+ `report`(~51 行/~40 locals)dict 组装。抽 helper 需 dataclass 式重构(40 参比内联糟);`run()` 非金标/装配网端到端覆盖 → 等价无网兜底。维护性收益 vs 风险不划算,留待真有动机时另设计。 |

## 收尾说明(2026-06-29)

sweep 达成既定目标:**检测器 sprawl 单源化**(C4/C5/C6/C7)、**LLM 契约静默失败硬化**(A3.1/wave2-5)、**承重 Ledger 化**(C1/C2)、**god-function 显著瘦身**(B1 wave2)。剩余两项一为产品决策阻塞(C3),一为高风险低收益(B1 wave3),故停在干净点。

**Resume**(若重启):SDD 进度账本 `.superpowers/sdd/progress.md`(本地持久)。每步不变量:`pytest tests/test_gold_regression.py tests/test_assembly_regression.py` 全绿。要续 C3 须先定 HIKI_SPINE 默认;要续 B1 wave3 须接受无网兜底 + 字符级复核为唯一等价机制。
