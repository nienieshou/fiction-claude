# E3 Slice 1b — 人评回流落冻结信号(grade-ingest 升级)设计

> 2026-06-29 · 技术债 E3(校准飞轮)第二片。接 Slice1(只读审计 `src/hiki/calibration.py`,发现 0 可拟合对齐)。codex 跨模型讨论共识 = **A(数据地基)+ guardrails**。基于:`master@defb7dc`。配套:`docs/design/tech-debt.md` E3 行、memory `e3-calibration-direction`。

## 目标与背景(已核实,master)

Slice1 证实:60 行 hfl **无一**携带冻结信号向量(`signals.build_signal_vector`,`schema_version=1`)→ 0 条可拟合 (信号↔人评) 对齐 → Slice2 影子模型无数据可拟合。本片补这个数据地基:**让今后每条人评行内联携带该书的冻结 `report["signals"]`**,使其 `signal_compat=="frozen"`、直接可拟合(信号内联 → 无需 Slice1 的脆弱 gold-join)。

**关键现实(改变了本片形状)**:
- 生产管线**已**落冻结向量:`produce.py:1507` 建 `report["signals"]`,`:1261` 写 `output/<book>_full/report.json`。每本已有 schema-v1 向量在盘。
- **已有**程序化回流脚本 `scripts/hfl_ingest.py`:读 `output/<eval_dir>/scorecard_*.yaml`(逐评委 YAML)+ 各 slug `report.json`,算加权总分(`_W=故0.30/笔0.25/人0.25/承0.20`)、捕获 `git rev-parse --short HEAD`、追加 `hfl.jsonl`。**唯一缺陷**:`_auto_signals()` 只写 legacy 子集(`deliverable/交付门/grade`),**不**写冻结 `report["signals"]` —— 这正是 Slice1 测得 0 可拟合的根因。
- `report.json` 无引擎 commit/sha 溯源(hfl `version` 是手填标签或 ingest 期 sha)。

所以本片 = **升级既有 blessed writer**(非建新基建),外加 commit 溯源 + 纯可测助手 + 校验/幂等护栏。

**风险姿态**:`hfl_ingest` 改产出形态(治根);`produce.py` 加 1 个 additive top-level 字段(无门/决策改动);`calibration.py` 加纯构造/校验助手(无 I/O)。门永不消费(程序级影子)。金标/装配网保持绿(它们读 `report["signals"]` 子 dict,不读新 top-level 键)。

## 决策(继承 + 本片锁定)

- ground truth = `网文编辑`,dims = standard4 `{拉力,笔力,人,承重}`。其余 scorer 各独立真值空间(见 [[e3-calibration-direction]])。
- 门生效永久下桌;本片只产可拟合数据 + 溯源,不碰门/不建模/不碰 web。

## 架构

### 1) `produce.py` — 加 `engine_commit`(additive top-level)

run() 组装 report 处(`report["signals"]=...` 一带,写盘 `:1261` 之前)加:
```python
report["engine_commit"] = _engine_commit()   # 本次跑的引擎 commit, 供信号溯源
```
模块级 best-effort 助手(捕获一次即可;失败→`"unknown"`,**绝不**让 report 写盘失败;确保 `produce.py` 顶部已 `import subprocess`,缺则加):
```python
def _engine_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except Exception:
        return "unknown"
```
- 放 **top-level**,**绝不**进 `report["signals"]`(否则破金标/装配网冻结向量等价)。
- 老 report(本改动前产)无此键 → ingest 读 `report.get("engine_commit","unknown")`,如实记 unknown。

### 2) `src/hiki/calibration.py` — 加纯构造/校验助手(无 I/O)

模块 docstring 更新:从"只读审计"→"校准数据 plumbing(读/分类 + 行构造/校验);全纯、无 I/O;文件写入由 CLI 持有"。

新常量 + 纯函数:
```python
# 按 dims schema 的 rubric 权重(单源; slot-1=.30 拉力(editor)/故事性(ops) 同槽不同标签, 非静默映射)
RUBRIC_WEIGHTS = {
    "standard4": {"拉力": 0.30, "笔力": 0.25, "人": 0.25, "承重": 0.20},
    "story4":    {"故事性": 0.30, "笔力": 0.25, "人": 0.25, "承重": 0.20},
}

def rubric_total(dims: dict, schema: str) -> float:
    """按 schema 权重算加权总分(四维须全 present 且数值)。schema∈{standard4,story4}。"""
    w = RUBRIC_WEIGHTS[schema]
    return round(sum(float(dims[d]) * wt for d, wt in w.items()), 2)

def signals_hash(signals: dict) -> str:
    """冻结信号向量的稳定指纹(json canonical, sort_keys)→ 幂等去重键之一。"""
    return hashlib.sha256(json.dumps(signals, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]

def build_hfl_row(*, scorer, slug, dims, comments, report, round_, output_dir,
                  ingested_at, date=None) -> dict:
    """构造一条 schema-正确的 hfl 行:内联冻结 report['signals'] 作 auto_signals(→ signal_compat=frozen),
    顶层带溯源元(engine_commit/output_dir/signals_hash/ingested_at)。纯函数; 校验失败 raise ValueError。
    output_dir 由调用方(CLI)显式传入(即读 report.json 的 slug 目录, str); report 自身不带其目录。
    date=scorecard 原 date 透传(可空); ingested_at=本次回流时间戳(调用方注入, 不在纯函数内取时钟)。
    - dims schema 由 _dims_schema(dims) 判; 对 GROUND_TRUTH(editor) 强制 standard4(story4 → ValueError)。
    - 四维须 present 且 0<=v<=100 数值(非 bool); 否则 ValueError(fail-closed)。
    - report 须含 dict 'signals' 且其有 'schema_version'; 否则 ValueError(不可拟合不准入)。
    - total = rubric_total(dims, schema)(派生, 非手填)。
    """
    ...
```
- `build_hfl_row` 返回的行:`{date(透传,可空), scorer, round, title, source, slug, dims, total, comments, auto_signals=report["signals"], version=report.get("engine_commit","unknown"), engine_commit, output_dir, signals_hash, ingested_at}`。`auto_signals` **逐字** = `report["signals"]`(含 schema_version → Slice1 `_signal_compat` 判 frozen)。
- **幂等键(对 RAW JSON 行,非 HflRow)**:`Slice1 的 load_hfl/HflRow 不保留 round/auto_signals 原 dict → 查重不能走 HflRow`。新增纯函数 `hfl_dup_key(raw: dict) -> tuple` = `(raw.get("scorer"), raw.get("slug"), raw.get("round"), signals_hash(raw.get("auto_signals") or {}))` + `find_duplicate(existing_raw_rows, new_row) -> bool`。CLI 在写前把现有 `hfl.jsonl` **按原始 json dict 逐行读**(非 load_hfl)算 key 集合查重。

### 3) `scripts/hfl_ingest.py` — 升级为 frozen-emit + 校验 + 幂等

- `_auto_signals` 删/改:行的信号载荷改为**整块** `report["signals"]`(经 `build_hfl_row`)。
- 维度/权重:按 `_dims_schema` 选 `RUBRIC_WEIGHTS`;对 `网文编辑` 要求 standard4(拉力…)。保留 story4(ops)路不破(权重表已含),但 ground-truth 校准只认 editor。
- 行构造改调 `calibration.build_hfl_row(...)`(纯,显式传 `output_dir=slug_dir`、`date`、`ingested_at`),脚本只持有 YAML 读 + 文件 append(thin CLI)。
- **幂等**:写前把现有 `hfl.jsonl` **按 raw json dict 逐行读**(非 load_hfl),用 `calibration.hfl_dup_key` 算 key 集合;`(scorer,slug,round,signals_hash)` 已存在则跳过并 stderr 浮现;`--allow-duplicate` 绕过。
- 校验失败行:跳过 + 醒目 stderr(沿用脚本现有 `⚠ 跳过` 风格),**不**静默写半行。
- `--write` 语义不变(默认预览)。`_sha()`/`_total`/`_auto_signals` 收编到 calibration 单源(脚本不再自带权重/总分逻辑)。

### 范围 nuance(刻意保留 / 排除)

- 只把信号载荷换成冻结向量 + 加溯源/校验/幂等;**不**改 scorecard YAML 输入格式、不改 `--round`/`--write` CLI 接口语义、不改 IRR 汇总打印。
- **不**碰 `/api/calibration` fixture、不加 web POST/表单(Slice 1c)。
- **不**建模、**不**让校准分进门。
- 老 `append_hfl_rX.py` 一次性脚本不动(历史产物;今后回流走升级后的 `hfl_ingest`)。

## 验证

- **纯函数单测**(`tests/test_calibration.py` 追加):
  - `rubric_total`:standard4 实例(60/70/60/30 → 56.5,对齐 hfl 行 47)+ story4 实例;缺维/非数值 → 调用方 ValueError(经 build_hfl_row)。
  - `signals_hash`:同 dict 同 hash;键序无关(sort_keys);改一值则变。
  - `build_hfl_row`(显式传 output_dir/date/ingested_at):happy(editor standard4)→ `auto_signals==report["signals"]`、`signal_compat`(经 `load_hfl` 往返)=="frozen"、`total` 派生正确、顶层带 engine_commit/signals_hash/output_dir/date;story4 给 `网文编辑` → ValueError;承重>100 / 非数值 / bool → ValueError;report 无 signals / signals 无 schema_version → ValueError;report 无 engine_commit → version=="unknown"。
  - `hfl_dup_key`(对 raw dict)/`find_duplicate`:同 (scorer,slug,round,signals_hash) 判重;slug 同但 signals_hash 不同(重跑)→ 不判重;raw 行缺 auto_signals → signals_hash 为空 dict 指纹(稳定)。
- **CLI 往返测**(新 `tests/test_hfl_ingest.py`):合成临时 `eval_dir`(1-2 个 `scorecard_*.yaml` + 对应 `<slug>/report.json` 带 signals)→ 跑 ingest(预览 + `--write` 到 tmp hfl)→ 断:写出的行 `load_hfl` 回读 `signal_compat=="frozen"`、total 正确、再次跑同输入触发幂等跳过。**不**写真 `assets/hfl.jsonl`(tmp 路径)。
- **`produce.py` engine_commit**:轻单测(monkeypatch subprocess 失败 → "unknown";成功 → 返回 strip 后 sha);确认 `report["engine_commit"]` 进盘而 `report["signals"]` **不含** engine_commit。
- **金标/装配回归网**:`pytest tests/test_gold_regression.py tests/test_assembly_regression.py` 绿(它们读 `report["signals"]` 子 dict / fact_table 计数,top-level 新键无关)。
- 全量 `pytest -m 'not api'` 绿,报确切 passed/deselected。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标

- **不**碰 `/api/calibration`、web 表单/POST(Slice 1c)。
- **不**建模、**不**让校准分进门(程序级永久影子)。
- **不**改 scorecard YAML 格式 / ingest CLI 接口语义 / IRR 打印。
- **不**回填老 60 行(它们仍 legacy/不可拟合;Slice1 审计如实分类)。
- **不**混池非 editor 真值空间作 ground truth。

## 风险

- **`hfl_ingest` 改产出**:行的 `auto_signals` 从 legacy 子集变整块冻结向量——是有意的治根改动(legacy 子集本就不可拟合)。老 60 行不动;新行 frozen。CLI 默认预览(非 `--write` 不落盘),降低误写风险。
- **`produce.py` 加 subprocess git 调用**:best-effort + timeout + 全 except → "unknown",绝不阻塞/失败 report 写盘;生产路无新硬依赖。
- **金标/装配网等价**:engine_commit 严格 top-level,冻结向量 `report["signals"]` 逐字不变 → 网读的子 dict 不变 → 平凡绿(codex 确认 gold_snapshot/装配网只读 signals 子 dict)。
- **dims 标签双源**(拉力 vs 故事性):权重按 schema 选,dims 键逐字保留入行,非静默映射;`网文编辑` 强制 standard4 拒 story4 → 真值空间不串。
- **幂等**:`(scorer,slug,round,signals_hash)` 四元键避免重跑误判重(slug 单键不足,Slice1 opus 复审已点);默认拒重 + `--allow-duplicate` 显式绕过。

<!-- codex-peer-reviewed: 2026-06-29T11:49:45Z rounds=2 verdict=approved -->
