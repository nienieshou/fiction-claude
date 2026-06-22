# hiki-fiction-rewrite · 使用说明

> **文档版本 v1.0** ｜ 对应代码 `hiki 0.1.0`（`src/hiki/__init__.py`）
> 架构 spec：Final v5.0（`docs/design/system_design_final.md`）
> 流水线迭代：R12 收官 / R13 待启（`docs/plans/r11_r12_summary.md`）
> 更新日期：2026-06-13

把**任意章数、鱼龙混杂**的中文网文，全自动压缩复写成固定 **60 章 / ~21 万字**的成品。全程零人工干预，救不动的源**允许拒收**。仅用 DeepSeek-v4 系列（pro 推理 / flash 走量），单本约 ¥0.4–5、6–7 分钟。

---

## 1. 环境准备

| 项目 | 要求 |
|---|---|
| Python | 3.10+（已用 3.x venv 验证） |
| 依赖 | `openai`、`httpx`、`python-dotenv`、`PyYAML`（缺 PyYAML 会回退内置默认配置） |
| API | DeepSeek 账号，base_url `https://api.deepseek.com` |
| 平台 | Windows / *nix 均可；Windows 控制台已自动 `reconfigure(utf-8)` 解决 GBK |

安装依赖：

```powershell
# 项目根目录 E:\Project_Python\hiki-fiction-cli\claude
.venv\Scripts\python.exe -m pip install openai httpx python-dotenv pyyaml
```

**配置 API Key** —— 在项目根 `.env` 写入：

```
DEEPSEEK_API_KEY=sk-你的key
```

未设置会直接 `RuntimeError: DEEPSEEK_API_KEY 未设置（检查 .env）`。

---

## 2. 命令总览

所有命令都需要 `src` 在 `PYTHONPATH` 上（代码在 `src/hiki/`）。Windows PowerShell：

```powershell
$env:PYTHONPATH = "src"
```

| 命令 | 用途 | 是否要 API Key | 典型耗时/成本 |
|---|---|---|---|
| `python -m hiki ingest <src>` | P0 清洗单本（切章/去垃圾/去重/编码修复） | 否 | 秒级 / ¥0 |
| **`python -m hiki run <src.txt>`** | **单本复写成品** | 是 | ~6–7min / ¥0.4–5 |
| **`python -m hiki run --tasks-file tasks.yaml`** | **批量复写**（任务驱动+续跑+失败隔离） | 是 | N 本×单本，外层并行 |
| `python -m hiki.pregrade <源...>` | 只深挖+分级，不生产（建源池地图） | 是 | ~¥0.25–1/本 |
| `python -m hiki.point_repair <out_dir>` | 对已生产成品做外科点修 | 是 | ~¥0.1–2/本 |

### `run` —— 复写（单本 / 批量）

```bash
python -m hiki run fictions_source/某本.txt --out output/某本          # 单本
python -m hiki run --tasks-file tasks.yaml --parallel 3 --spine        # 批量
```

`tasks.yaml`（**冒号后必须有空格**）：
```yaml
tasks:
  - slug: novel_a              # 必填:任务标识 + 输出子目录名
    source: fictions_source/小说A.txt
    out: output/novel_new      # 实际落 output/novel_new/novel_a/
  - slug: novel_b
    source: fictions_source/小说B.txt
    out: output/novel_new
    candidates: 1              # 可选 per-task 覆盖:candidates/chapters/min_grade/force...
```

| 选项 | 默认 | 说明 |
|---|---|---|
| `--tasks-file` | — | 批量任务 yaml；省略则跑单本 `src` |
| `--out` | `output/<源名>_full`(单本) | 批量=父目录，落 `<out>/<slug>/` |
| `-n/--candidates` | 3 | 每场景候选数（成本×质量） |
| `--min-grade` | — | 源分级门槛，低于此档拒收（如 `A`） |
| `--parallel` | 3 | 并行本数（账号限流内，≤5） |
| `--spine / --no-spine` | **开（质量默认）** | Fact Spine 事前一致性（承重 +18.8 实证）；`--no-spine` 关闭 |
| `--force` | 关 | 忽略已有阶段产物从头重跑（默认**续跑**：mine/plan/draft 产物在即跳过） |
| `--best-of` | 1 | 拒收即重掷N次取首个可交付。**只重"交付门拒"**(死人复活/章缝/双版本等随机型),源头致命(Q/暗黑/低于min-grade)不重。每次重掷=一次全量¥。实证:随机型重掷必救,系统性源(每稿都造死人复活)救不了——后者待"反造死亡预防"。 |

**续跑(B2)**：崩溃/中断后重跑同一命令，自动跳过已完成阶段（draft 逐章续画）。**失败隔离**：一本崩不拖累其余，traceback 落 `<out>/<slug>/_crash.txt`。汇总 `output/batch_summary.{json,md}`。

---

## 3. 各命令详解

### 3.1 `ingest` —— 清洗（无需 API）

```powershell
$env:PYTHONPATH="src"; python -m hiki ingest fictions_source\某本.txt
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `src` | 必填 | 源 `.txt` 路径 |
| `--out` | `output/<源名>/source` | 输出目录 |

产出 `clean.txt` + `meta.json`（字数/章数）。清洗规则在 `config/pipeline.yaml > ingest`（编码探测、章节正则、垃圾行模式、乱码符、最短章长），可滚动扩充。

### 3.2 `pregrade` —— 源池预分级

先对一批源做深挖+分级（**不生产**），输出题材/质量地图，再按档抽源生产。

```powershell
$env:PYTHONPATH="src"; python -m hiki.pregrade fictions_source --parallel 8
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `sources` | 必填 | 一个目录 或 多个 `.txt` |
| `--parallel` | 8 | 并行本数 |
| `--chunks` | 12 | 全书深挖分窗数 |

产出 `output/pregrade_map.{json,md}`：每本的 **档位 S/A/B/C/D/Q**、主角弧（真实/表面/无）、暗黑比、题材语域、风险、理由。
- 暗黑比 ≥0.4 → **Q 拒收**；≥0.2 → content_flag（最高 D）。
- ⚠ 已知局限：LLM 在源头判“主角弧/人维”几乎无判别力（会脑补），可信功能是**暗黑拒收 + Q/D 过滤 + 题材地图**。

### 3.3 `produce` —— 单本生产

```powershell
$env:PYTHONPATH="src"; python -m hiki.produce fictions_source\某本.txt --min-grade A
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `src` | 必填 | 源 `.txt` |
| `--chapters` | 60 | 目标章数 |
| `--chunks` | 12 | 全书深挖分窗数 |
| `-n / --candidates` | 3 | 每场景候选数（BoN） |
| `--refine-rounds` | 3 | 精修轮数（实证 2–3 轮即够，多轮震荡；故质量默认 3 而非更高） |
| `--min-grade` | 无 | 源档门槛，低于此档拒收。`A`=只产 S/A 好源 |

**流程**：清洗 → 全书 map-reduce 深挖（厚 bible + 全局场景池打分筛选 + 源分级）→ Q/低于门槛短路拒收 → 两层规划（60 章节拍图 → 并发分章）→ 场景 BoN 起草 → 控字/人名归一/章缝缝合/套话门/暗黑净化/事实表对账 → 确定性承重审计 → **交付门** → 命名出书。

### 3.4 `batch` —— 多本并行

```powershell
$env:PYTHONPATH="src"; python -m hiki.batch fictions_source --parallel 4 --min-grade A
```

参数同 `produce`，额外 `--parallel`（默认 4，**建议 ≤5**——受 DeepSeek 账号上限约束：pro 500 / flash 2500，4 本≈440 pro 安全）。每本 try/except 隔离，单本崩不拖垮整批。产出 `output/batch_summary.{json,md}`（可交付/拒收/失败、成本、墙钟）。

### 3.5 `point_repair` —— 选优点修

对**已生产**的成品目录做外科点修（复活修复 / 章级定向重写 / 复检），比重跑省钱且无重掷方差。

```powershell
$env:PYTHONPATH="src"; python -m hiki.point_repair output\某本_full
```

参数仅 `out_dir`（生产产出目录）。复检通过则交付并清掉旧的 `.不可交付.md`。

---

## 4. 输出产物

每本生产在 `output/<源名>_full/`：

```
output/<源名>_full/
├── source/clean.txt, meta.json   清洗结果
├── bible.json                    厚圣经（主角/中心冲突/语域/弧/agency）
├── macro.json                    60 章节拍骨架
├── plan.json                     逐章/逐场景规划（含时序元数据）
├── fact_table.json               全书事实表（生死/修为对账）
├── final.md                      纯正文成品
├── 《书名》.md                    带书名+卖点的成品（可交付时）
├── 《书名》.不可交付.md            交付门拦截时（绝不流向编辑）
└── report.json                   全量诊断报告
```

`report.json` 关键字段：`deliverable`、`交付门`、`grade`、`final_consistent`、`暗黑比`、`章缝_检出/修复`、`套话门_重写章数`、各类 advisory、`cost_cny`、`seconds`。

---

## 5. 交付门与拒收（核心纪律）

系统**不靠 LLM 打绝对分自证质量**（实证：DeepSeek 自评、甚至 Opus 都 Goodhart 高估 9–17 分）。质量认证 = 确定性硬检 + 机械信号 + 人工 ground truth。

**确定性交付门**（命中即 `deliverable=false`，写 `.不可交付.md`）：
- 阵营串线 ≥1 条
- 过短章 ≥3 章
- 暗黑饱和（暗黑比 >0.25）
- 维14 死人复活 / 残缝 >8 / `final_consistent=false` / 高潮预告跳空

**拒收**（`rejected=true`）：源分级 = Q、或暗黑比 ≥0.4、或低于 `--min-grade` 门槛。

> 设计公理：A4 源是脊柱、提分靠选不靠写；A5 对照评估破 Goodhart；A7 成本自适应、救不动则拒；A8 人是老师不是操作员。详见 `src/hiki/__init__.py` 与架构 spec。

> **生死门和解（R16）**：死人复活门残留按**文本复活 beat 检测**（`prose_continuity.verify_revival_beats`，`LIFE_BEAT`）判——
> 复写**清楚交代了归来机制**（树精重生/借尸还魂/假死被揭穿…读者看得懂为何还活着）= ③忠实复活 → 降 advisory；
> 死后**突兀出场、毫无说明** = ②漏复活/真矛盾 → 进门。beat 检测失败时退回源弧和解（`bible.life_arcs`：`dies_returns`→放）。
> _revalidate 真实正文实证：桑念✅树精重生→放、上官尔蓝✅借尸还魂→放、纳珈✅突兀出场→拦（精确区分 ③/②，**优于维14取交集**——后者会误杀上官尔蓝/桑念这类清晰重生）。
> **生死弧抽取**（喂源弧/项2 用）= 专用轻 prompt **定向细窗 pass**（`extract_life_events_pass`+`roster_str`）：bible 就绪后串行、细分 `n_life≥20`、喂 roster 逐角色核查，治开放抽取漏配角死亡。
> **安全不变量**：beat 检测+源弧都判不出 → 默认仍 gate，绝不误放真矛盾。
> **余下局限/后续**：前向预防（喂 plan/draft 遵从源弧，dies_final 禁写活/dies_returns 要求渲染复活）见 `docs/superpowers/plans/` forward-injection（项2，数据显示当前低杠杆，暂缓）。

---

## 6. 配置文件

| 文件 | 内容 |
|---|---|
| `config/models.yaml` | 模型计价、**阶段→模型路由**（extract/plan→pro，draft→flash，fact_audit→pro 等） |
| `config/pipeline.yaml` | 目标章数/每章字数、单本预算上限 ¥50、ingest 清洗规则、分级阈值 |

改路由/阈值改 YAML 即可，**不写死在代码**（A6 配置驱动）。

---

## 7. 典型工作流

```powershell
$env:PYTHONPATH = "src"

# ① 先给整个源池建地图，挑出好源、剔除 Q/暗黑
python -m hiki.pregrade fictions_source --parallel 8
#   → 看 output/pregrade_map.md，记下 S/A 档源

# ② 批量只产好源
python -m hiki.batch fictions_source --parallel 4 --min-grade A
#   → 看 output/batch_summary.md

# ③ 对距线差几分的成品做点修，而非重跑
python -m hiki.point_repair output\某本_full
```

---

## 8. 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `DEEPSEEK_API_KEY 未设置` | `.env` 缺 key |
| `REDUCE 失败：厚 bible 无效` | pro 思考模式偶发吐空（flaky），**非源质量问题，直接重跑** |
| 控制台中文乱码 | 已自动处理；若仍乱，确认终端 UTF-8 |
| 大量 429 | 降 `--parallel`；并发受账号上限 pro500/flash2500 |
| 成品是 `.不可交付.md` | 交付门拦截，看 `report.json > 交付门`，重跑/点修/或弃源 |
| 找不到 `hiki` 模块 | 未设 `PYTHONPATH=src` |

---

## 9. 现状与边界（诚实标注）

- **可稳定交付**：干净、可复现、无 0 分灾难（场景重复/性别翻转/死人复活已结构化治住）的商业爽文开局，分布 ~67–74（严格评分尺），好源（如星际题材）可达 ~80。
- **天花板**：纯 DeepSeek + prompt/架构工程，craft 上限约 88–90（Opus 估值，人工实评更低）。**80→90 的成长弧/句子美感只能靠微调穿透**（spec §18-K，未启用）。
- **R13 主攻方向**：plan brief 事实清单化、act 边界定向深检、异时空支线优先砍除（见 `docs/plans/r11_r12_summary.md`）。

---

*本说明随代码演进；架构/需求变更请同步 bump 文档版本号。权威架构以 `docs/design/system_design_final.md` 为准。*
