# 会话总结收口 · 2026-06-15

> 一次长会话的成果汇总。三条线:**Fact Spine(质量)→ tech-debt(可维护)→ CLI(可交付)**。
> 分支 `fact-spine-m1.5-m2`(10 commits,均推送);`pytest` 65 测 + CI;全程默认管线零行为改动。

---

## 1. Fact Spine —— 承重事前一致性(质量线)

把跨章事实矛盾从「21万字 prose 空间」搬到「~50-200 行 registry 空间」、前移到起草前。**六类钉死**(全 behind `HIKI_SPINE=1`):

| 类 | 机制 | 验证 |
|---|---|---|
| ① 测量仪修复 | `IDENTITY_VERIFY` 真矛盾门 + 复合中文数 + 可变量白名单 | 身份误报 ~90% 滤除;M1「无变化」证伪为坏仪表 |
| ② 数值钉死 | fact_observations→REDUCE.facts→`_spine_facts` | 数值真矛盾 12→2;彩礼/失散年数 prose grep 可验 |
| ③ Opus承重A/B | 双盲 pairwise 精读 | 退婚 34→39、致命 8→3 |
| ④ 身份钉死 | `_spine_roster` + 3铁律(新功能角色另起名) | 头号致命周柏森(律师↔总监)grep 消解 |
| ⑤ 时间线登记表 | `milestones` 里程碑账(复用波间结算) | 机制证(单测+运行时) |
| ⑦ 世界观体系 | `places`+`power_system`→`_spine_world` | 傲世 baseline 42→m3 **76**(致命5→0,入甜区) |

**M2 批量(线性甜区5本,Opus 盲审)**:承重均值 35.4→54.2(+18.8),3/5 大胜,grep 核验(生父6名→1、母亲3名→1、离婚版本39→0)。

**诚实裁定(本会话最重要的发现)**:四维实测推翻乐观——**同文本 Opus 承重读数 ±40**(怀孕 pairwise 74 vs 四维 34)。pairwise +18.8 被对照锚定高估;**可信的是 grep 类级修复,不是 holistic 分**。五本四维总分均值 62.2,仍是承重次品。

---

## 2. tech-debt 还债(可维护线)

全系统审计(6路 finder),登记 `docs/design/tech-debt.md`。本会话落地:

| 主题 | 成果 |
|---|---|
| **F 测试+CI** ✅ | `pyproject`+`requirements`+CI;旧脚本迁入 `tests/`;**65 测**含 characterization(cross_check/ledger/spine 渲染器 原 0%) |
| **G 死代码/瘦身** ✅ | 删 5 死函数+metrics.py+死 prompts;`output/` **416 垃圾文件**移出跟踪(987→571) |
| **D 配置** ◐ | D1 交付门阈值→config+纯函数(2304组合证等价);D2/D3/D5 旋钮入 config |
| **A 可靠性** ◐ | A4 空响应重试根治+jitter;A2 崩溃审计进门;A1 承重路径;A5 评级失败即拒 |
| **B god-function 拆解** ✅主体 | **`run()` 528→188 行(−64%)**:mine/plan/draft/refine/gate/finalize 阶段化;mine/plan/draft 三贵阶段 **resume(B2)**;根除 `cont` 遮蔽 scope |
| 余 | A3 schema / C 检测器统一 / E assets·校准器(待) |

**/code-review 10 修**(复审 Fact Spine diff):`_num_of` 万/亿量纲、里程碑不截断、出生误匹配、cap 分类键、薄网短路、`_pin_block` 收敛等。

---

## 3. CLI 封装(可交付线)

```bash
python -m hiki run <src.txt> [--out DIR]            # 单本
python -m hiki run --tasks-file tasks.yaml          # 批量
```
- `batch.py`(G3 孤儿)**复活为引擎**:out 映射 `<out>/<slug>` · 单本失败隔离 · **续跑**(吃 B1/B2 阶段 resume)· `--spine/--force/--parallel/--min-grade` · `batch_summary.{json,md}`。
- 验证:7 batch 单测 + e2e CLI dispatch(零API)+ tasks.yaml 友好报错。

**串成可交付品**:一条命令把一批源跑成成品,中断可续、单本失败不塌、自动汇总可交付/拒收/成本。

---

## 4. 诚实边界(不变)

- **输出区间没移动**:真人工 ~50、四维总分均值 62.2,**全部低于出货线 75,远低于目标 95**。CLI 让系统**可运维**,Fact Spine 治了承重**可钉死的类**,但:
  - **测量危机**:Opus 承重 ±40 + 整体高估 9-17 → 当前**无法可信认证**到没到 X 分。
  - **非承重天花板**:笔力~65/人~61(50%权重)是微调墙,工程动不了 → 即使承重满分也封顶 ~70。
- **下一个真正移动区间的动作 = 修测量**(E3 校准器 / grep 清单承重分),不是再加第七类钉死或再重构。

---

## 5. 状态一览

| 维度 | 状态 |
|---|---|
| 质量(Fact Spine 六类) | ✅ 落地+验证;承重 grep 可证改善,holistic 未抬过线 |
| 可维护(测试/config/拆解/resume) | ✅ 主体;65 测+CI,run() −64%,三贵阶段续跑 |
| 可交付(CLI) | ✅ tasks.yaml 批量+续跑+失败隔离 |
| 待办(价值序) | **测量(E)** > 严选源/选择性交付(配方) > A3/C(工程债尾) > 微调(产品级) |

*权威架构 `system_design_final.md`;承重专项 `fact_spine.md`;债账 `tech-debt.md`;拆解方案 `b1-run-refactor.md`。*
