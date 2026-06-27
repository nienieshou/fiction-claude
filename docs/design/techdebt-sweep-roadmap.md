# 技术债 sweep 路线图(C 类 + A3 + E)

> 2026-06-27 起。配套登记册 `docs/design/tech-debt.md`(权威状态)。本文件是**执行序列 + resume 指针**。
> 纪律:每项独立 spec→plan→SDD→PR,项间用金标回归网(`assets/gold_regression/`)守等价。绝不一锅端。

## 已落地

| 项 | 交付 | 状态 |
|---|---|---|
| **E2 金标回归网** | PR #6 | ✅ 已合并 master。Tier-A 门决策快照网(7本)进 CI。 |
| **C4 textnum 单源** | PR #7 | ✅ CI 绿,待合并。中文数字+章节/卷正则收口,修 mining/slice 漏卷。 |
| **E2.1 装配层网** | PR #7 | ✅ CI 绿,待合并。`signal_counts_from_fact_table` + fact_table 入库 + cross_check 语料(C1 等价基线)。 |

## 进行中

| 项 | 交付 | 状态 |
|---|---|---|
| **C1 死人复活 Ledger** | branch `feat/c1-revival-ledger` | spec + plan **已写未执行**。spec: `docs/superpowers/specs/2026-06-27-c1-revival-ledger-design.md`;plan: `docs/superpowers/plans/2026-06-27-c1-revival-ledger.md`(6 任务,SDD 执行)。 |

## 待办(各自 spec→plan→SDD,建议序)

| 序 | 项 | 体量/风险 | 依赖/备注 |
|---|---|---|---|
| 1 | **C1 死人复活**(进行中) | 6路径/3模型,中高 | 计划已就绪,直接 SDD 执行。 |
| 2 | **C2 修为合并** | 2 引擎(序数/数值),中 | 网未覆盖序数引擎 → 先补特征化(同 C1 P1/P3 套路)。可复用 RevivalLedger 模块(char_ledger.py)加 power concern。 |
| 3 | **C5 name 谓词单源** | 5+ 处界 2-4/2-5/2-6/2-8,小 | 有真 bug(人名界 5 vs 6 → "欧阳修远"provenance 缺口)。`is_person_name`/`is_item_name` 单源;2-4 variant anchor 是有意紧界,保留。 |
| 4 | **C3 身份渲染器** | 3 渲染器(2 个数据相同),中 | **半阻塞**:渲染器1(id_map)删除依赖 HIKI_SPINE 转正决策——需先定 HIKI_SPINE 是否转默认。渲染器2/3 可先合(数据同、仅格式异)。 |
| 5 | **A3 schema 层** | 30 契约/34 调用点,大 | **风险最高**:改的是金标网兜不住的检测器层。须各契约 characterization 后再动;建 `validate(raw,schema)→retry→reject` 复用层 + 逐契约 schema。建议先做 Class-B(静默假阴)高危契约子集,非一次 30 个。范围图见会话 Explore 报告(A3)。 |

## Resume 指针(关机后从这里接)

**当前分支**:`feat/c1-revival-ledger`(基于 `feat/techdebt-sweep` HEAD `7b8212d`,含 E2.1)。
**未推送**:本分支有 2 个 commit(spec + plan),尚未 push。
**下一步**:
1. 若先合 PR #7(C4+E2.1)→ 合后把 `feat/c1-revival-ledger` rebase 到 master。
2. 执行 C1:调 `superpowers:subagent-driven-development`,按 `docs/superpowers/plans/2026-06-27-c1-revival-ledger.md` 逐任务跑(Task 1 ledger → Task 2 P1/P3 补网 → Task 3/4/5 迁移 → Task 6 收口)。
3. SDD 进度账本:`.superpowers/sdd/progress.md`(本地持久,resume 时先读它)。

**关键不变量(每步必守)**:`pytest tests/test_gold_regression.py tests/test_assembly_regression.py` 全绿 + 7 本 `ft_revival_residual` 零变化。
