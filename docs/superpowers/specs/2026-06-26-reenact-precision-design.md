# D2 重演检测器精度修复 — 设计文档

**日期**: 2026-06-26
**状态**: 已批准设计，待转写实现计划
**来源**: 保留集验证读（docs/evidence/readthrough_defect_catalog.md "保留集验证读"节）证实 reenact_hits 被假阳性污染。

## 问题

`_plane_check`（src/hiki/produce.py:1163）把"角色在对话/回忆中向另一角色转述读者已见的事件"（视角转述）误判为"事件重演"，使 `reenact_hits` 虚高。该信号经 `事件重演` 喂交付门 `reenact_min`（gate.py:128），FP 污染**阻塞了阈值重标定**：盲目降阈会掩盖真重演，盲目升阈会放过真泛滥。

`PLANE_CHECK` prompt（prompts.py:531）已含排除句"简短回顾/提及/承接余波 不算"，但对**详细的对话转述**（多事实复述）仍过火 —— 单 prompt 的召回/精度耦合无法细分。

**实证标注（保留集验证读）**：
- ZYGGY02252 ch29（程婉向宋旸转告所见娶亲事，×3 事实）+ ch38 → **误判，应丢弃**。reenact_hits=4 虚高。
- CPBXN00188 ch49（同一漩涡黑影场景，仅距离 10米→5米 伪进展）+ ch18（墓门倒塌动作双写）→ **真重演，应保留**。

## 目标

在 reenact_hits 喂闸门前，去除"视角转述"假阳性，得到干净的真重演信号，解除阈值重标定的前置阻塞。不改 PLANE_CHECK 第一段召回逻辑，不改 signals schema。

## 非目标（YAGNI 边界）

- 不把视角转述重分类到别的信号（如 D10 注水）。
- 不动 PLANE_CHECK 第一段召回逻辑。
- 不动 adj-dup 通道（同套判别逻辑未来可反哺，本计划不含）。
- 不在本计划做阈值重标定（清信号后的独立下一步）。

## 判别规则（裁决器核心）

裁决器对每个被 PLANE_CHECK flag 的 hit（事件 + 本章正文）做单一二选一判断：

**保留 = 真重演（缺陷）** — 叙事镜头把同一场景/动作/对峙当作新发生的事重新搬演：
- 角色再次"现场"行动/说原话，重放（常在章首）；
- 零新进展：无新信息/新决定/新结果，只为读者再演一遍；
- 含"伪进展"：同场景仅改细微数值/措辞制造假推进（CPBXN ch49 距离 10→5米）→ **保留**。

**丢弃 = 视角转述 / 合理复述（正常叙事）** — 须**同时**满足两条：
1. **转述形式**：以对话（角色甲告诉角色乙）或回忆（"她想起…"）的报告式呈现，镜头不重搭场景；
2. **有叙事功能**：听者由此获知/决定/反应，推进关系或情节。

**边界守则**：**存疑 → 保留**（偏向召回，宁可少滤一个 FP，不放过真缺陷；与闸门"挡极端泛滥"取向一致）。

标注样本预期：ZYGGY ch29/ch38 → 丢弃；CPBXN ch49/ch18 → 保留。

## 架构 / 数据流

### 新增 prompt `REENACT_ADJUDICATE`（prompts.py，紧挨 PLANE_CHECK）

- 输入：单个被 flag 事件 + 本章正文（复用已有 `ch_texts[ci][:6000]`）。
- 输出：`{"reenact": true/false, "why": "<15字>"}`（true=真重演保留，false=视角转述丢弃）。
- prompt 体现判别规则与"存疑→保留"偏向。

### 改 `_plane_check`（produce.py:1163）— detect→adjudicate

1. 现有逻辑不动，照旧并发收齐 raw hits（高召回第一段）。
2. 新增第二段：对每个 raw hit 并发跑 `_adjudicate(ci, event)`，复用本章 `ch_texts[ci][:6000]`。
3. `reenact: true`（含存疑保守判 true）→ 进 `reenact_hits`（真重演，喂闸门）。
4. `reenact: false` → 进 `filtered`（视角转述，**不**喂闸门）。
5. 返回 `(reenact_hits, filtered)` 二元组。
6. raw hits 为空 → 跳过裁决，返回 `([], [])`。

**保守失败模式**：裁决器异常/空响应 → 该 hit 默认**保留**（true），绝不因裁决器抽风把真重演静默滤掉。`_plane_check` 既有 try/except 兜底（异常→空列表）维持。

### 调用点 / 报告 / 信号（produce.py ~1387, ~1430, ~1453, ~1482）

**关键：单一来源变量 `reenact_hits` 喂全部三个消费者**（已核对实际接线）：
- `reenact_hits = await _plane_check(...)`（1387）→ 进 `sig["reenact_hits"]`（1430）。
- 消费者一（闸门）：`_run_ship_gate` 自建 ship_signals 时取 `"事件重演": len(sig["reenact_hits"])`（produce.py:1212）→ 喂 `evaluate_ship_gate` 的 reenact_min（gate.py:160）。
- 消费者二（报告）：`控制面重演核对`（1453）= reenact_hits。
- 消费者三（信号）：`build_signal_vector(reenact_hits=len(reenact_hits))`（1482）。

**因此接线极简**：把 `_plane_check` 返回的**清后**真重演列表赋给 `reenact_hits` 变量 → 三个消费者**自动**取到干净数，**无需** early_repeat plan Task 3 那样的独立 gate 映射（那里 _run_ship_gate 漏映射险些让信号空死；此处 `事件重演` 已从 `sig["reenact_hits"]` 派生，天然跟随）。

改动：
- 解包：`reenact_hits, reenact_filtered = await _plane_check(...)`（1387）。`reenact_hits` 现为清后真重演列表。
- **新增 advisory 字段** `控制面重演_视角转述滤除` = `reenact_filtered or ["无"]`（报告 dict，1453 附近）—— 透明留痕，供测不准/校准审计，**只**进报告，不进 sig、不喂闸门、不进 signals。
- schema 不动（reenact_hits 既有 key，值变干净，SIGNAL_SCHEMA_VERSION 维持 1）。
- **接线回归测试必须断言**：三个消费者（gate 的 `事件重演`、报告 `控制面重演核对`、signals.reenact_hits）取的都是清后数，且 `控制面重演_视角转述滤除` 不进 sig/不喂闸门。

### 成本

裁决只在 raw hits 上跑（hit 很少，整本通常 <10），每 hit +1 flash call，可忽略。

## 测试

### 单测（FakeClient，零真实 API；复用 tests/test_repair_readback.py 的 per-bucket 队列模式）

- `_adjudicate` reenact:true → hit 进 reenact_hits、不进 filtered。
- `_adjudicate` reenact:false → hit 进 filtered、不进 reenact_hits。
- 裁决器空响应/异常 → 保守保留（进 reenact_hits）。
- raw hits 为空 → 跳过裁决，返回 `([], [])`。
- 多 hit 跨章并发归类正确（部分 true 部分 false 不串位）。
- `_run_ship_gate` 与 `signals.reenact_hits` 取的是清后数（接线回归）。

### 校准验收（标注集，detect→adjudicate 实跑，类比 holdout 坐实）

一次性脚本（scratchpad，类似 holdout_seam_replay.py）在 ZYGGY02252 + CPBXN00188 上重跑 `_plane_check`：
- **必须丢弃**（FP 应被滤）：ZYGGY ch29、ch38。
- **必须保留**（真重演 TP）：CPBXN ch49（伪进展）、ch18。
- 预期：ZYGGY reenact_hits 4 → 降（ch29×3/ch38 滤除）；CPBXN ch49 仍留。

**验收门槛**：标注样本上 **0 漏真重演**（漏一个真重演=不通过，偏向召回）；FP 滤除率尽量高。

## 受影响文件

- `src/hiki/prompts.py` — 新增 `REENACT_ADJUDICATE`。
- `src/hiki/produce.py` — `_plane_check` 二段化 + 返回二元组；调用点解包；新增 advisory 报告字段；接线清后数到 gate/signals。
- `tests/test_reenact_precision.py`（新）— 单测。
- scratchpad 校准脚本（一次性，不入库）。
