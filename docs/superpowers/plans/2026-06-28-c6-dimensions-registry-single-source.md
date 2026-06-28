# C6 子项目① — DIMENSIONS 转可信单源 + 一致性守卫 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给死目录 `audit.DIMENSIONS` 加 `gating`/`signals` 字段如实标注哪些维硬拦门,加 `NON_DIM_GATE_FLOORS` 常量记非维地板,加一致性守卫测断言"目录 gating 集 = 门实际硬拦"——纯元数据 + 测试,零运行时行为改动。

**Architecture:** 扩 `Dim` dataclass(2 个带默认值的新字段,37 条位置构造不破);4 条 gating 维(2/6/12/14)显式置 `gating=True, signals=(...)`;新增 `NON_DIM_GATE_FLOORS` 常量;新增 `tests/test_dimensions_registry.py` 用 `evaluate_ship_gate` 纯函数驱动守卫。

**Tech Stack:** Python ≥3.10,标准库,pytest。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-28-c6-dimensions-registry-single-source-design.md`(读它拿门消费键全表 + gating 维映射 + 非维地板理由)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。**
- **零运行时行为改动**:不触任何运行时代码路径(`DIMENSIONS` 仍不进运行时);不改阈值/config/信号计算。新字段全带默认值,37 条原位置构造零改,仅 4 条追加 kwargs。
- **gating 反映默认 config**:`block_on_reenact/climax_skip/final_consistent` 均 `False`(advisory);守卫读默认 thr(`evaluate_ship_gate(sig)` 不传 thr)。
- **保守 gating 维集 `{2, 6, 12, 14}`**:只认干净 1:1 对应;`章内双版本`/reenact 等归非维地板或 advisory。
- `pytest -m 'not api'` 离线全绿 + 金标/装配回归网绿。编码 UTF-8。

---

## Task 1: Dim 扩字段 + gating 标注 + NON_DIM_GATE_FLOORS + 一致性守卫测

**Files:**
- Modify: `src/hiki/audit.py`(`Dim` dataclass:16-22;`DIMENSIONS` 维 2/6/12/14:28/32/38/40;`DIMENSIONS` 列表后加 `NON_DIM_GATE_FLOORS`)
- Create: `tests/test_dimensions_registry.py`
- Modify: `docs/design/tech-debt.md`(C6 行)
- Read first: `audit.py:16-67`(Dim + DIMENSIONS 现状)、`gate.py:172-235`(evaluate_ship_gate + signal_vector_to_gate_input,确认门消费键)

**Interfaces:**
- Produces: `audit.Dim` 新增 `gating: bool = False`、`signals: tuple[str, ...] = ()`;`audit.NON_DIM_GATE_FLOORS: tuple[str, ...]`
- Consumes: `gate.evaluate_ship_gate(sig: dict) -> list[str]`、`gate.signal_vector_to_gate_input(sv: dict) -> dict`(均现存,不改)

- [ ] **Step 1: 写守卫失败测试**

新建 `tests/test_dimensions_registry.py`:
```python
"""C6 子项目①: DIMENSIONS 可信单源 + 一致性守卫(目录 gating 集 = 门实际硬拦)。
零 API; 纯函数驱动 evaluate_ship_gate。"""
from hiki import audit, gate


def _benign_sig() -> dict:
    """全良性基线: evaluate_ship_gate(默认 thr) 应零 issue。"""
    return {
        "阵营串线": 0, "过短章数": 0, "暗黑比": 0.0, "预告跳过": None,
        "plan维14复活": 0, "事实表跑过": True, "事实表复活残留": 0,
        "残缝": 0, "final_consistent": True, "事件重演": 0, "章内双版本": None,
        "数值真矛盾": 0, "身份真矛盾": 0, "承重审计崩溃": False,
        "开篇代入感": 100, "早段重复": 0,
    }


# 每个 gating signal → (触发值, 需附带的其他键覆盖)
_TRIGGER = {
    "阵营串线": (1, {}),
    "数值真矛盾": (6, {}),
    "身份真矛盾": (6, {}),
    "plan维14复活": (1, {"事实表跑过": False}),
    "事实表复活残留": (1, {}),
}


def test_benign_baseline_no_issues():
    assert gate.evaluate_ship_gate(_benign_sig()) == []


def test_gating_dims_actually_gate():
    """每个 gating=True 维的每个 signal 触发 → 门必产 issue。"""
    for d in audit.DIMENSIONS:
        if not d.gating:
            continue
        assert d.signals, f"维{d.id} gating=True 但无 signals"
        for s in d.signals:
            val, extra = _TRIGGER[s]
            sig = _benign_sig()
            sig[s] = val
            sig.update(extra)
            assert gate.evaluate_ship_gate(sig), f"维{d.id} signal {s} 触发应产 issue"


def test_advisory_signals_do_not_gate_under_default_config():
    """降级信号(block_on_*=False)触发 → 默认 config 不产 issue。"""
    for s, val in (("事件重演", 99), ("预告跳过", "x"), ("final_consistent", False)):
        sig = _benign_sig()
        sig[s] = val
        assert gate.evaluate_ship_gate(sig) == [], f"{s} 默认应 advisory 不拦"


def test_gating_dim_id_set_pinned():
    """分类钉死: gating 维集漂移即断。"""
    assert {d.id for d in audit.DIMENSIONS if d.gating} == {2, 6, 12, 14}


def test_gating_signal_names_valid():
    """每个 gating 维引用的 signal 键 ∈ 门桥接输出键(防 typo/死信号名)。"""
    valid = set(gate.signal_vector_to_gate_input({}).keys())
    for d in audit.DIMENSIONS:
        for s in d.signals:
            assert s in valid, f"维{d.id} signal {s} 不在门输入键"


def test_non_dim_floors_disjoint_from_dim_signals():
    """非维地板与 gating 维 signal 不相交(地板本就非维)。"""
    dim_sigs = {s for d in audit.DIMENSIONS for s in d.signals}
    assert not (set(audit.NON_DIM_GATE_FLOORS) & dim_sigs)
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_dimensions_registry.py -q`
Expected: FAIL — `AttributeError: 'Dim' object has no attribute 'gating'`(及 `audit` 无 `NON_DIM_GATE_FLOORS`)

- [ ] **Step 3: 扩 `Dim` dataclass(`audit.py:16-22`)**

把:
```python
@dataclass
class Dim:
    id: int
    name: str
    axis: str          # 承重/笔力/人/故事性
    kind: str          # det/mech/llm
    status: str
```
改为:
```python
@dataclass
class Dim:
    id: int
    name: str
    axis: str          # 承重/笔力/人/故事性
    kind: str          # det/mech/llm
    status: str
    gating: bool = False               # C6①: 默认 config 下该维是否产生硬拦(交付门)
    signals: tuple[str, ...] = ()       # C6①: 喂 gate.evaluate_ship_gate 的输入键(advisory→空)
```

- [ ] **Step 4: 4 条 gating 维显式置标(`audit.py` 维 2/6/12/14)**

把这 4 行(分别在 28/32/38/40 附近):
```python
    Dim(2, "阵营归属/随从匹配", "承重", "det", "✓"),      # ← 张岩/格森门
...
    Dim(6, "数值/资源账一致", "承重", "det", "~"),
...
    Dim(12, "称谓/身份一致", "承重", "det", "✓"),          # ← 圣子/圣帝
...
    Dim(14, "生死/伤势状态", "承重", "det", "~"),
```
改为(只追加 kwargs,其余不动;保留各自行尾注释):
```python
    Dim(2, "阵营归属/随从匹配", "承重", "det", "✓", gating=True, signals=("阵营串线",)),      # ← 张岩/格森门
...
    Dim(6, "数值/资源账一致", "承重", "det", "~", gating=True, signals=("数值真矛盾",)),
...
    Dim(12, "称谓/身份一致", "承重", "det", "✓", gating=True, signals=("身份真矛盾",)),          # ← 圣子/圣帝
...
    Dim(14, "生死/伤势状态", "承重", "det", "~", gating=True, signals=("plan维14复活", "事实表复活残留")),
```
(维 6 与 12 各列其 spine 薄网分量 signal,均 gating=True:门里 `数值真矛盾+身份真矛盾≥6`,任一分量贡献该硬门。)

- [ ] **Step 5: 加 `NON_DIM_GATE_FLOORS`(`DIMENSIONS` 列表闭合 `]` 之后)**

```python


# C6①: 门的非维灾难地板/定类硬门 —— 不属 37 维(篇幅/内容比/修复残差/代入感/元状态/章内检测),
# 列此以示注册表是"维视角",门另有非维门(防误读注册表为完整门规格)。
# 注: 章内双版本 关联维4(场景/事件唯一)但非干净 1:1(章内 12-gram 检测地板)→ 归非维地板。
NON_DIM_GATE_FLOORS: tuple[str, ...] = (
    "过短章数", "暗黑比", "残缝", "开篇代入感", "早段重复", "承重审计崩溃", "章内双版本",
)
```

- [ ] **Step 6: 跑确认通过**

Run: `python -m pytest tests/test_dimensions_registry.py -q`
Expected: PASS（6 passed）

- [ ] **Step 7: 全量 + 金标/装配网(零行为改动验证)**

Run: `python -m pytest tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全绿(本切零运行时路径改动)。
Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。报告确切 passed/deselected 数。

- [ ] **Step 8: 刷新 `docs/design/tech-debt.md` C6 行**

`| C6 |` 状态加 `◐`,备注追加:`C6① 已落: DIMENSIONS 加 gating/signals 字段(如实标注 4 gating 维 {2,6,12,14}→门信号) + NON_DIM_GATE_FLOORS 常量 + 一致性守卫测(目录gating集=门实际硬拦, 防漂移)。纯元数据+测试零行为改动。残: 让门/扫描器读目录gating(②)/ config门控白烧advisory扫描器(③省token)`。

- [ ] **Step 9: 提交**

```bash
git add src/hiki/audit.py tests/test_dimensions_registry.py docs/design/tech-debt.md
git commit -m "feat(C6①): DIMENSIONS 加 gating/signals 字段 + NON_DIM_GATE_FLOORS + 一致性守卫(目录=门, 零行为改动)"
```

---

## Self-Review

- **Spec 覆盖**:① Dim 扩字段 → Step 3;② gating 维标注 {2,6,12,14} → Step 4;③ NON_DIM_GATE_FLOORS → Step 5;④ 4 类守卫(真gating/真不gating/分类钉死/signal名有效)→ Step 1 的 5 个测 + 非维不相交测。✅
- **行为保持**:零运行时路径改动;验收 = 金标/装配网 + 全量绿(Step 7)。新字段默认值保 37 条位置构造不破。
- **占位**:无 TBD;新代码(Dim 扩、4 维 kwargs、NON_DIM_GATE_FLOORS、整个测试文件)给完整代码;Step 4 标"保留行尾注释"是有意要求。
- **类型一致**:`Dim.gating: bool`、`Dim.signals: tuple[str,...]`、`NON_DIM_GATE_FLOORS: tuple[str,...]` 跨 spec/plan/测一致;测试引用的门函数签名 `evaluate_ship_gate(sig)`/`signal_vector_to_gate_input(sv)` 与 gate.py 现状一致。
- **风险**:① signal 名 typo → Step 1 `test_gating_signal_names_valid` 守;② gating 集判断漂移 → `test_gating_dim_id_set_pinned` 钉死;③ 加字段破构造 → 全默认值 + 仅 4 条追加 kwargs。
