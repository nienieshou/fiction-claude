# B1 拆解方案 — `run()` god-function → 阶段管线

> 2026-06-14 · tech-debt B1/B2。前置:F(测试网)✅、D1/D2/D3(config)✅ 已就位。
> 目标:把 528 行 `produce.run()` 拆成按 ¥成本对齐的纯阶段 + 编排器,落出断点续跑(B2)。

## 1. 现状相位图(实测,行偏移相对 run() 起点 686)

| # | 相位 | ¥占比 | 现状落盘 |
|---|---|---|---|
| 1 | ingest | ~0 | `source/clean.txt` |
| 2 | **mine**(map-reduce bible+场景+源分级) | ¥1-2 | 无!拒收短路写 report |
| 3 | **plan**(macro→分章并发→8 步 plan-repair) | ¥0.3 | `bible/macro/plan.json` |
| 4 | **draft**(造峰+gold+波次循环+settle) | **¥4-5** | 无! |
| 5 | refine(POV/异名/复活/净化/章缝/收尾/裁尾 ~8 passes,原地改 ch_texts) | ¥1-2 | 无! |
| 6 | fact-audit(事实表+复活/修为修复+薄网) | ¥0.5 | `fact_table.json` |
| 7 | plane-check(控制面重演核对) | ¥0.3 | 无 |
| 8 | assemble+gate(拼装+37维+intra+evaluate_ship_gate) | ~0 | 无 |
| 9 | finalize(gen_title+输出+craft+report) | ¥0.1 | `final.md`/`《》.md`/`report.json` |

**病灶**:① 最贵 mine/draft 不落盘 → 晚期崩溃全损(无 resume);② `ch_texts` 被相位 5-7 原地改 ~10 次,跨相位变量遮蔽(`cont`/`ec`/`sys_pv`)已让 3 本崩;③ 门信号散落 200 行 gather。

## 2. 目标架构:6 阶段 + 编排器

```
stage_mine    : src.txt   → MineOut{bible, scenes, grade}        落 bible/scenes/grade.json
stage_plan    : MineOut   → PlanOut{plan, beats, ordered, gold}  落 macro/plan.json
stage_draft   : PlanOut   → DraftOut{ch_texts, settled}          落 draft/ch_NN.md(逐章)+settled.json
stage_refine  : DraftOut  → RefineOut{ch_texts}                  落 refined/ch_NN.md
stage_gate    : RefineOut → GateOut{final, signals, deliverable} 落 fact_table.json
stage_finalize: GateOut   → report                              落 final.md/《》.md/report.json
```

编排器(run() 瘦成 ~30 行):
```python
async def run(src, ..., out_dir, force=False):
    ctx = BookCtx(src, out_dir, cli, target_chars, gate_thr, prod, ...)
    m = await stage_mine(ctx, force);  if m.rejected: return m.report
    p = await stage_plan(ctx, m, force)
    d = await stage_draft(ctx, p, force)
    r = await stage_refine(ctx, d, force)
    g = await stage_gate(ctx, r)
    return await stage_finalize(ctx, g)
```
- `BookCtx` = frozen dataclass → 消灭 8-arg 串参 + 闭包捕获。
- 每 stage 模板:`if artifact.exists() and not force: load() else: compute()+persist()` → B2 resume 自然落出。

## 3. Resume(B2)
- 阶段产物存在即跳过;draft 逐章落盘 → mid-draft 崩溃只重画未完成章。
- `--force` 绕过;原子写(tmp→rename)防半截产物;落盘即契约(downstream 所需全在产物里,如 draft 连 settled.json 一起落)。

## 4. 提取顺序(增量,一步一 commit 一验证,不 big-bang)

| 步 | 提取 | 风险 | 验证 |
|---|---|---|---|
| **B1-1** | `stage_mine`+`stage_plan`(已有 json 落盘,契约最清)+ resume | 低 | characterization 测 + 1 smoke |
| B1-2 | `stage_finalize`(叶子,纯输出) | 低 | report 结构测 |
| B1-3 | `stage_gate`(gather signals → 已纯的 evaluate_ship_gate) | 低-中 | gather_gate_signals 补测 |
| B1-4 | `stage_draft`(波次+settle,逐章落盘) | 中 | smoke + resume 测 |
| B1-5 | `stage_refine`(~8 passes 统一 RepairPass 协议) | 中-高 | 每 pass 独立测 + smoke |
| B1-6 | 删残留 + BookCtx 收口 | 低 | 全套 + 完整 A/B smoke |

每步**机械搬运(同调用同顺序,零逻辑改)**→ 行为按构造保持;pytest 守纯函数;阶段边界补 1-2 新测。

## 5. 风险登记

| 风险 | 缓解 |
|---|---|
| LLM 非确定 → 无法 artifact-diff 证等价 | 只机械搬运(不动调用/顺序);characterization 测 + 人读 1 次 smoke。**诚实:不能证等价,只能构造保持+抽查** |
| `ch_texts` 原地改语义丢失 | 每 pass 显式 `ch_texts = pass(ch_texts, ctx)`,返回值即契约 |
| settled/signals 跨阶段漏传 | 落盘 settled.json + GateSignals dataclass 显式传 |
| resume 读半截产物(崩在落盘中) | 原子写 tmp→rename + 产物末尾 sentinel |
| 提取引入回归且 smoke 没抓到 | 增量分步,每步可单独回滚;B1-5 最险单独 PR |

## 6. 成本
- 工程:6 步小 PR;纯函数验证 0 成本(pytest)。
- ¥smoke:每步收尾 1 本 n=1(~¥7),全程 ~6 次 ≈ ¥40。LLM 管线唯一的真端到端验证。
- 默认 smoke 源=退婚(历史对照多)。

---

*接线前以每步 smoke 不崩 + 输出合理为准;证伪即回退该步。权威架构仍以 `system_design_final.md` 为准。*
