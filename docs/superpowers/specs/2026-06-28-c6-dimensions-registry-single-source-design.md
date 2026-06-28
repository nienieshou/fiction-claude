# C6 子项目① — DIMENSIONS 转可信单源 + 一致性守卫 设计

> 2026-06-28 · 技术债 C6(检测器 sprawl:~半数 37 维是 advisory/哨兵,算了就扔)第一片。
> C6 全量需拆多子项目(本 spec 只做"地基"片);基于:`master`(独立)。配套:`docs/design/tech-debt.md` C6 行。

## 背景(已核实,master)

- `audit.DIMENSIONS`(`audit.py:25-67`)是 37 维**描述性目录**(`Dim(id,name,axis,kind,status)`),`status` 仅 `✓/~/advisory/metric`,**无 gating 布尔**。
- grep 证 `DIMENSIONS` **只在定义处出现,被任何代码消费**——死目录(纯文档)。
- 真正的交付门是**另一套**:`gate.evaluate_ship_gate(sig, thr)`(`gate.py:172-207`)消费一组中文信号键,由 `gate.signal_vector_to_gate_input`(`gate.py:210-235`)从冻结信号向量桥接。门信号与 37 维**不同构**:部分维↔信号、部分信号是非维灾难地板、部分信号被 config 关成 advisory。

**门实际消费键**(evaluate_ship_gate 分支):`阵营串线`(>0)、`过短章数`(≥3)、`暗黑比`(>0.25)、`预告跳过`(仅 block_on_climax_skip)、`plan维14复活`(>0且未跑事实表)、`事实表复活残留`(>0)、`残缝`(>8)、`final_consistent`(仅 block_on_final_inconsistent)、`事件重演`(≥7且 block_on_reenact)、`章内双版本`(真值)、`数值真矛盾+身份真矛盾`(≥6 spine网)、`承重审计崩溃`(真值)、`开篇代入感`(<40,可被`早段重复`封顶)。
默认 config:`block_on_reenact/climax_skip/final_consistent` 均 `False`(advisory)。

## 目标

把死目录变成**可信、测试背书**的单源:每维标注是否 gating + 喂哪个门信号;守卫测防目录与真门漂移。**纯元数据 + 测试,零运行时行为改动。**

**风险姿态:行为保持** —— 不碰运行时代码路径,不改阈值/config,不让门读目录(子项目③)。

## 架构

### ① 扩 `Dim` dataclass(加默认字段,37 条原位置构造不破)
```python
@dataclass
class Dim:
    id: int
    name: str
    axis: str
    kind: str
    status: str
    gating: bool = False                  # 默认配置下该维是否产生硬拦
    signals: tuple[str, ...] = ()          # 喂 evaluate_ship_gate 的输入键(advisory→空)
```
37 条沿用现位置参数(新字段走默认);仅给清晰 gating 维显式置 `gating=True, signals=(...)`。

### ② 哪些维 gating(默认 config,保守只取干净 1:1 对应)
| 维 | signals | 门分支(evaluate_ship_gate) |
|---|---|---|
| 2 阵营归属/随从匹配 | `("阵营串线",)` | `阵营串线>0` 硬拦 |
| 6 数值/资源账一致 | `("数值真矛盾",)` | `数值真矛盾+身份真矛盾≥spine_net_min(6)` |
| 12 称谓/身份一致 | `("身份真矛盾",)` | 同上(spine 薄网,数值+身份合计) |
| 14 生死/伤势状态 | `("plan维14复活","事实表复活残留")` | `plan维14复活>0`(未跑事实表兜底)/ `事实表复活残留>0` |

- `事件重演`/`预告跳过`/`final_consistent` 现 `block_on_*=False` → **gating=False**(注释标"config 可翻 → 届时改标")。
- 维 6 与 12 共同喂 spine 薄网(门里二者**求和**比阈),故二者各列其分量 signal,均 `gating=True`(任一分量贡献该硬门)。

### ③ 非维地板(不在 37 维注册表内,显式记 companion 常量)
```python
# 门的非维灾难地板/定类硬门 —— 不属 37 维(篇幅/内容比/修复残差/代入感/元状态),
# 列此以示注册表是"维视角",门另有非维门(防误读注册表为完整门规格)。
NON_DIM_GATE_FLOORS: tuple[str, ...] = (
    "过短章数", "暗黑比", "残缝", "开篇代入感", "早段重复", "承重审计崩溃", "章内双版本",
)
```
- `章内双版本` 关联维 4(场景/事件唯一)但非干净 1:1(章内 12-gram 检测地板),**判断:归非维地板**,注释标明。

### ④ 一致性守卫测(`tests/test_dimensions_registry.py`,mock-free,纯函数驱动)
1. **gating 维真 gating**:对每个 `gating=True` 维的每个 `signal`,在一份"全良性"基线 sig dict 上把该 signal 置触发值 → `gate.evaluate_ship_gate(sig)`(默认 thr)必返**非空** issue 列表。(`数值真矛盾`/`身份真矛盾` 置 spine_net_min(6) 触发;`阵营串线`/`plan维14复活`/`事实表复活残留` 置 1 触发,且 `plan维14复活` 配 `事实表跑过=False`。)
2. **advisory 真不 gating**:基线上把 `事件重演=99`、`预告跳过="x"`、`final_consistent=False` 分别置触发值 → 默认 config 下 `evaluate_ship_gate` 对这些**不产** issue(证 `block_on_*=False` 降级生效)。
3. **分类钉死**:`{d.id for d in audit.DIMENSIONS if d.gating} == {2, 6, 12, 14}`(漂移即断)。
4. **signal 名有效**:每个 gating 维引用的 signal 键 ∈ `set(gate.signal_vector_to_gate_input({}).keys())`(防 typo/死信号名;该桥接输出含全部门输入键)。

## 验证
- 新 `tests/test_dimensions_registry.py`(上述 4 类守卫)。
- `python -m pytest -q` 全量 + 金标/装配回归网绿(本切零运行时路径改动 → 天然等价)。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- 不让 gate/扫描器读目录 gating 标(子项目③,行为敏感)。
- 不省 token / 不动 advisory 扫描器(craft/early_repeat/event_state)(子项目②)。
- 不改任何阈值/config/信号计算。`DIMENSIONS` 仍不进运行时——本切只让它"可信",不让它"驱动"。
- 不收编非维地板进 37 维(它们本就非维)。

## 风险
- **dim↔signal 映射判断**:保守只认 {2,6,12,14} 干净 1:1;`章内双版本`/reenact 等归地板或 advisory,守卫②③把判断**钉成可回归的断言**(后续若改判,改注册表+测一处即可)。
- **加字段破构造**:新字段全给默认值,37 条位置构造零改;仅 4 条追加 kw,diff 最小。
- **config 漂移**:gating 反映**默认** config;守卫读默认 thr。若将来 `block_on_reenact=True`,守卫②会按预期失败 → 提示同步注册表(这正是守卫价值)。
- **零行为改动**:不触运行时路径,gold/装配网天然绿(非"靠校准证等价",是"无路径可变")。
