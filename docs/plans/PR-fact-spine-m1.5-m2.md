# PR: Fact Spine + 工程硬化 + 人机校准闭环(A/B/C/D) + 10k 漏斗薄片

base: master ← fact-spine-m1.5-m2

## 摘要

本分支从「承重事前架构」一路推进到「人工真值校准闭环」和「万本规模漏斗」。四条主线，全程 falsifiable、真值兜底：

| 主线 | 内容 | 验证 |
|---|---|---|
| **1. Fact Spine** | 承重一致性**事前架构**：矛盾从 21 万字 prose 空间搬到 ~50-200 行 registry 空间、前移到起草前。六类钉死(名/数值/身份/地点/势力/体系)。`HIKI_SPINE=1`，默认管线零改动 | Opus A/B + grep 双验证(下详) |
| **2. 工程硬化** | tech-debt 清账(可靠性/死代码) + 行级 code-review 10 修 + 配置驱动(D) + pytest/CI 测试网 + `run()` god-function 拆阶段管线(B1，528→188 行)+ 逐章断点续跑(B2) | 77 tests 绿、CI |
| **3. CLI** | `hiki run`(单本/批量 tasks.yaml + 续跑 + 失败隔离) | 5 题材批量实跑 |
| **4. 人机校准闭环** | 首次人工真值 → **A/B/C/D** 四 action(下详) | 人工 5 本盲评 + 重跑实证 |
| **5. 10k 漏斗薄片** | `hiki funnel`(pregrade→filter→run 一条命令) | 实源 dry-run |

---

## 主线 4：human-eval-5 人机校准闭环（本轮核心）

首次拿到人工真值（1 运营评委盲评 5 题材成品，权重 故30/笔25/人25/承20）：

| 本 / 题材 | 人类总分 | vs Opus 自评 |
|---|---|---|
| 隐婚千金 / 現言 | **76.0**(全场第一,达出货线) | +10.3 |
| 星厨甜妻 / 星际 | 74.8 | +9.8 |
| 团宠拾月 / 年代 | 72.0 | +4.8 |
| 武神 / 修仙 | 60.8 | +3.7 |
| 和谈令 / 古言(S源) | 54.0(全场最低) | **−15.2** |

据真值做四刀，**每刀都带诚实边界，A/D 被数据反推**：

- **A 重标承重门**(`gate.py`)：真值表证伪信号可分性——重演/spine/final/预告与人类承重**零相关**（最可追本含最多重演）。非判别信号**降 advisory**，硬门只留灾难级。5 本离线重判 + re-finalize 正名（零¥，gate 纯函数）。
- **B 穿越/重生开篇代入铁律**(`produce.py`+`prompts.py`)：修唯一被人类挖出、机器自检全瞎的真生成 bug（原主视角开篇再死/原身矛盾/NPC点破金手指）。**实证**(重跑¥15.37)：双审稿证实和谈/团宠开篇三伤全修复。
- **C 开篇代入感审计**(`audit.py`+`prompts.py`)：补机器最大盲点（和谈被高估15分=机器无代入信号）。`opening_immersion_audit`(advisory)。**实证**(¥0.024)：合成破开篇→代入感分30，抓到 craft 漏的代入崩。
- **D 笔力维**：原"过严该放松"假设**被证伪**（去套话门重写隐婚22章→人类笔力90，机制在产清稿）；"偏严"是自评分偏差非生产门。故**不松**，只把旋钮入 `config.decliche`。

证据：`docs/evidence/human_eval5_calibration.md` · 原始分 `assets/hfl.jsonl` · 收口 `docs/plans/2026-06-16-human-eval5-loop.md`。

---

## 主线 5：10k 漏斗薄片 `hiki funnel`

pregrade→filter→run 一条命令（`src/hiki/funnel.py`）。10k 省钱在**选源**：弱源不烧改写钱（¥65k 全量 → ~¥18k 漏斗，filter 4× 杠杆）。`--dry-run` 估成本不改写，`--max N` 控试点预算。

**pilot 立刻撞出头号风险**：pregrade **源档 ≠ 人类成品分**（B 源退婚→人76最高；S 源傲世→人54最低）→ `--keep S,A` 会漏掉真金。**filter 校准是上 10k 的前置条件**，比工程脚手架优先。设计：`docs/design/funnel_pipeline.md`。

---

## 主线 1：Fact Spine M1.5+M2（基础，保留）

七杠杆全部 falsifiable + grep/Opus 双验证：

| | 杠杆 | 验证 |
|---|---|---|
| ① | 测量仪修复(IDENTITY_VERIFY 真矛盾门 + 复合中文数 + 可变量白名单) | 身份误报 ~90% 滤除;M1「无变化」证伪为坏仪表 |
| ② | 数值钉死(fact_observations→REDUCE.facts→_spine_facts) | 数值真矛盾 12→2;彩礼/失散年数 grep 可验 |
| ③ | Opus 承重 A/B | 退婚 34→39、致命 8→3 |
| ④ | 身份钉死(_spine_roster + 3铁律) | 头号致命周柏森(律师↔总监)grep 消解 |
| ⑤ | 时间线登记表(milestones 里程碑账) | 单测+运行时(治孕产时间线退步) |
| ⑥ | §3.6 薄网进交付门(cross_check 真矛盾) | 接线 gated(低召回兜底网) |
| ⑦ | 世界观体系登记表(places + power_system 冻结) | 傲世 baseline 42→m3 76(致命5→0) |

M2 批量(线性甜区 5 本，Opus 盲审 pairwise 承重 A/B)：承重均值 **35.4 → 54.2 (+18.8)**，Spine 臂 n=1 被让分（保守下界）。grep 核验：怀孕生父 6名→徐山川×36；六零母亲 3名→1名；离婚多版本 39→0。

---

## 测试 / 文档

- **测试**：`tests/` 全套 **77 passed**（gate/produce_units/stages/funnel + characterization），`.github/workflows/ci.yml`。
- **设计文档**：`system_design_final.md`(§0 现状增量 v5.1，单一可信入口) · `fact_spine.md` · `funnel_pipeline.md` · `tech-debt.md` · `b1-run-refactor.md`。
- **output/**：整目录 gitignore（产物可重建），结论性证据迁入 `docs/evidence/`。

## 诚实边界

- **机器自评(承重/笔力)系统性不可裁决**（同文承重±40，两度被真值证实）→ 只 advisory，不作交付裁决。
- 质量现状：人类成品 **54–76**，最佳(现言)达出货线 75，**95 远未达、承重(50)是瓶颈**。
- 仅 **1 评委**（IRR 无意义）；B/C 是否真抬人类分、pregrade filter 校准、多评委复评 = 头号待办。
- Opus 绝对分含 grader 方差 → **Δ + 致命计数 + grep 是硬信号，绝对分软**。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
