# Tier 1 设计：全书深挖 + 两层规划

> 目标：把 ~75 天花板的**信息损失部分**回收。源书人工=90，其角色深度/主线骨架/爽点节奏本就存在；
> 旧切片架构只读开头 4 万字、让模型现编剩下的 → 人=63/承重=78/爽点通胀。本层**把全书已有的深度挖出来注入**，不动模型（非微调）。

## 核心原则：前端重建、后端复用
被人工验证过的后端（draft BoN+refine+gold → 双向控字 → 确定性人名归一 → 37维审计）不动。
改的是"喂给后端的料"：薄 bible+5-8场景 → **厚角色档案 + 60-90 全局场景 + 60章骨架**。

## 数据流
```
clean.txt(73万字)
 ①分块  按章 K≈12 窗(每窗~5万字,重叠1章)
 ②MAP   K协程并发 EXTRACT_CHUNK → {场景卡[], 角色观察(主动did/想要wanted/关系/腔调)}
 ③REDUCE 归并: 场景→全局池(去重排序打type) ; 观察→厚bible(档案+中心冲突+升级阶梯)
        ↑深度在此诞生; 别名跨窗归一交给REDUCE的LLM
 显式打分 SCENE_SCORE 全局场景→选 top≈1.4×章数
 源分级  SOURCE_GRADE (看完全本再判 S/A/B/C/D/Q→生产模式; Q/拒收 短路)
 ④PLAN-A(macro·1 pro) 厚bible+全局场景 → 60章节拍图(主线+爽点类型调度+势力弧+伏笔全图)
 ⑤PLAN-B(分章·60协程并发) 节拍[i]+指定场景 → 本章场景计划(现有ledger字段)
 ⑥后端(复用) 逐场景 draft BoN/refine/gold(注前情账本) → 控字 → 归一 → 审计 → 拼60章/21万字
```

## 4 个已定决策（用户拍板 2026-06）
1. **显式场景打分**：`SCENE_SCORE` 给全局场景 0-100，选 top≈1.4×章数进 60 章（可控压缩比），非靠 PLAN 隐式选。
2. **源分级挪到 REDUCE 后**：看完全本厚 bible 再 `SOURCE_GRADE` 定级，比开头拍准；Q/拒收直接短路省成本。
3. **纯 map-reduce**：不加 1M 全本 pass；不够再说。
4. **泛化验证选末世/星际**：CPBXN00276全球陆沉 + ZYGWJ02935大佬她美飒全星际（反差大、无人工基线，压泛化）。

## 治三处天花板的对应
- **人 63** ← 角色观察抽"主动did/想要wanted" + 厚档案 `goal/goal_internal/arc_milestones/agency_examples` 注入起草；"主动"从空洞口号变成"照源里他真干过的事写"。
- **承重 78·长线主矛盾不稳** ← `central_conflict` + PLAN-A macro 骨架保证一条主线贯穿 60 章 + 势力 stance_arc。
- **故事性·爽点通胀** ← `escalation_ladder` + PLAN-A `spotlight_payoff_type` 跨章强制变换、破境摊开；`_variety` 指标量化。

## 落地文件
- `prompts.py`：EXTRACT_CHUNK / REDUCE_BIBLE / SCENE_SCORE / SOURCE_GRADE / PLAN_MACRO / PLAN_CHAPTER。
- `mining.py`：chunk_by_chapters / map_extract / merge_scenes / collect_observations / reduce_bible / score_scenes / grade_source / mine_book。
- `produce.py`：_plan_macro / _plan_one_chapter / run（复用 slice_validate 后端）。
- `config/models.yaml`：新增 chunk_extract/scene_score/plan_chapter→flash；reduce/source_grade/plan_macro→pro。
- 用法：`python -m hiki.produce <源.txt> [--chapters 60] [--chunks 12] [-n 3]`。

## 成本/并发
- 估 ~¥10-12/本（远低于 ¥50 上限）。外层跑批限 3-4 本并行（每本内部已重并发，避撞 DeepSeek 500 pro 限流）。

## 验证口径（A8 人为师）
建完跑末世+星际 → **用户人工复评四维**。LLM 审计/Opus/自读均证不可信（高估,人 +17）。
若 Tier1 把总分推到 80+ → 再上 Tier2 硬门蹭笔力/爽点 → 逼近 83-85；剩 85→95 才动微调（拿人工分当信号）。
