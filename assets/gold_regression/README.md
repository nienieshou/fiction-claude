# 金标回归网（E2）

两层，两种预言机：

## Tier-A — 确定性门决策快照（零 API，进 CI）
- 夹具: `<slug>/fixture.json` = 冻结 `report["signals"]` + 期望 deliverable + ship_issues。
- 测试: `tests/test_gold_regression.py` 经 `gate.signal_vector_to_gate_input` 桥接重跑门，逐位比对。
- 护什么: 交付门逻辑/阈值/ship_issue 串/DIMENSIONS 注册表(C6)/共享门(C7)/config 单源(D) 重构不退化。
- **不护**: 检测器内部 + 信号装配(原始检出→计数) 的改动——见下方 backlog。
- 书单: 7 本(2 拒本 + 2 边界 + 3 净本/含 defect_bank 双角色)，覆盖修仙/古言/都市/玄幻/探险。

## Tier-B — 语义召回（烧 API，标 @pytest.mark.api，不进 CI）
- 召回: `scripts/regression_replay.py`(飞轮②) 对 `defect_bank.jsonl` 中 baseline_hit=true 的缺陷重检，新漏一个=FAIL。
- 误报: 对 `clean_guards.json` 三本认证净本重检，新增假阳超基线带=FAIL。
- 不变量(零 API): `tests/test_defect_bank_invariants.py` 防标注腐烂。

## 重钉策略
有意改动导致 Tier-A 红灯 → `python scripts/gold_snapshot.py --repin <slug>`，commit 写
`re-pin: <slug> <旧决策>→<新决策> 原因`。无 re-pin 说明的红灯一律当退化处理。

## Backlog（本期不做）
- 题材洞: 末世(测 dark_ratio 门)/星际/七零 需新跑产物(¥)。
- 装配层网: 冻结 `fact_table.json` 原始检出 → 离线重跑 spine/复活计数装配，护 C1 CharacterStateLedger 重构。
