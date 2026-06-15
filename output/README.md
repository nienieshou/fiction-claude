# output/ — 生成产物区（**整目录 gitignore，不入库**）

> 本目录下所有内容都是**可重建产物**（源 + 锁定代码 → 一键重跑），故整目录 `.gitignore`。
> 唯一入库的是本 `README.md`（约定文档）。需要长期留存的**结论性证据**抽成摘要、入库到 `docs/evidence/`。

---

## 1. 命名约定（长期管理的硬规矩）

| 形态 | 路径 | 含义 |
|---|---|---|
| 单本成品 | `output/<源名>_full/` | 一次完整产出：`final.md` / `《书名》.md` / `report.json` / `bible·macro·plan·fact_table` / `draft/ch_NN.md`（resume 用）/ `source/clean.txt` |
| 批次产出 | `output/<批次名>/<slug>/` | `hiki run --tasks-file ...` 的批，每本一子目录；批根有 `batch_summary.{json,md}` |
| 中间/实验 | `output/_<用途>/`、`output/*smoke*/`、`output/*_gen/` | 下划线前缀或带 smoke/gen，随手可删 |
| 评分地图 | `output/pregrade_map.{json,md}` | `hiki pregrade` 的源分级地图（运行时重生成） |

**约定**：要交付/评分的成品放 `<slug>_full` 或 `<批次>/<slug>`；中间物一律下划线前缀，方便批量清。

## 2. 证据怎么留（产物可删，结论不可丢）

产物体量大且可重建 → **不进 git**。但「5 本精读证明承重塌方」这类**结论**要长期可引用：
抽成 markdown/json 摘要，提交到 **`docs/evidence/`**（已入库，设计文档从那里引用）。

- ✅ 入 `docs/evidence/`：批次精读摘要、A/B 对照、归并裁决留痕、pregrade 地图快照。
- ❌ 不入库：21 万字 `final.md`、`draft/`、`bible/macro/plan` 全量 json。

## 3. 清理

中间物随手删（下划线前缀/smoke/gen）。成品目录确认无引用后可 `rm -rf`——git 无记录，**删前确认 `docs/evidence/` 已留摘要**。
