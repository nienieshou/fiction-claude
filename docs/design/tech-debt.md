# 技术债登记表（Tech-Debt Register）

> 2026-06-14 · 全系统审计（6 路并行 finder + 验证）。判据=对照本项目自己的 PRD NFR + 8 公理。
> 状态图例：✅ 已修 · ◐ 部分 · ⬜ 待办。配套：`system_design_final.md`(权威架构)、`fact_spine.md`(承重专项)。

审计当时规模信号：`produce.py` 1276 行（`run()` 528 行 god-function）；69 条 R8–R16 打补丁注释；produce.py 596 个数字字面量；`output/` 445M 被 git 跟踪；`assets/` 8 目录缺 7；纯函数测试覆盖 ~18%；无 CI。

---

## A. 可靠性：质量门「失败即放行」◐（最危险——LLM 抽风即静默出货次品）

| | 项 | 状态 | 备注 |
|---|---|---|---|
| A4 | `client.complete` 空响应静默返回 `""` → repair pass 经 `out or text` 假装修好;retry 仅覆盖 RateLimit/APIError(连接/超时闪断 abort 整跑,无 resume→全损) | ✅ | 空响应可重试+jitter+扩 connection/timeout。**根治:大部分 fail-open 由空响应触发** |
| A2 | 裸 `except Exception` 把整个 Tier3 事实对账+Spine薄网吞成「advisory失败」→ 真死人复活/身份矛盾照出货;代码 bug(AttributeError)伪装成 advisory | ✅ | 拆分:解析类→advisory;非预期崩溃→`fact_audit_crashed` 进 ship_issue |
| A1 | 空/截断响应被当「0 问题」(false-clean):`fact_audit`/`extract_facts` 抽取失败=该章无事实=矛盾漏检 | ◐ | 承重路径已修(`n_unaudited`>25%章→进门)。**每-pass 重试耗尽已 stderr 浮现(A3 wave3); 进 ship 信号的 unknown 计数仍待办**(A4 已缓解触发源) |
| A5 | `grade_source` 解析失败默认 B 级 → Q 源拿免费全本 ¥draft | ✅ | 重试+失败即拒(Q/拒收),实测短路 |
| A3 | **LLM 输出零 schema 校验**(违 A1/R2):全走 `_safe_json`→裸 dict→`.get()` 默认;缺字段当合法流下去 | ◐ | **A3.1 已落**: `schemas.validate(raw,required,types)` 谓词 + `src/hiki/llm_validate.complete_validated(...→dict\|None)`(validate→retry→终败None)。2 标杆改 fail-closed: `PROSE_REVIVAL_VERIFY`(畸形→保留存疑复活,治漏检)/`EXTRACT_CHUNK`(畸形→stderr 浮现丢失,非静默 `{}`)。happy-path 逐位保持(金标网守),fail-path mock 测。残: 其余 28 契约分波(Class A 硬回退/B 静默假阴/C 保护偏置)/ `_safe_json` 不搬; wave2: LIFE_EVENTS(_extract_life_one) 经 complete_validated(schemas.parsed 容 dict-or-list) — 失败 retry+stderr 浮现, 治静默丢生死事件, happy 逐位保持; wave3: seam/adj_dup/handshake/ending 四检共享环抽 gate.detect_retry(消4处copy-paste) — 重试耗尽 stderr 浮现"可能漏检"(治静默假阴), happy 逐位保持(门信号零变化); A3 wave4 已落: verify_identity._judge 换 complete_validated 共享重试 + 解析耗尽标 verify_failed(落盘 fact_table.json) + stderr 浮现 + 报告 advisory。门字节保持(耗尽仍 real=False, spine_id_contra 不变); 仅 HIKI_SPINE 开时激活。残: extract_facts 逐章失败 per-chapter 浮现(已被 n_unaudited>25% 聚合门覆盖, 边际低)。 |

## B. 结构：god-function + 无断点续跑 ◐（B1-1 已落,方案见 `b1-run-refactor.md`）

| | 项 | 状态 | 备注 |
|---|---|---|---|
| B1 | `run()` = 528 行 god-function,9 阶段内联,违反自己的 A1「阶段=纯函数」 | ◐ | **B1-1** mine/plan · **B1-2** finalize · **B1-3轻** gate · **B1-4** draft(+resume) · **B1-5** refine inline 块抽函数(`_ending_guard`[那个崩3本的 cont 遮蔽 bug-site,独立scope根除]/`_fact_audit_repair`/`_plane_check`,+4 monkeypatch测+真数据验)。**run() 528→188 行(−64%)**;剩 B1-6 BookCtx 收口(可选,收编残余 8 参) |
| B2 | **无 resume/幂等**(spec 头条「全量断点续跑」是空头支票) | ◐ | mine/plan resume(零API验)+ **draft 逐章 resume**(`draft/ch_NN.md`,full+partial 单测:只重画缺章、智能结算)。`force=True` 绕过。剩 refine resume |
| B3 | 跨阶段变量遮蔽(`cont`/`ec`/`sys_pv` 复用),已实锤让 3 本崩 | B1 拆函数后自然消除(局部死在函数边界) |
| B4 | 8 参函数 + 闭包捕获 10+ 可变量,wave-draft 无法脱离 run() 测 | 引入 frozen DraftContext dataclass |

## C. 检测器 sprawl（打地鼠的根）◐

| | 项 | 状态 | 备注 |
|---|---|---|---|
| C1 | **死人复活在 6 路径/3 数据模型重复检**,门里手写优先级裁权威(注释就是这串 bug 的 changelog) | ◐ | `RevivalLedger`(`char_ledger.py`) 收 P1/P2/P3 死亡/出场事件为单源(`record_death`/`record_appearance` + `revivals`/`post_death_appearances`),3路检测变薄 adapter,行为逐位保持(金标+装配+特征化网证等价)。残(follow-up): 门里手写优先级收口 `resolve_gating`(属 principled 改判)/C2修为/C3身份/C5 name谓词。**终审修复(I1)**: `post_death_appearances` 改引用"出场前最近死亡"(原误取最早死亡),恢复与旧 `dead[who]=i` 覆写语义的逐位等价。**已知可接受偏差(repair-only,零门影响)**: P3 `find_revivals` dedup(首条无复活+次条本可命中)与迁移前略异; commit 4e86e95 message 误述 verify/repair 已改(实际未改,保持dict消费) |
| C2 | 修为单调 = 2 套引擎(audit 序数阶梯 vs prose_facts 数值+5%) | ✅ | `PowerLedger`(`char_ledger.py`)+ 可插拔比较器(序数/数值)收 `check_power_monotonic`/`fix_power_monotonic`/`cross_check`-power 3 adapter,域逻辑(`_power_rank`/`num_of`)adapter 注入(ledger 零 audit/prose 依赖),行为逐位保持(characterization + cross_check_corpus 证等价)。残(follow-up): principled 改判(阈值/判据)/ power-finding 列表序由"首现"→"首退"(内容等价,网不pin) |
| C3 | 身份钉死 3 渲染器并存(id_map + spine_roster + plan-roster),迁移半截 | ⬜ | HIKI_SPINE 转正后删 id_map + ad-hoc roster |
| C4 | 中文数字/章节正则在 4-5 模块复制且已分叉(config 含「卷」,mining 不含) | ✅ | `src/hiki/textnum.py` 单一来源(顺带修 mining/slice 漏卷) |
| C5 | 「who/state 入账」循环 5 处重写,name 长度界不一(2-6/2-8/2-5) | ◐ | 7 站点 `2<=len<=N` 收口 `src/hiki/names.py`(`is_person_name(nm,max_len)`/`is_item_name`),行为逐位保持(各站点传现状界 4/5/6/8 + 反相锚保留)。残(follow-up): **界统一**(人名 2-5 vs 2-6 分叉=provenance 缺口,需校准选 5/6)/ `safe_pairs` 谓词 |
| C6 | ~半数 37 维 + 多扫描器是 advisory/哨兵,算了就扔(白烧 token) | ◐ | 用 DIMENSIONS 单一注册表 gating=True/False 驱动。C6① 已落: DIMENSIONS 加 gating/signals 字段(如实标注 4 gating 维 {2,6,12,14}→门信号) + NON_DIM_GATE_FLOORS 常量 + 一致性守卫测(目录gating集=门实际硬拦, 防漂移)。纯元数据+测试零行为改动。C6② 已落: craft_audit(唯一默认白烧~2500tk/本)经 config.advisories.craft_audit 门控(默认开行为保持, 量产置false省token), config.advisory_on 单源助手。early_repeat(gating-leak)/event_state(HIKI_SPINE特性) 不动。残: slice_validate.py 另有第二个未门控 craft_audit 烧点(独立管道, 后续可同接 advisory_on)/ 让门读目录gating(③) |
| C7 | `point_repair` 重实现 produce 尾门(复活/收尾/连续性),手工同步 | ◐ | C7.1 已落: ENDING_CHECK 检测抽 gate.ending_check, produce._ending_guard + point_repair 两处 call(消手工同步), 行为逐位保持。ending_check 已并入共享 gate.detect_retry(A3 wave3, 四检同环)。残: revival/continuity dedup(缠 produce 尾门 B1) |

## D. 配置驱动缺口（违 NFR-M2）◐

| | 项 | 状态 | 备注 |
|---|---|---|---|
| D1 | **交付门 cutoff 全硬编码**(残缝>8、spine_net≥2、dark>0.25...)——最重要决策零 config | ✅ | `config/pipeline.yaml ship_gate` + `gate.evaluate_ship_gate(signals, thr)` 纯函数;2304 组合证行为等价;`scripts/_test_gate.py` 沉淀(门首次可测,顺带补 F1) |
| D2 | `chars_per_chapter=3500` 硬编码 ~6 处 | ✅ | run() 读 `output.chars_per_chapter`→`target_chars`,全部 6 处替换 |
| D3 | wave 切点 `[8,20,33,46]`、N/caps 内联 | ◐ | `production` 块:scene_per_chapter/peak_divisor/n_peak_bonus/wave_fallback_cuts/wave_min_chapters 入 config(`_wave_bounds` 参数化+测试)。残:max_tokens/temperature 斜坡(D3b,~40 call sites,入 models.yaml routing 更合适) |
| D4 | prompts 全内联(无 `assets/prompts/` 版本化) | ⬜ | **并入 E（assets 支柱）**:非机械搬运,需 version+hash+loader 设计,半做反增 churn |
| D5 | model 路由 typo 静默回落 flash | ✅ | `_model_for` 未知 stage stderr 告警(once);本质修在 E 的 stage-routing 校验 |

## E. 版本化资产 + 学习飞轮未建（A6 支柱整根缺）⬜

| | 项 | 状态 | 备注 |
|---|---|---|---|
| E1 | **8 个 assets/ 目录缺 7**;产出-affecting 资产零 version/hash → prompt 改动不可 pin/回滚/二分归因 | ⬜ | 物化 assets/,资产带 version+content-hash,run 记 asset-set hash |
| E2 | **无金标回归 harness**(「升级对金标回归不退化」不可执行);`assets/gold/` = 2 个 14 行 stub | ◐ | 立真金标库 + 确定性+廉价 LLM 复评,退化即 fail。Tier-A 门决策快照网已建(7 本金标,零 API 进 CI,docs:assets/gold_regression/);残: 装配层网(冻 fact_table 重跑计数,护 C1)+题材洞补本+装配层网(C1 等价基线: signal_counts_from_fact_table + cross_check 语料 + fact_table 入库) |
| E3 | **HFL/偏差校准器 = vaporware**:`hfl.jsonl` 只写不读,无 bias_model 训练/加载;spec 破 Goodhart 的稳定机制不存在 | ⬜ | 建 consumer 拟合 per-维偏差,版本化 + 应用到闸门分 |

> E 与 system-review 的「测量危机」(Opus 承重 ±40)同根:没有可信测量+回归网,承重收益无法守住。

## F. 测试与 CI ✅（Phase 0+1 已建网）

| | 项 | 状态 | 备注 |
|---|---|---|---|
| F1 | 纯函数覆盖 ~18%:`cross_check`(矛盾引擎)、`_cn_to_num`(自带 bug 史)、整个 `ledger`、5 个 spine 渲染器无测试 | ✅ | Phase1:`tests/` 补 characterization——cross_check 四类/`_cn_to_num`·`_num_of`/ledger 5 函数(原 0%)/5 个 spine 渲染器/gate/审计核心,**钉死当前行为供后续重构证等价**。残:full audit 套件/slice_validate |
| F2 | 无 pytest/CI/runner;手跑 assert 脚本无人自动跑 | ✅ | Phase0:`pyproject.toml`(pytest+pythonpath)+`requirements.txt`+`.github/workflows/ci.yml`(push/PR 跑 pytest);旧 `scripts/_test_*.py` 迁入 `tests/`;**44 测 0.47s 全绿** |

## G. 死代码 & 仓库卫生 ✅（本轮已清）

| | 项 | 状态 |
|---|---|---|
| G1 | 死函数 `reconcile_bible`/`repair_chapter`/`_normalize_near_names`/`registry_summary`/`within_cap` + 整个 `metrics.py` + `schemas.ChapterSummary` + 死 prompts(RECONCILE/REPAIR) | ✅ 已删(src −73 净) |
| G2 | `output/` 445M 被跟踪 → 416 中间垃圾文件(`_bok*`/`_gbok*`/`_full_gen`/`_crash_*`/`_disc`/`_m0_seq`/`_pregrade`)移除跟踪 + `.gitignore` 防再入(权威证据全留) | ✅ 987→571 |
| G3 | `batch.py`/`pregrade.py` 孤儿 CLI(245 行) | ◐ `batch.py` **复活为 `hiki run` 引擎**(任务驱动 tasks.yaml + 单本失败隔离 + resume + 汇总,+7 测);`pregrade.py` 仍独立 |
| G4 | 14/28 脚本是做完一次性;docs/plans 16 轮记多已被 ARCHIVE 取代 | ⬜ 故意未动(被 plan 文档引用,移动造成 stale 引用,价值低) |
| G5 | 死配置键 `pk_screen`/`book_gate`;admission 占位块;105M git history bloat | ⬜ 小;history purge 另议 |

---

## 推荐修复序

1. **A 剩余(A3 schema 层 + A1 全 pass)** — 静默放行直接摧毁质量门存在意义。
2. **D1 交付门阈值入 config + `evaluate_ship_gate` 纯函数** — 小、高回报,顺带可测。
3. **F2 立 pytest+CI,F1 给 cross_check/_cn_to_num/ledger 补测** — 之后任何重构才有网。
4. **B1 拆 run()** → 顺带解 B2(resume)、B3、B4。**最大工程,解锁其余一切。**
5. **C 统一 CharacterStateLedger** → 收 C1/C2/C3/C5,打地鼠变一处。
6. **E**（金标回归 + 校准器）— 产品级长投,与测量危机同根。

## 本轮已交付（2026-06-14）

- **G 全清**(死代码 + 416 文件仓库瘦身)。
- **A 高价值低风险半**(A4 空响应重试根治、A2 崩溃审计进门、A1 承重路径覆盖不足进门、A5 评级失败即拒)。
- **/code-review 10 修**(`_num_of` 万/亿量纲、里程碑不截断、出生误匹配、verify 快照、cap 分类键、世界观体系门、薄网短路、`_pin_block` 收三渲染器、`_MUTABLE` 去重、跨题材里程碑桶)。
- 全程默认管线零行为改动 + 测试通过。
