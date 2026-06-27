# scripts/ 索引

本目录是 **实验/校准/工具脚本**,不是产线代码(产线在 `src/hiki/`,Web 在 `web/`)。

**为什么不归档、不重命名:** 这些脚本的路径被 `docs/`(plans / design / evidence)和少量源码注释**按完整路径引用**,作为实验结果的出处与可复现步骤。移动或改名会让那些引用变成死链、抹掉溯源性。整理目录请优先靠本索引,**不要 `git mv`**;确需移动时,必须同步改掉所有引用路径。

脚本均为**手动运行**(`python scripts/xxx.py`,多数需 `PYTHONPATH=src`,部分需 `.env` 里的 `DEEPSEEK_API_KEY`)。CI(`.github/workflows/ci.yml`)只跑 `pytest`,不调用本目录任何脚本。

图例:⚙️ = 仍在用的活工具 · 🔧 = 手动校准(真 API,非 pytest) · 📄 = 一次性历史实验/探针(留作溯源)

---

## ⚙️ 活工具(开发回路中反复使用)

| 脚本 | 作用 | 关联 |
|---|---|---|
| `replay_gate.py` | 把新交付门判据回放到盘上全部 `report.json`,对照已知人工/Fable 分(≥75 全拦/≤68 全放)。**交付门阈值改动后必跑,验证不退化。** | `config/pipeline.yaml`、`docs/plans/2026-06-11-tier3-ab-round.md` |
| `regression_replay.py` | 飞轮②:回归重放硬门——每轮工程落地后跑,确认银行里已能命中的病例(`baseline_hit=true`)不退化。 | 缺陷飞轮 |
| `seed_defect_bank.py` | 飞轮①:`defect_bank.jsonl` 种子——把评审证实的缺陷落到仍存在该缺陷的冻结版本上。 | 缺陷飞轮 |
| `review_to_targets.py` | 飞轮④:评审结构化 findings → `repair_targets.json` + `defect_bank` 追加。 | 缺陷飞轮 |
| `repair_replay.py` | 良品线点修:把交付门「事件重演」章号从 report 的控制面重演核对字段取出,定向重演核对。 | `docs/superpowers/plans/2026-06-26-reenact-precision.md` |

## 🔧 校准脚本(手动跑,真 API,非 pytest)

| 脚本 | 作用 | 关联 |
|---|---|---|
| `reenact_precision_calib.py` | 在标注 holdout 上实跑 `_plane_check` 二段,验收重演裁决精度(2026-06-26)。 | `docs/superpowers/plans/2026-06-26-reenact-precision.md` |
| `m0_advisory_verify.py` | 灰区判读校验:8 个已知案例(4 真矛盾/4 噪声),要求真≥3/4 保留且噪声≥3/4 滤除。 | R11-3 |

---

## 📄 历史实验 / 探针(一次性,留作溯源)

### 事实脊柱 Spine(fact_spine)
| 脚本 | 作用 | 关联 |
|---|---|---|
| `m0_spine_reconcile.py` | M0:事实脊柱归并裁决可行性(2026-06-13)。 | `docs/design/fact_spine.md §7`、`docs/evidence/m0_spine_reconcile.json` |
| `m1_run.py` | M1 Spine 端到端跑(`HIKI_SPINE=1`,指定 out_dir)。 | `docs/design/fact_spine.md` M1 |
| `m1_compare.py` | M1 A/B 漂移对照:Spine 版 vs 非 Spine 版,按类计数。 | `docs/design/fact_spine.md` M1.5 |
| `m15_mine_facts.py` | M1.5②廉价门:只跑 mining,验证 `bible.facts` 是否把设定数值归并成单值。 | `docs/design/fact_spine.md` |
| `m2_spine_batch.py` | M2:线性甜区 5 本 · Spine 全套单跑 n=3(2026-06-14,¥34.87)。 | `docs/evidence/batch_summary_spine_m2.md`、`m2_chengzhong_ab.md` |

### 事件/子情节脊柱 + 对账测量
| 脚本 | 作用 | 关联 |
|---|---|---|
| `event_spine_m0.py` | A-M0:验证「事件/状态账」可行性,抽每个人物的状态时间线。 | `docs/design/event_subplot_spine.md` |
| `m0_fact_recall.py` | 对账环 M0:冷战/灵气两本已知病例测召回(≥70% 接产线)。 | — |
| `m0_facttable_recall.py` | A2′ 事实表对账召回测试(同上 11 条真值,≥50% 入产线 advisory)。 | — |
| `m0_measure.py` | B 路线 M0 事后差分测量(与生成解耦):SEAM_CHECK 章缝数 + POV 离群数。 | `docs/plans/recall_result.md` |
| `m0_seq_draft.py` | B 路线 M0:同 plan 下顺序整本起草 vs 并行分章起草差分。 | — |
| `m0_seq_dup_remeasure.py` | R12 补测:顺序/并行双臂的版本互斥密度(`ADJ_DUP_CHECK`)。 | — |
| `m0_adjdup_recall.py` | R11-0:邻章版本互斥检测器召回测试。 | `docs/plans/r11_round_notes.md` |
| `m0_discriminator.py` | 判别器验证实验(决定 test-time compute 路线生死)。 | `docs/plans/ARCHIVE-2026-06-13.md` |

### 生死弧 lifearc(死人复活拒收线)
| 脚本 | 作用 | 关联 |
|---|---|---|
| `arc_m0_lifedeath.py` | 生死弧抽取原型(事前·源头),验可行性。 | `docs/superpowers/plans/2026-06-18-lifearc-*` |
| `arc_m1_lifedeath.py` | 生死弧抽取 v2(M1):硬化召回,救主角 uncertain→dies_returns。 | 同上 |
| `arc_m2_fullread.py` | 生死弧抽取 v3(M2):全文窗读 + 跨窗实体追踪。 | `docs/superpowers/plans/2026-06-18-lifearc-recall-tuning.md` |
| `arc_integ_probe.py` | 集成探针:真书源上跑 mine 的 MAP+生死弧聚合,核对 v3 真值。 | `docs/superpowers/plans/2026-06-18-lifearc-mine-integration.md` |
| `step0_arc_classify.py` | Step0:给拒收书补抽生死弧,把被门 flag 的角色分三类。 | 同上 |
| `bucketB_split.py` | 桶 B 拆分:对被生死门拦但源弧=无弧的角色做定向源读。 | 同上 |
| `beatcheck_probe.py` | 项1 可行性探针:文本复活 beat 检测能否区分忠实复活 vs 漏复活。 | — |
| `item1_rejudge.py` | 用项1(复活 beat 检测)重判 6 本死人复活拒收书。 | — |

### best-of-K / 量产 / 泛化
| 脚本 | 作用 | 关联 |
|---|---|---|
| `best_of.py` | M3 best-of-K(stable-75 路线核心):同源并行跑 K 次,选 ship_issues 最少的本。 | `docs/plans/FINAL-conclusion.md`、`ARCHIVE-2026-06-13.md` |
| `run_linear5_bestof.py` | 线性甜区 5 本 · best-of-3 量产(2026-06-13)。 | — |
| `gen_validate.py` | 5 本泛化验证:各题材 best-of-3,验陌生题材能否稳定交付 71 零硬伤本。 | `docs/plans/ARCHIVE-2026-06-13.md` |
| `load_bearing_eval.py` | 承重 rubric LLM-judge(B-接线验证):成品全文单 pass `fact_audit=v4-pro/1M`。 | `docs/design/load_bearing_measurement.md §7` |

### 人工评分回流 HFL(human-eval loop)
| 脚本 | 作用 | 关联 |
|---|---|---|
| `hfl_ingest.py` | 人工评分回流:读 `scorecard_*.yaml` + 各 slug 的 `report.json` 入账本。 | `docs/plans/2026-06-16-human-eval5-loop.md` |
| `append_hfl_r7.py` | 一次性:HFL 账本追加第 7 跑 Fable 四维评分(与人工分隔离)。 | — |
| `append_hfl_r8.py` | 一次性:HFL 追加 R8 轮 Fable 四维(4 本,含锚本新旧双版配对)。 | — |
| `append_hfl_r9.py` | 一次性:HFL 追加 R9 轮 Fable 四维(3 本)。 | — |
| `append_hfl_r11.py` | 一次性:HFL 追加 R11 轮 Fable 评分(5 本)。 | — |

### 其它探针
| 脚本 | 作用 | 关联 |
|---|---|---|
| `planonly_location_probe.py` | plan-only 探针:只重跑 plan 阶段,量 location 槽覆盖率/漂移(零起草、零重抽 mine)。 | — |
