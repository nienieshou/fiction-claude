# 漏斗产线（Funnel Pipeline）· 10k 本规模复写流水线设计

> **版本 v0.1（pilot 薄片已落地）** ｜ 2026-06-16
> 定位：把单本 `hiki run` 放大到**万本规模**的产线架构。核心不是改写本身，而是**用便宜的 pregrade 在烧改写钱之前筛源**。
> 公理依据：A4 源是脊柱/提分靠选 · A7 成本随难度自适应。
> 已落地：`src/hiki/funnel.py` + `hiki funnel` 子命令（commit 0f08df6）。

---

## 0. 一句话

**10k 本不全量改写（¥65k 不可行），而是漏斗：ingest→pregrade→按档 filter→只放强源进改写→门+抽样QA→入库。省钱全在 filter，质量主杠杆在选源（pregrade），不在改写。**

---

## 1. 形状：漏斗，不是平 batch

```
10000 raw
  │ ① ingest+dedup     (~¥0,  确定性)        去重/去损坏/去过短      → ~9000
  │ ② pregrade         (~¥0.3/本 = ¥2700)    S/A/B/C/D/Q + 题材 + 暗黑 + 主角弧
  │      └─ FILTER --keep S,A                  弱源不进改写(省钱命门)  → ~25% = 2300
  │ ③ triage/route     (~¥0,  从pregrade派生) 按题材难度选config       (修仙/古言加candidates)
  │ ④ rewrite          (¥6.7/本 × 2300 ≈ ¥15k) mine→plan→draft→refine→gate→finalize
  │      └─ 每本自带 Fact Spine / 穿越POV铁律(B) / 代入审计(C) / 门(A)  都是 per-book 独立
  │ ⑤ gate + 抽样QA                            机器门兜灾难 + 分层抽样人评校准
  └─ ⑥ deliver/catalog                         交付入库带元数据;拒收→复跑队列或弃
```

**成本账**：全量 ¥65k → 漏斗 ~¥18k（pregrade ¥2.7k + 改写 ¥15k），filter 是 4× 省钱杠杆。

---

## 2. 命门：pregrade filter 的校准（**头号风险，非工程**）

漏斗的省钱全压在 filter（`--keep S,A`）上。**filter 错 = 漏掉好书 / 放进烂书。** pilot 第一时间就撞出这个：

| 本 | pregrade 源档 | human-eval-5 成品分 |
|---|---|---|
| 退婚→隐婚 | **B**（会被 S,A 过滤掉）| **76（全场第一,唯一上出货线）** |
| 傲世→和谈 | **S**（filter 放行）| **54（全场最低）** |
| 六零→团宠 | A | 72 |
| 灵气→武神 | A | 60.8 |
| 星际→星厨 | S | 65 |

**pregrade 源档与人类成品分几乎不相关**（S 的傲世最低、B 的退婚最高）。结论：

- **源档 ≠ 成品质量**。要么 pregrade 对"纯人物/现言"类偏严，要么复写引擎能把 B 源抬到出货线。
- **`--keep S,A` 默认会漏掉真金**。10k 漏斗上线前，**必须先按人类成品真值回归校准 pregrade 分级**（或放宽到含 B）。
- 这与全局测量主题一脉相承：连源分级都可能与人类真值不对齐。pregrade 校准 = 上 10k 的前置条件。

---

## 3. 规模 QA：10k 不可能逐本人评

- **人工真值是唯一可信**（反复证实），但 10k 本不可能逐本人评。
- **机器门不可靠**（承重门信号与人类承重零相关，已降 advisory，见 fact_spine §3.6 / human-eval-5）。

故 10k 质量保证 = **分层抽样校准 + 机器门兜底 + 漂移监测**：

| 手段 | 作用 |
|---|---|
| 机器门（bulk）| 逐本兜灾难级（过短/暗黑/复活/审计崩）；承重微观信号入库但**不当质量认证** |
| 分层抽样人评 | 按 题材×档位 抽 N 本/层 → 回归校准该层门阈值（hfl 机制）+ 估交付质量分布 |
| 漂移监测 | 抽样分随时间/题材掉 → 报警 → 重新校准 |

**诚实定位**：10k 下交付质量 ≈「机器门放行的 + pregrade 选源决定的」，接受"统计 X% 达线"而非"逐本认证"。

---

## 4. 已落地：`hiki funnel`

```bash
hiki funnel fictions_source/ --keep S,A --dry-run          # 看漏斗+估成本,不烧改写钱
hiki funnel fictions_source/ --keep S,A --max 20 --spine --parallel 5   # 强源优先改写前20本
```

| 环节 | 实现（`src/hiki/funnel.py`）|
|---|---|
| 收集 | `pregrade._collect`（源目录 / 多个 .txt）|
| ① pregrade | `pregrade.run_pool` 逐本独立分级 |
| ② filter | `select()` 按 `--keep` 过滤 → 档+字数排序 → `--max` 截顶（强源优先）|
| ③ run | `build_tasks` → `batch.run_tasks`，slug 自动唯一、失败隔离、resume |
| 报告 | `funnel_report.{json,md}`：入池→分布→存活→改写→可交付 + 分阶段¥ + ¥/交付本 |

- `--dry-run`：只 pregrade+filter+**估改写成本**（¥6.7/本锚），不改写。
- `--max N`：强源优先取前 N 本（pilot 控预算）。
- 验证：4 纯函数测试（select/slug/build_tasks/report）；实源 dry-run 3本→S1/A1/B1→存活2→估¥14.23。

---

## 5. 10k 缺口（pilot → 生产）

| 能力 | 现状 | 10k 需要 |
|---|---|---|
| 单本流水线 | ✅ resume/失败隔离 | 够用 |
| 漏斗自动化 | ✅ `hiki funnel` | 够 pilot |
| pregrade 校准 | ❌ 与人类真值不对齐 | **上线前置**：按成品真值回归 / 放宽 keep |
| 状态/幂等 | ❌ 静态收集 | 持久化队列+状态机(pregraded/queued/drafting/gated/delivered)、content-hash 去重、跨重启幂等 |
| 全局预算 | 单本 ¥50 cap | 全局预算闸 + 分阶段成本追踪 |
| 并发 | per-book 110pro + --parallel | 账号 TPM 天花板（探持续上限分波）|
| 可观测 | funnel_report | 吞吐/烧钱率/过门率/漂移 dashboard |
| QA | 机器门 | 分层抽样人评回流（hfl 雏形）|

---

## 6. Roadmap

1. **pregrade 校准**（前置）：5 本已有真值先验证相关性 → 扩 100 本 dry-run 看分布 → 回归校准分级或调 keep。
2. **100 本试点实跑**：funnel 实改写，量真实 filter 通过率 / ¥/本 / 过门率 / 抽样人评吻合度。
3. **工程放大**：持久化队列/状态库 + 并发分波 + 全局预算闸 + dashboard。
4. **10k 生产**：同漏斗 + 分层抽样 QA 常态化 + 漂移监测。

> 核心判断：**10k 漏斗的头号风险是 pregrade filter 的校准，不是工程脚手架。** 先解决选源可信，再放大。
