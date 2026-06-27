# C1 死人复活 Ledger 设计

> 2026-06-27 · 技术债 C1(检测器 sprawl 根)首切。范围锁定:**仅死人复活合并**;C2 修为/C3 身份/C5 name 谓词各自后续。
> 配套:`docs/design/tech-debt.md`(C 类登记)、`assets/gold_regression/`(E2.1 装配层网,本设计的安全垫之一)。

## 目标

把"死人复活"在 **6 条检测/修复路径、3 套数据模型**上的重复检测,收口为**一个带 provenance + confidence 的 `RevivalLedger`**;3 套数据模型降为薄 adapter;门里"手写优先级裁权威"显式化为 ledger 上的 source 优先级。

**风险姿态(已定):行为保持的聚合层**——纯债务消减,**零产品行为变化**,裁决**逐位复现今天**,用金标网 + 新建特征化证等价。principled 改判留 follow-up。

## 现状(已核实的合并目标)

### 6 条路径 / 3 套数据模型

| 路径 | 位置 | 数据模型 | 喂给谁 |
|---|---|---|---|
| P1 `check_revival` | `audit.py:331-352` | **plan维度 list**(`scenes[i]["deaths"]:list[str]` 等) | `deterministic_audit`→`_run_ship_gate`→`plan维14复活`(**回退**信号) |
| P2 `cross_check` 生死段 | `prose_facts.py:95-111` | **findings dict**(`{cat:"生死",who,ch_a,ch_b,why,conf:"高"}`) | `fact_table.json["findings"]`→`_fact_audit_repair`、`signal_counts_from_fact_table` |
| P3 `find_revivals` | `prose_continuity.py:185-202` | **roster dict**(`{deaths:[{who,clue,ch,win}],...}`) | `audit_and_repair`(叙事修复) |
| P4 `verify_revivals` | `prose_continuity.py:205-218` | 消费 P2/P3 候选,LLM 逐条确认 `is_revival` | `_fact_audit_repair`、`point_repair`、`audit_and_repair` |
| P5 `verify_revival_beats`+`reconcile_revival` | `prose_continuity.py:221-243,164` | `beat_rendered` + life_arcs 回退 | **门 vs advisory 分流**(`produce.py:1103-1114`) |
| P6 `repair_revivals_smart`+`point_repair._verified_revivals` | `prose_continuity.py:351-382`、`point_repair.py:60-66` | 重写死亡/复活场景 | 叙事修复 |

### 今天的门裁决(behavior-preserving 必须复现)
- 门复活信号 `ft_revival_residual = len(ft["生死_verify后"])`,来自 **P2(事实表)** 流:cross_check→cand→verify_revivals→repair→verify_revivals→verify_revival_beats→`gate_rev` 分流(`produce.py:1091-1115`)。**金标网(E2.1)已钉死此信号在 7 本上的值。**
- `plan维14复活`(P1)是**回退**信号:`gate.py:159` 仅当 `plan维14复活>0 且 not 事实表跑过` 才进门。
- P3(roster)**只做叙事修复**,不直接进门。
- 即:provenance 优先级 = `facts`(权威) > `plan`(回退) > `roster`(仅修复)。门里手写优先级就是这个,ledger 显式化但**不改判**。

## 架构

### 模块与数据模型
新建聚焦模块 `src/hiki/char_ledger.py`,含 `RevivalLedger`(本期只做复活;C2/C3/C5 后续往同模块加 sibling concern)。纯类型(dataclass / TypedDict):

```
DeathEvent(who: str, ch: int, clue: str, source: str)        # source ∈ {"facts","plan","roster"}
AppearanceEvent(who: str, ch: int, source: str)
RevivalRecord(who: str, death_ch: int, revive_ch: int, clue: str,
              sources: set[str], confidence: str)             # confidence ∈ {"高","中","低"}
```

`RevivalLedger`(纯、零 LLM、零 IO):
- `record_death(who, ch, clue="", source) -> None`
- `record_appearance(who, ch, source) -> None`
- `revivals() -> list[RevivalRecord]` —— 确定性跨源去重合并:同 `who` 的 death → 其后最早 appearance 配成一条;多源命中则并 `sources`、取最强 confidence(facts 生死=高 > plan=中 > roster=低,沿用现状各路置信)。
- `resolve_gating(verified: list[RevivalRecord]) -> list[RevivalRecord]` —— 按 source 优先级输出"进门"集合,**复现今天 P2 权威 / P1 回退 / P3 仅修复的判定**。

**裁决由 source 优先级驱动,confidence 不驱动本期裁决**:复活 findings 现状一律 `conf="高"`,故 `confidence` 字段仅为与 findings dict 的字段对等(下游兼容)而携带,不参与 behavior-preserving 的门判定。principled 用 confidence 改判属 follow-up。

确定性合并规则(从现状逐路抽取,保证等价):
- P2 生死 findings 的 `2 <= len(who) <= 6`、"death 后最早 present" 语义 → `record_death`/`record_appearance` 的等价输入(adapter 内保持原过滤,不在 ledger 内改界——name 谓词统一是 C5,非本期)。
- 合并键 = `who`;一个 who 取首个 death_ch 与其后首个 revive_ch(与 P2/P3 现状一致)。

### Adapter(3 路变薄,消费方产出**逐位不变**)
- **P2** `prose_facts.cross_check` 生死段:改为往 ledger 写 facts 源 death/appearance,再由 ledger 产出等价 `生死` findings。`signal_counts_from_fact_table` 与 `生死_verify后` 产出**不变**(E2.1 网守)。
- **P1** `audit.check_revival`:改为读 ledger 的 plan 源,输出 `维14死人复活` list **不变**。
- **P3** `prose_continuity.find_revivals`:改为写 roster 源并经 ledger 产候选;`verify_revivals`/`verify_revival_beats`/`repair_revivals_smart` **留在原处**,改成消费 `RevivalRecord`。
- **LLM 编排、门、`_fact_audit_repair` 流程不动**,只换数据载体(dict → `RevivalRecord`,或 record→dict 的兼容投影)。

## 验证与特征化(A 方案硬要求)

现网只护 P2(cross_check 语料 + 装配网 E2.1);**P1(plan维度)/P3(roster)当前无网 → 迁移前先补网**。

1. `tests/test_char_ledger.py`:ledger 纯函数语料——跨源去重、source 优先级裁决、confidence 合并、death-后-appearance 配对边界。
2. `tests/test_revival_paths_characterization.py`:钉死 `check_revival`(P1)与 `find_revivals`(P3)**迁移前的输出**(synthetic 输入→精确输出),迁移后必须逐位相同。
3. 复用 **金标网 + 装配网(E2.1)**:7 本 `ft_revival_residual` / `生死_verify后` **零变化**;在样本上 `plan维14复活` 不变。
4. 全量 `pytest` + 金标网绿;`produce.py` 默认管线行为等价(本期不改门、不改 LLM 步)。
5. SDD 纪律:逐任务 TDD + 两段复核 + opus 全分支终审;项间网守。

## 非目标(本 spec 明确不做)
- C2 修为(2 引擎)/ C3 身份(3 渲染器)/ C5 name 谓词(界 2-4/2-5/2-6/2-8 分叉)。
- principled 改判(用 provenance+confidence 修当前手写优先级判错的情形)——留 follow-up,届时金标网已护。
- LLM 编排重构、门阈值、name 界统一。

## 风险
- **最高风险:P2 adapter 改动若让 `生死` findings 结构/计数漂移 → 金标装配网立刻红**(这是好事,网在工作)。迁移须保持 P2 产出逐位等价。
- P1/P3 当前无网 → 靠新建 characterization(步骤 2)兜底;迁移前先让其绿。
- `RevivalRecord` 与现有 dict 消费方的兼容投影需覆盖所有字段(`why`/`clue`/`ch_a`/`ch_b`/`revive_ch` 等),避免下游 `.get()` 取空。
