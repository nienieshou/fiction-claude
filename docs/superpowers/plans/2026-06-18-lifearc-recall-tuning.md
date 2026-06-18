# 生死弧抽取召回调优 Follow-up Plan（投资前先测量）

> 这是 `2026-06-18-lifearc-mine-integration.md` 的后续。该计划已合并（master `b378fc0`）：生死弧基础设施 + 和解感知生死门已就位且**保守安全**（缺弧→仍拦，绝不误放）。**唯一缺口 = 召回**：忠实复活难例（桑念）在多任务 `EXTRACT_CHUNK`（12 窗）下漏抽 → 无弧 → "救忠实复活"未生效。

**Goal:** 把生死弧抽取的召回提到能稳定救回 `dies_returns` 难例（硬判据：桑念 → `dies_returns`），同时控制额外成本。

**已知事实（来自本会话证据）：**
- v3 *专用* 全读 pass（`scripts/arc_m2_fullread.py`，20 窗、只抽生死）：桑念 ✅ `dies_returns`，¥0.34/61万字。
- 集成版（`scripts/arc_integ_probe.py`，搭 `EXTRACT_CHUNK`、12 窗、5 类同抽）：桑念 ❌ 无弧，袁麟/卢炳元 ✅ `dies_final`。¥1.22。
- 根因假设：多任务 prompt 稀释 life_events 召回；窗太粗也可能漏。

## 第一步：测量，不要直接改（决策前先有数）

候选三条路，各自的召回/成本要先量出来，别拍脑袋选：

| 方案 | 做法 | 预期召回 | 预期成本 | 风险 |
|---|---|---|---|---|
| A. 提窗数 | `EXTRACT_CHUNK` 仍多任务，但 `n_chunks` 12→20/24 | 中 | 略增（同 prompt 多跑几窗） | 可能仍被多任务稀释 |
| B. 专用 pass | 生死事件单独一遍轻 prompt（=v3 arc_m2），与主 MAP 并发 | 高（v3 已证） | +一遍 flash 全读（~¥0.3-0.5/本） | 偏离"骑现有窗近零成本"初衷 |
| C. 混合 | 主 MAP 照旧；只对"被生死门 flag 但无弧"的角色补一次定向全读 | 高且省 | 仅难例补抽 | 逻辑更复杂 |

**Task R1（投资前测量）：** 在固定 3 本（含桑念书 ZTGGX02751、袁麟书 _rerun_ZYGGX02148、再加一本有 dies_returns 的）上，分别跑 A/B/C，记录每本每方案的：①目标角色 fate 是否命中真值 ②¥成本 ③召回的弧数。产出一张召回×成本对比表。复用 `arc_m2_fullread.py`（B 的代理）+ 改窗数的 `arc_integ_probe.py`（A 的代理）。**判据：选能让桑念稳定 `dies_returns` 且单本增量成本可接受（建议 ≤¥0.5/本）的最省方案。**

### Task R1 实测结果（2026-06-18，2 锚本：桑念 / 袁麟+卢炳元）

| 方案 | 桑念(GT=dies_returns) | 袁麟(GT=dies_final) | 卢炳元(GT=dies_final) | 成本 | 稳定性 |
|---|---|---|---|---|---|
| A@12（集成基线） | 无弧 ❌漏救 | dies_final ✅ | dies_final ✅ | 随主 MAP | — |
| A@20（提窗） | dies_returns ✅ | **无弧**（gate 对/未分类） | dies_final ✅ | ¥1.39/2 本≈¥0.7/本 | **噪声**（袁麟 12→20 翻成无弧） |
| **B（专用 pass，arc_m2，20 窗）** | **dies_returns ✅** | **dies_final ✅** | **dies_final ✅** | **¥0.33 冷 / ¥0.01 缓存** | **稳定** |
| C（混合） | =B（漏才补） | =MAP 命中 | =MAP 命中 | ≈MAP + 难例补 | 复杂，且 B 已够便宜 |

**结论 = 选 B（专用轻 prompt 全读 pass）。** 理由：
1. **召回最干净**：3/3 显式命中真值；A 即便提到 20 窗仍被多任务稀释（袁麟翻成无弧），且**非单调/噪声**——一个对生死门要"可信"的信号，A 的不稳定直接出局。
2. **最便宜**：B 读的是**与主 MAP 同一批窗**，DeepSeek prefix 缓存命中 → 输入近零（实测第二本 ¥0.01）；增量主要是轻 prompt 的少量 output，**远低于 ¥0.5/本**预算。A 反而要把昂贵的多任务 prompt 多跑 8 窗，更贵。
3. **最简单**：C 的条件触发只在"B 很贵"时才划算，而 B 已经便宜到不值得加复杂度。

**安全旁证**：A@20 里袁麟"无弧"但门判定仍 = gate（保守默认拦），说明无论召回如何波动，**保守默认始终不会误放**——召回只影响"能不能救"，不影响"会不会误放真矛盾"。

**第二步据此锁定方案 B**（下文）。

## 第二步：实现选中的方案（TDD，按 mine-integration 计划同款粒度）

- 若选 **A**：把 mine 的 `n_chunks` 默认对生死敏感书上调（或单独给生死弧用更细窗），无新 prompt。
- 若选 **B**：新增 `mining.extract_life_events_pass(cli, chunks)`（轻 prompt，只抽 life_events，与 `map_extract` 并发），结果并入 `collect_life_events`。`mine_book` 增一次并发调用。
- 若选 **C**：在 `_fact_audit_repair`，对 `reconcile_revival==gate` 且 `who` 不在 `life_arcs` 的残留，补一次定向源书全读（仅该角色），二次判 gate/advisory。

**回归判据：** 集成探针 `arc_integ_probe.py` 桑念 → `弧=dies_returns / 门判定=advisory`；袁麟/卢炳元仍 `dies_final / gate`（不得因提召回而把真矛盾误降级）。

## 第三步：召回达标后的增量（可选，依赖本计划）

- **"漏复活情节"判定**：advisory 分支里进一步校验复写 ch_a..ch_b 是否含复活 beat，区分 ②漏复活（应补 beat）/③忠实复活（真放行）。
- **前向预防（forward-injection）**：把 `_spine_alive_baseline` 升级为"遵从 life_arcs"喂 plan/draft（另见同目录后续计划）。

## 成功标准

1. 桑念稳定 `dies_returns`、袁麟/卢炳元稳定 `dies_final`（探针硬判据）。
2. 单本增量成本量化且可接受。
3. 真矛盾零误降级（不得为提召回牺牲安全）。
4. 在原 10 本拒收集上重测：死人复活拒收里有多少是 `dies_returns` 误杀（应被救），多少是真矛盾（应留拒）——给出最终"该救几本"的数。
