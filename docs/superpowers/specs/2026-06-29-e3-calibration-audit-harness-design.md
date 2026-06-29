# E3 Slice 1 — HFL 校准数据审计 + 对齐 harness 设计

> 2026-06-29 · 技术债 E3(校准飞轮)第一片。codex 跨模型诊断 + `assets/hfl.jsonl` 数据核实后,锁定 E3=最高杠杆下一步,以**影子模式**起步(门永不生效,见决策)。基于:`master`。配套:`docs/design/tech-debt.md` E3 行、memory `e3-calibration-direction`。

## 决策(2026-06-29,用户拍板)

1. **ground truth = `网文编辑`**(`scorer=="网文编辑"`:editor-eval-1 `d5a032e` 5本 + editor-eval-2 `120ceec` 9本)。`fable`=AI 代理(占多数行)/`运营评委1`(用「故事性」非「拉力」)/`总编辑` 维度不一致 → 各为独立真值空间,**不可混池**。
2. **不采被拒书人评。** 后果(用户已知会):无被拒书标签 → 校准只能学**假阳性**(门放行但人判坏),学不到**假阴性/误拒** → **门生效永久下桌**,E3 = 永久影子假阳性分诊信号,喂人工复核,绝不自动决策。契合已锁定的「系统只产客观信号 + 标签底稿,主观三维人工」边界。

## 背景(已核实,master)

E3 是「校准 consumer 整根缺失」:`assets/hfl.jsonl`(60 行人评)被 `web/backend/adapters.py` 读作展示,但 `/api/calibration` 返回 **fixture 假数据**(`adapters.py:352` 一带),**无任何 `bias_model` 拟合/加载**。门 `gate.evaluate_ship_gate`(`gate.py:172`)仍是静态阈值,非校准预测层。

核实 `assets/hfl.jsonl`(60 行)发现两条硬约束,决定本片只能是**审计**而非建模:

1. **冻结信号 schema 在 60 行中出现 0 次。** `signals.build_signal_vector` 的 `schema_version=1` 向量从不在 hfl 行里;各行 `auto_signals` 全是各轮临时键(`战力崩坏`/`套话门`/`代入感分`/`交付门`列表…)。→ 现在无法直接拟合「冻结向量→人评」。
2. **gold fixtures ≠ 编辑评的那次跑。** gold_regression fixture(`assets/gold_regression/<slug>/fixture.json`)持有冻结向量,但**无引擎版本/commit 溯源字段**(仅 `slug/role/signal_schema_version/signals/expected_*`)。实证:`ZYGGY02252` fixture `opening_immersion=85,reenact_hits=4,seam_detected=13,deliverable=true`,而同 slug 的 `网文编辑` hfl 行(`120ceec`)`代入感分=88,控制面重演=3,章缝检出=21` → 不同次生成。`BPBXS00052` 更明显:fixture `deliverable=false` vs hfl 行 `deliverable=true`。→ **当前 0 条「冻结向量↔编辑人评」有效对齐**;若按 slug 盲配会用错位特征教模型。

**但**:`网文编辑` 行的 `auto_signals` **自带** `deliverable`(rows 47-60 全有)+ 编辑 `承重` 维 → 门↔人评分歧可**当下直接量化**,无需 gold join。实证假阳性:`BPBXS00052` 裸过门(deliverable=true)编辑给 `承重=30`;`CPBXN00233` 承重=30 裸过。这是测量危机的实证。

## 目标

建 `src/hiki/calibration.py`(纯函数,0 LLM / 0 网络 / 只读)+ 一个只读审计脚本,产出:

- **兼容性报告**:60 行按 (truth_space × dims_schema × signal_compat × version) 分桶 + 解析错误清单(fail-closed)。
- **假阳性透镜**(立即价值):`网文编辑` 行中 `deliverable==True ∧ 承重<floor` 的书 + 分歧率。
- **溯源分歧审计**(证据):对 slug 重叠书,把 hfl 旧键映射到冻结键后逐键比 gold fixture,量化分歧 → 证明「0 条可拟合对齐」,为 Slice 1b 立硬前置。

**风险姿态**:新增独立纯模块 + 只读脚本;**不碰** pipeline / 门 / web / hfl 写入。金标/装配网无关路径 → 平凡绿。

## 架构

### 新模块 `src/hiki/calibration.py`

常量(单源,显式编码决策):
```python
TRUTH_SPACE = {"网文编辑": "editor", "fable": "proxy", "运营评委1": "ops", "总编辑": "chief_editor"}
GROUND_TRUTH = "editor"          # 2026-06-29 用户决策
STANDARD4 = frozenset({"拉力", "笔力", "人", "承重"})
CHENGZHONG_FLOOR = 50            # 承重<50=结构性不合格(据编辑评语:30/40 均"前后矛盾/逻辑不通")
# hfl 旧 auto_signals 键 → 冻结向量键(仅用于溯源分歧比对,非建模)
LEGACY_TO_FROZEN = {"代入感分": "opening_immersion", "控制面重演": "reenact_hits",
                    "章缝检出": "seam_detected", "deliverable": "deliverable",
                    "暗黑比": "dark_ratio", "final_consistent": "final_consistent",
                    "过短章数": "too_short_chapters", "章内双版本": "intra_repeat_chapters"}
# 故意排除(无稳定 frozen 对应):交付门(各轮自由文本/列表)、章缝修复、
# 各类一次性键(战力崩坏/套话门/throws/classification/cost_cny/best_of…)。
```

数据模型(frozen dataclass):
```python
@dataclass(frozen=True)
class HflRow:
    line_no: int
    scorer: str
    title: str | None         # false_accept_lens 输出需书名;旧行可能仅有 source
    source: str | None
    truth_space: str          # editor/proxy/ops/chief_editor/unknown
    dims: dict
    dims_schema: str          # standard4 / story4 / other
    total: float | None
    slug: str | None          # 旧行(总编辑/fable)无 slug
    version: str | None
    auto_signals: dict
    signal_compat: str        # frozen(有schema_version) / legacy(有旧键) / none(空或仅文字)
    deliverable: bool | None  # auto_signals.get("deliverable")
```

纯函数:
```python
def load_hfl(path) -> tuple[list[HflRow], list[dict]]:
    """逐行解析 jsonl(跳空行)。畸形行 fail-closed:收进 errors[{line_no,error,raw}],
    从 rows 排除,绝不当合法行流下去。每行派生 truth_space/dims_schema/signal_compat。"""

def compat_report(rows, errors) -> dict:
    """兼容性报告:按 truth_space×dims_schema×signal_compat×version 计数,
    + n_rows/n_errors/n_ground_truth。纯聚合。"""

def false_accept_lens(rows, floor=CHENGZHONG_FLOOR) -> dict:
    """ground-truth(editor)行中 deliverable==True ∧ 承重<floor → 假阳性候选。
    返回 {flagged:[{slug,title,承重,total,version,auto_signals}], n_editor_with_deliverable, rate}。
    仅看 hfl 行自身 deliverable,不依赖 gold。"""

def load_gold_signal_vectors(gold_dir) -> dict[str, dict]:
    """slug -> fixture['signals'](冻结向量)。只读 assets/gold_regression/<slug>/fixture.json。"""

def provenance_divergence(rows, gold_vectors) -> dict:
    """editor∩slug∩(gold 有该 slug)的书:把 hfl auto_signals 经 LEGACY_TO_FROZEN 映射后,
    与 gold 冻结向量**逐可比较共享键**(两侧都 present 且类型可比的数值/布尔键)比对。
    每本归类 status ∈ {divergent, inconclusive}:
      - divergent:任一可比较共享键不相等 → **证实是不同次跑**(可对齐性=否,硬证据)。
      - inconclusive:所有可比较共享键相等,但 gold fixture **无引擎版本/commit 溯源字段**
        → 无法证实同次跑(可能巧合,尤其仅 deliverable 等少数键重叠时)→ **不算 matched**。
    返回 {books:[{slug,shared_keys,diffs,status}], n_overlap, n_divergent, n_inconclusive,
    n_provenance_matched}。**n_provenance_matched 仅在存在显式溯源元数据且一致时才 >0;
    当前 gold fixture 无该字段 → 结构性恒为 0**——绝不由 legacy 键巧合相等推断 matched
    (codex landmine:子集巧合相等会喂 Slice 2 错位训练对)。
    预期:重叠书全部 divergent 或 inconclusive,n_provenance_matched==0 → 0 可拟合对齐。"""

def format_report(compat, fa, prov) -> str:
    """三段人读摘要(纯字符串,供脚本打印)。"""
```

### 只读脚本 `scripts/calibration_audit.py`

`load_hfl(assets/hfl.jsonl)` → 三函数 → `print(format_report(...))`。零副作用、零写入。沉淀为可重复运行的审计入口(镜 `scripts/` 现有只读工具习惯)。

### 本片产出的诚实结论(实现需复现/确认,不得粉饰)

- 假阳性:editor 书里 N/14 `deliverable=true ∧ 承重<50` → 门↔编辑分歧**当下可量化**。
- 拟合数据:`n_provenance_matched==0`(结构性:gold 无溯源字段,重叠书只会落 divergent/inconclusive)→ **Slice 1b(评分时落冻结 `report["signals"]` + scorer 标签)是 Slice 2 建模的硬前置**。审计如实报「现在拟合不了」,这是结论不是失败。

## 验证

- **纯函数单测**(新 `tests/test_calibration.py`,用 `tests/` 内合成小 fixture,**不**依赖真 assets):
  - `load_hfl`:正常行解析 + 派生字段;空行跳过;畸形 JSON 行 → 进 errors 不进 rows(fail-closed)。
  - `truth_space`/`dims_schema`/`signal_compat` 分类:editor/proxy/ops、standard4 vs story4(故事性)、frozen/legacy/none 三态各覆盖。
  - `false_accept_lens`:deliverable=true∧承重<floor 命中;deliverable=false 或承重≥floor 不命中;非 editor 行不计入;floor 可调。
  - `provenance_divergence`:任一可比较共享键不等 → status=divergent;全等但无溯源字段 → status=inconclusive(**非 matched**);无可比较共享键(类型不可比/无重叠)→ inconclusive;slug 不在 gold → 不入 overlap;`n_provenance_matched` 恒为 0(无溯源元数据,绝不由巧合相等推断)。
  - `compat_report` 计数正确。
- **真数据不变量 smoke**(`tests/test_calibration_realdata.py`,跑真 `assets/hfl.jsonl`+`assets/gold_regression`):不崩;`n_rows==60`;所有 `scorer=="网文编辑"` → truth_space=="editor";报告键齐全。**断结构不变量与当前快照计数,并注:hfl 增长时更新**(characterization 性质)。
- **金标/装配网**:本片不碰 pipeline/门/web → `pytest tests/test_gold_regression.py tests/test_assembly_regression.py` 平凡绿(无路径相交)。
- 全量 `pytest -m 'not api'` 绿,报确切 passed/deselected。
- SDD:单任务 TDD + 两段复核 + opus 终审。

## 非目标

- **不拟合任何模型**(Slice 2)。本片只读、只审计、只报告。
- **不碰** pipeline / `gate` / web / hfl 写入 / `/api/calibration` fixture(那是 Slice 1b)。
- **不让校准分进门**——程序级永久影子(决策 2)。
- **不混池**非 editor 真值空间进 ground truth;**不按 slug 盲配** version 分歧的 (向量,标签)。
- 不动 A3 残 / C6③ / D3b / A1 等其余债。

## 风险

- **溯源缺失是数据事实,非本片能修**:gold fixture 无 version 字段、且与编辑评的跑分歧 → 本片只能**如实报 0 可拟合对齐**并把缺口推给 Slice 1b。把这点写进结论而非掩盖,是本片的核心价值。
- **slug 缺失**:旧行(总编辑/fable)无 slug → 自然排除出 join,兼容性报告里如实计数(`signal_compat=legacy/none`)。
- **dims schema 异构**:`运营评委1` 用「故事性」→ `dims_schema=story4`,不进 editor standard4 对齐;报告分列。
- **`承重` floor=50 的选取**:据编辑评语经验值(30/40 行均明述结构崩坏),写成可调常量;非门阈值、不影响任何决策,仅分诊标注。
- **fail-closed 纪律**:畸形行/缺特征绝不默认 0 流下去(codex landmine:缺信号默认 0 会教模型「假干净」)——本片在解析层即排除并浮现,为 Slice 2 立规矩。

<!-- codex-peer-reviewed: 2026-06-29T09:33:13Z rounds=2 verdict=approved -->
