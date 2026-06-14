# PR: Fact Spine M1.5+M2:六类钉死(名/数值/身份/地点/势力/体系) + 承重 A/B 验证

base: master ← fact-spine-m1.5-m2

## 摘要

承重一致性**事前架构**推进:把矛盾从「21万字 prose 空间」搬到「~50-200行 registry 空间」、前移到起草前。全部 behind `HIKI_SPINE=1`,**默认管线零改动**;每杠杆 falsifiable + grep/Opus 双验证。

## 七个杠杆

| | 杠杆 | 验证 |
|---|---|---|
| ① | 测量仪修复(IDENTITY_VERIFY 真矛盾门 + 复合中文数 + 可变量白名单) | 身份误报 ~90% 滤除;M1「无变化」证伪为坏仪表 |
| ② | 数值钉死(fact_observations→REDUCE.facts→_spine_facts) | 数值真矛盾 12→2;彩礼/失散年数 prose grep 可验一致 |
| ③ | Opus 承重 A/B | 退婚 34→39、致命 8→3 |
| ④ | 身份钉死(_spine_roster + 3铁律:新功能角色另起名) | 头号致命周柏森(律师↔总监)grep 消解 |
| ⑤ | 时间线登记表(milestones 里程碑账,复用波间结算) | 单测+运行时机制证(治孕产时间线退步) |
| ⑥ | §3.6 薄网进交付门(cross_check 真矛盾→ship_issues) | 接线 gated;低召回兜底网(非保证) |
| ⑦ | 世界观体系登记表(places + power_system 冻结→_spine_world) | 见 M2 傲世 |

## M2 批量裁定(线性甜区 5 本,Opus 盲审 pairwise 承重 A/B,grep 核验)

承重均值 **35.4 → 54.2 (+18.8)**,Spine 臂 n=1 vs baseline best-of-3 = 被让分(保守下界)。

| 本 | baseline | spine | Δ |
|---|---|---|---|
| 怀孕命剩三月 | 34 | **74** | +40 |
| 六零团购 | 38 | **71** | +33 |
| 退婚财阀 | 42 | **61** | +19 |
| 误嫁豪门 | 34 | 34 | 0 |
| 傲世狂妃 | 29 | 31 | +2 |

3/5 大胜(2 本入强源甜区 71-74)。grep 核验:怀孕生父 6名→徐山川×36;六零母亲 3名→庄玲1名;离婚多版本 39→0。

**⑦ 攻下最硬持平本**:傲世(战力体系乱序+地名横跳致命)加 world registry → baseline 42 → m3 **76**(致命 5→0),跨进甜区。grep 证:战力数字段 217→92 且境界名现身、地名变体→0。

## 诚实边界

- Opus 绝对分含 grader 方差(~6-13pt 摆动)→ **Δ与致命计数+grep 是硬信号**,绝对分软。
- Spine 覆盖类已扩到 **名/数值/身份/地点/势力/体系 六类**;剩余失效类=**同事件双互斥版本**(需 plan 级 Spine.timeline,仍未建满)+ **edit-1 变体名**(徐寒武类)+ **POV/人称**。
- ⑤⑥ 为机制证(单测+运行时),完整 efficacy 随 M2 后续批量补。

## 变更

- `src/hiki/{prose_facts,prompts,mining,produce}.py` — 六类钉死 + 薄网
- `scripts/{m1_compare,m15_mine_facts,m2_spine_batch}.py` — 验证/批量驱动
- `docs/design/fact_spine.md` — 全程 falsifiable 裁定记录
- `output/` — M2 证据(5 spine_m2 + 傲世 m3 + 退婚 v2-v4 + 汇总,沿用仓库 output 留痕惯例)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
