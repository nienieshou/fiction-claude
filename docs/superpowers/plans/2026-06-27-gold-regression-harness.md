# 金标回归网（E2 Tier-A）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一张**零 API、确定性、进 CI** 的金标回归网，在交付门/信号装配/阈值/注册表被重构时，自动红灯任何让金标书交付决策（ship/reject + ship_issues）翻动的改动——为后续 C 类检测器合并提供"行为等价"证明工具。

**Architecture:** 检测器分三层——①LLM 检测（贵、非确定）②信号装配（纯）③交付门（纯）。本网钉在 ②③ 边界：把 7 本金标书的**冻结英文信号向量** `report["signals"]` 快照成夹具，经新建桥接函数 `gate.signal_vector_to_gate_input` 还原中文门输入，重跑 `gate.evaluate_ship_gate` 逐位比对冻结决策。Tier-B 语义召回（缺陷库 + 净本误报）烧 API、标 `@pytest.mark.api`、不进 CI，复用既有 `scripts/regression_replay.py`。

**Tech Stack:** Python 3.10+，pytest，纯标准库（json/pathlib）。无新依赖。

## Global Constraints

- **Python ≥3.10**；不新增第三方依赖（标准库 json/pathlib 即可）。
- **不改默认管线行为**：本计划只新增文件 + 一个纯函数；`src/hiki/produce.py` 的 run 路径零行为变更。
- **信号 schema 冻结纪律**（见 `src/hiki/signals.py` 头注）：只许追加新键、默认 None，严禁改名/删既有键；本计划不动 `signals.py`。
- **`pytest -m 'not api'` 必须离线全绿**：Tier-A 网零 API；Tier-B 一律标 `@pytest.mark.api`（`pyproject.toml` 已默认 `-m 'not api'` 排除）。
- **金标书单（已定）**：层 A 全收 7 本（盘上已有冻结产物）。认证净本=`ZYGGY02252`/`ZYGGY02079`/`CPBXN00188`；其余 4 本只作信号快照。题材洞（末世/星际/七零）留 backlog，不在本计划新跑。
- **编码**：所有读写 UTF-8；脚本对 `output/<slug>/report.json` 用 `encoding="utf-8"`。
- **重钉策略**：有意改动信号/阈值导致金标决策变动时，必须用 `scripts/gold_snapshot.py --repin <slug>` 重生夹具，并在 commit 信息写 `re-pin: <slug> <旧决策>→<新决策> 原因`。

金标书 7 本（slug → output 目录名前缀 → 角色）：

| slug | output 目录 | 题材 | 交付 | 角色 |
|---|---|---|---|---|
| BPBXS00052 | `BPBXS00052极品全能小村医_20260625_full` | 都市村医 | 拒 | reject_guard(过短) |
| CPBGX00031 | `CPBGX00031我真不是大罗金仙带房穿越修仙世界73W_20260625_full` | 修仙 | 放 | snapshot(defect_bank盲区) |
| CPBGX00056 | `CPBGX00056反派：记忆曝光女主为我痛哭反派记忆曝光全世界都为我流泪73w_20260625_full` | 反派玄幻 | 拒 | reject_guard(死人复活) |
| CPBGX00192 | `CPBGX00192灵气复苏：开局无限合成_20260625_full` | 修仙灵气 | 放 | snapshot(defect_bank命中) |
| CPBXN00188 | `CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full` | 探险直播 | 放 | clean_guard + 边界(spine=5/门6) |
| ZYGGY02079 | `ZYGGY02079农女为后：皇上独宠我` | 宫斗古言 | 放 | clean_guard |
| ZYGGY02252 | `ZYGGY02252归隐田园：执子手共白头` | 田园古言 | 放 | clean_guard |

---

## Task 1: 信号向量 → 交付门输入 桥接函数

把英文冻结信号向量（`signals.build_signal_vector` 的输出 = `report["signals"]`）映射成 `evaluate_ship_gate` 消费的中文门输入。这座桥是回归网的钉点，也是"两套信号词汇手工同步"（C 邻接债）的单一来源。

**Files:**
- Modify: `src/hiki/gate.py`（在 `evaluate_ship_gate` 之后追加函数）
- Test: `tests/test_signal_gate_bridge.py`

**Interfaces:**
- Consumes: `gate.evaluate_ship_gate(sig, thr)`（已存在，消费中文键）；`signals.build_signal_vector(...)` 输出的英文键 dict。
- Produces: `gate.signal_vector_to_gate_input(sv: dict, extra: dict | None = None) -> dict` —— 返回 `evaluate_ship_gate` 可直接消费的中文键 dict。`sv` 缺失的门字段（阵营串线/plan维14复活/事实表跑过/承重审计崩溃/预告跳过）取良性默认，可由 `extra` 注入真值。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_signal_gate_bridge.py
from hiki import gate, signals


def _clean_vector(**over):
    sv = signals.build_signal_vector(
        deliverable=True, grade="A", immersion_score=85, reenact_hits=4,
        seam_detected=13, seam_residual=1, dark_ratio=0.03,
        spine_num_contra=3, spine_id_contra=0, ft_revival_residual=0,
        too_short_chapters=0, final_consistent=True, intra_repeat_chapters=0)
    sv.update(over)
    return sv


def test_bridge_clean_vector_ships():
    gi = gate.signal_vector_to_gate_input(_clean_vector())
    assert gate.evaluate_ship_gate(gi) == []          # 干净本 → 无 ship_issue


def test_bridge_too_short_rejects():
    gi = gate.signal_vector_to_gate_input(_clean_vector(too_short_chapters=4))
    issues = gate.evaluate_ship_gate(gi)
    assert any("过短" in i for i in issues)


def test_bridge_revival_residual_rejects():
    gi = gate.signal_vector_to_gate_input(_clean_vector(ft_revival_residual=1))
    issues = gate.evaluate_ship_gate(gi)
    assert any("死人复活" in i for i in issues)


def test_bridge_seam_boundary_8_passes():
    # 残缝阈值 seam_residual_max=8，>8 才拦；=8 必须放
    gi = gate.signal_vector_to_gate_input(_clean_vector(seam_residual=8))
    assert not any("残缝" in i for i in gate.evaluate_ship_gate(gi))


def test_bridge_extra_injects_nonvector_field():
    gi = gate.signal_vector_to_gate_input(_clean_vector(), extra={"阵营串线": 2})
    assert any("阵营串线" in i for i in gate.evaluate_ship_gate(gi))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_signal_gate_bridge.py -q`
Expected: FAIL — `AttributeError: module 'hiki.gate' has no attribute 'signal_vector_to_gate_input'`

- [ ] **Step 3: 实现桥接函数**

在 `src/hiki/gate.py` 的 `evaluate_ship_gate` 函数之后追加：

```python
def signal_vector_to_gate_input(sv: dict, extra: dict | None = None) -> dict:
    """英文冻结信号向量(signals.build_signal_vector / report["signals"]) → 中文交付门输入
    (evaluate_ship_gate 消费)。单一桥接,消除两套信号词汇的手工同步(C 邻接债)。

    sv 不含的门字段(阵营串线/plan维14复活/事实表跑过/承重审计崩溃/预告跳过)默认良性,
    可由 extra(取自完整 report)注入真值。章内双版本: sv 存计数,门只用真值性,透传即可。"""
    e = extra or {}
    intra = sv.get("intra_repeat_chapters")
    return {
        "阵营串线": e.get("阵营串线", 0),
        "过短章数": sv.get("too_short_chapters", 0) or 0,
        "暗黑比": sv.get("dark_ratio", 0) or 0,
        "预告跳过": e.get("预告跳过"),
        "plan维14复活": e.get("plan维14复活", 0),
        "事实表跑过": e.get("事实表跑过", True),
        "事实表复活残留": sv.get("ft_revival_residual", 0) or 0,
        "残缝": sv.get("seam_residual", 0) or 0,
        "final_consistent": sv.get("final_consistent", True),
        "事件重演": sv.get("reenact_hits", 0) or 0,
        "章内双版本": intra if intra else None,
        "数值真矛盾": sv.get("spine_num_contra", 0) or 0,
        "身份真矛盾": sv.get("spine_id_contra", 0) or 0,
        "承重审计崩溃": e.get("承重审计崩溃", False),
        "开篇代入感": sv.get("opening_immersion"),
        "早段重复": sv.get("early_repeat", 0) or 0,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_signal_gate_bridge.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add src/hiki/gate.py tests/test_signal_gate_bridge.py
git commit -m "feat(gate): signal_vector_to_gate_input 桥接 — 英文冻结向量→中文门输入,单一来源"
```

---

## Task 2: 金标快照工具 + 生成 7 本夹具

读 `output/<dir>/report.json`，抽 `signals` + `deliverable`，经桥接重跑门做**自校验**（还原决策须与 producer 记录的 deliverable 一致，否则拒写），落 `assets/gold_regression/<slug>/fixture.json`。

**Files:**
- Create: `scripts/gold_snapshot.py`
- Create: `assets/gold_regression/<slug>/fixture.json`（×7，由脚本生成）
- Test: `tests/test_gold_snapshot.py`

**Interfaces:**
- Consumes: `gate.signal_vector_to_gate_input`、`gate.evaluate_ship_gate`（Task 1）。
- Produces: `gold_snapshot.snapshot_one(report: dict, slug: str, role: str) -> dict` 返回夹具 dict，键 = `{slug, role, signal_schema_version, signals, expected_deliverable, expected_ship_issues}`；不一致时 `raise ValueError`。CLI: `python scripts/gold_snapshot.py`（按内置 ROSTER 全生成）/ `--repin <slug>`（重生单本）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_gold_snapshot.py
import json
import pytest
from pathlib import Path
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "gold_snapshot", Path(__file__).resolve().parents[1] / "scripts" / "gold_snapshot.py")
gold_snapshot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gold_snapshot)


def _report(**sig_over):
    sig = {
        "schema_version": 1, "deliverable": True, "grade": "A", "opening_immersion": 85,
        "reenact_hits": 4, "seam_detected": 13, "seam_residual": 1, "dark_ratio": 0.03,
        "spine_num_contra": 3, "spine_id_contra": 0, "ft_revival_residual": 0,
        "too_short_chapters": 0, "final_consistent": True, "intra_repeat_chapters": 0,
        "early_repeat": None, "opening_overload": None}
    sig.update(sig_over)
    return {"deliverable": sig["deliverable"], "signals": sig}


def test_snapshot_clean_ship():
    fx = gold_snapshot.snapshot_one(_report(), "ZYGGY02252", "clean_guard")
    assert fx["expected_deliverable"] is True
    assert fx["expected_ship_issues"] == []
    assert fx["signal_schema_version"] == 1


def test_snapshot_reject_too_short():
    fx = gold_snapshot.snapshot_one(
        _report(deliverable=False, too_short_chapters=4), "BPBXS00052", "reject_guard")
    assert fx["expected_deliverable"] is False
    assert any("过短" in i for i in fx["expected_ship_issues"])


def test_snapshot_refuses_when_decision_mismatch():
    # producer 记 deliverable=True，但信号含 4 章过短 → 还原必拒 → 不一致 → 拒写
    with pytest.raises(ValueError, match="决策不一致"):
        gold_snapshot.snapshot_one(
            _report(deliverable=True, too_short_chapters=4), "X", "snapshot")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_gold_snapshot.py -q`
Expected: FAIL — `ModuleNotFoundError` 或 `AttributeError: ... 'snapshot_one'`

- [ ] **Step 3: 实现脚本**

```python
# scripts/gold_snapshot.py
"""金标快照工具(E2 Tier-A): output/<dir>/report.json → assets/gold_regression/<slug>/fixture.json。
自校验=经桥接还原的门决策须与 report.deliverable 一致,否则拒写(信号向量不足以复现决策)。
用法: python scripts/gold_snapshot.py [--repin <slug>]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hiki import gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "assets" / "gold_regression"

# slug → (output 目录名, 角色)。角色: reject_guard|clean_guard|snapshot
ROSTER = {
    "BPBXS00052": ("BPBXS00052极品全能小村医_20260625_full", "reject_guard"),
    "CPBGX00031": ("CPBGX00031我真不是大罗金仙带房穿越修仙世界73W_20260625_full", "snapshot"),
    "CPBGX00056": ("CPBGX00056反派：记忆曝光女主为我痛哭反派记忆曝光全世界都为我流泪73w_20260625_full", "reject_guard"),
    "CPBGX00192": ("CPBGX00192灵气复苏：开局无限合成_20260625_full", "snapshot"),
    "CPBXN00188": ("CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full", "clean_guard"),
    "ZYGGY02079": ("ZYGGY02079农女为后：皇上独宠我", "clean_guard"),
    "ZYGGY02252": ("ZYGGY02252归隐田园：执子手共白头", "clean_guard"),
}


def snapshot_one(report: dict, slug: str, role: str) -> dict:
    sv = report["signals"]
    gi = gate.signal_vector_to_gate_input(sv)
    issues = gate.evaluate_ship_gate(gi)
    replay_deliverable = not issues
    if replay_deliverable != bool(report.get("deliverable")):
        raise ValueError(
            f"{slug} 决策不一致: 还原 deliverable={replay_deliverable} != "
            f"report={report.get('deliverable')}(信号向量不足以复现门决策,需 extra 或重跑)")
    return {
        "slug": slug,
        "role": role,
        "signal_schema_version": sv.get("schema_version"),
        "signals": sv,
        "expected_deliverable": replay_deliverable,
        "expected_ship_issues": issues,
    }


def _read_report(out_dir_name: str) -> dict:
    p = ROOT / "output" / out_dir_name / "report.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _write_fixture(fx: dict) -> Path:
    d = GOLD / fx["slug"]
    d.mkdir(parents=True, exist_ok=True)
    p = d / "fixture.json"
    p.write_text(json.dumps(fx, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main(argv: list[str]) -> None:
    only = None
    if len(argv) >= 2 and argv[0] == "--repin":
        only = argv[1]
    for slug, (out_dir, role) in ROSTER.items():
        if only and slug != only:
            continue
        fx = snapshot_one(_read_report(out_dir), slug, role)
        p = _write_fixture(fx)
        print(f"{'拒' if not fx['expected_deliverable'] else '放'}  {slug}  → {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: 跑单测确认通过**

Run: `python -m pytest tests/test_gold_snapshot.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 生成 7 本真夹具并核对**

Run: `python scripts/gold_snapshot.py`
Expected: 打印 7 行；`BPBXS00052` 与 `CPBGX00056` 显示"拒"，其余 5 本"放"。若任一本抛 `决策不一致` → 该本 `report["signals"]` 缺字段，记录到计划备注、改用 `extra` 注入（暂从 ROSTER 排除并在 README 标注），不要硬塞。

- [ ] **Step 6: 提交**

```bash
git add scripts/gold_snapshot.py tests/test_gold_snapshot.py assets/gold_regression/
git commit -m "feat(gold): 金标快照工具 + 7 本 Tier-A 夹具(自校验门决策)"
```

---

## Task 3: 回归网测试（进 CI，零 API）

加载全部夹具，桥接 + 重跑门，逐位比对冻结决策。这是网本体。

**Files:**
- Create: `tests/test_gold_regression.py`

**Interfaces:**
- Consumes: `assets/gold_regression/*/fixture.json`（Task 2）；`gate.signal_vector_to_gate_input` + `gate.evaluate_ship_gate`（Task 1）。

- [ ] **Step 1: 写测试（此时夹具已存在 → 应直接通过，作为"网已张开"的活证据）**

```python
# tests/test_gold_regression.py
"""金标回归网(E2 Tier-A): 冻结金标书的门决策不许被改动悄悄翻动。零 API,进 CI。
有意改动导致红灯 → 用 `python scripts/gold_snapshot.py --repin <slug>` 重钉,commit 写 re-pin。"""
import json
from pathlib import Path
import pytest
from hiki import gate

GOLD = Path(__file__).resolve().parents[1] / "assets" / "gold_regression"
FIXTURES = sorted(GOLD.glob("*/fixture.json"))


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_gold_set_nonempty():
    assert len(FIXTURES) >= 7, f"金标夹具不足: {len(FIXTURES)} < 7"


@pytest.mark.parametrize("fx_path", FIXTURES, ids=[p.parent.name for p in FIXTURES])
def test_gold_decision_frozen(fx_path):
    fx = _load(fx_path)
    gi = gate.signal_vector_to_gate_input(fx["signals"])
    issues = gate.evaluate_ship_gate(gi)
    assert issues == fx["expected_ship_issues"], (
        f"{fx['slug']} ship_issues 变动:\n  期望={fx['expected_ship_issues']}\n  实得={issues}\n"
        f"  若为有意改动→ python scripts/gold_snapshot.py --repin {fx['slug']}")
    assert (not issues) == fx["expected_deliverable"], f"{fx['slug']} 交付决策翻转"


def test_clean_guards_ship():
    # 认证净本必须保持可交付——误报守卫
    for p in FIXTURES:
        fx = _load(p)
        if fx["role"] == "clean_guard":
            assert fx["expected_deliverable"] is True, f"{fx['slug']} 净本竟不可交付"


def test_reject_guards_blocked():
    # 拒本必须保持被拦——漏放守卫
    for p in FIXTURES:
        fx = _load(p)
        if fx["role"] == "reject_guard":
            assert fx["expected_deliverable"] is False, f"{fx['slug']} 拒本竟可交付"
```

- [ ] **Step 2: 跑测试确认通过**

Run: `python -m pytest tests/test_gold_regression.py -q`
Expected: PASS（≥10 passed：7 参数化 + 3 不变量）

- [ ] **Step 3: 跑全量套件确认零退化**

Run: `python -m pytest -q`
Expected: 全绿，passed 数 = 旧基线 + 本计划新增；`1 deselected`（api）。

- [ ] **Step 4: 验证网真会红灯（人为破坏 → 必失败 → 还原）**

Run（临时把某本 `expected_ship_issues` 改一个字再跑，确认 FAIL，然后 `git checkout` 还原）：
```bash
python -m pytest tests/test_gold_regression.py -q   # 改后应 FAIL
git checkout assets/gold_regression/                # 还原
```
Expected: 改后 FAIL（证明网有效），还原后 PASS。

- [ ] **Step 5: 提交**

```bash
git add tests/test_gold_regression.py
git commit -m "feat(gold): Tier-A 回归网进 CI — 金标书门决策逐位冻结,零 API"
```

---

## Task 4: Tier-B 语义守卫（缺陷库覆盖不变量，零 API）+ API 召回接线说明

Tier-B 的 API 召回**已存在** `scripts/regression_replay.py`（飞轮②）。本任务只补两件零 API 的：①`defect_bank.jsonl` 的 schema/覆盖不变量测试（防标注腐烂）；②把 3 本认证净本登记为误报守卫清单，供 API 召回模式读取。

**Files:**
- Create: `tests/test_defect_bank_invariants.py`
- Create: `assets/gold_regression/clean_guards.json`

**Interfaces:**
- Consumes: `assets/defect_bank.jsonl`（19 行，键 `book/path/ch/cat/detector/baseline_hit/id`）。
- Produces: `assets/gold_regression/clean_guards.json` = `["ZYGGY02252","ZYGGY02079","CPBXN00188"]`，供后续 `scripts/regression_replay.py --clean-guard` 读取（接线点，本任务不改 replay 脚本）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_defect_bank_invariants.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "assets" / "defect_bank.jsonl"
GUARDS = ROOT / "assets" / "gold_regression" / "clean_guards.json"

REQUIRED_KEYS = {"book", "path", "ch", "cat", "detector", "id", "baseline_hit"}


def _rows():
    return [json.loads(l) for l in BANK.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_every_row_has_required_keys():
    for r in _rows():
        missing = REQUIRED_KEYS - r.keys()
        assert not missing, f"defect {r.get('id','?')} 缺键 {missing}"


def test_ids_unique():
    ids = [r["id"] for r in _rows()]
    assert len(ids) == len(set(ids)), "defect_bank id 有重复"


def test_baseline_hit_is_bool():
    for r in _rows():
        assert isinstance(r["baseline_hit"], bool), f"{r['id']} baseline_hit 非 bool"


def test_clean_guards_present():
    guards = json.loads(GUARDS.read_text(encoding="utf-8"))
    assert set(guards) == {"ZYGGY02252", "ZYGGY02079", "CPBXN00188"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_defect_bank_invariants.py -q`
Expected: FAIL — `clean_guards.json` 不存在（`FileNotFoundError`）；前三测可能因现有行缺键而 FAIL（记录哪些行缺，下一步补齐或在 README 标注）。

- [ ] **Step 3: 建净本守卫清单**

```json
// assets/gold_regression/clean_guards.json
["ZYGGY02252", "ZYGGY02079", "CPBXN00188"]
```

若 Step 2 暴露 `defect_bank.jsonl` 有行缺 `REQUIRED_KEYS`（首两行已知含全部键），逐行补齐缺字段（`detector` 缺→填 `"none"` 表示已知检测缺口；`baseline_hit` 缺→按该缺陷当前是否被检出填 `true`/`false`）。不要删行。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_defect_bank_invariants.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add tests/test_defect_bank_invariants.py assets/gold_regression/clean_guards.json
git commit -m "feat(gold): Tier-B 缺陷库覆盖不变量 + 认证净本守卫清单"
```

---

## Task 5: 文档 + 刷新 tech-debt 登记

**Files:**
- Create: `assets/gold_regression/README.md`
- Modify: `docs/design/tech-debt.md`（E2 行状态）

- [ ] **Step 1: 写 README**

```markdown
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
```

- [ ] **Step 2: 刷新 tech-debt E2 行**

将 `docs/design/tech-debt.md` 中 E2 行状态由 `⬜` 改为 `◐`，备注追加：
`Tier-A 门决策快照网已建(7 本金标,零 API 进 CI,docs:assets/gold_regression/);残: 装配层网(冻 fact_table 重跑计数,护 C1)+题材洞补本`。

- [ ] **Step 3: 全量套件最终确认**

Run: `python -m pytest -q`
Expected: 全绿；`1 deselected`。

- [ ] **Step 4: 提交**

```bash
git add assets/gold_regression/README.md docs/design/tech-debt.md
git commit -m "docs(gold): 金标回归网 README + tech-debt E2 刷新为 ◐"
```

---

## Self-Review

- **Spec 覆盖**: ①"放多少本"→ Global Constraints + ROSTER(7 本，角色明确)；②"什么算退化"→ Task 3(Tier-A 逐位决策比对)+ Task 4(Tier-B 召回/误报，接线既有 replay)。✅
- **零 API/CI 纪律**: Task 1-4 全离线；Tier-B API 召回不在本计划新建、复用 `regression_replay.py`，README 标注。✅
- **不改默认管线**: 仅新增 1 纯函数 + 新文件，produce.run 零改。✅
- **类型一致**: `signal_vector_to_gate_input`(Task1) → `snapshot_one`(Task2) → `test_gold_regression`(Task3) 三处签名/键名一致(`signals`/`expected_ship_issues`/`expected_deliverable`/`role`)。✅
- **已知近似（非占位，明确记录）**: 桥接对 `章内双版本` 透传计数而非 producer 的列表显示——门只用真值性，决策等价；7 本金标 intra=0，无影响。若未来金标本 intra>0，Task2 自校验会因显示串差异暴露，届时精化桥接。
- **风险**: Task 2 Step 5 若某本 `report["signals"]` 缺字段致"决策不一致"——已给降级路径(排除该本+README 标注+用 extra)，不硬塞。
```
