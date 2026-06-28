# A3 wave5 — score_scenes 静默单发硬化(失软+可见)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `mining.score_scenes` 唯一的静默单发 LLM 调用换成共享重试 infra `complete_validated`(0→2 试)+ 耗尽 stderr 浮现,保留 importance 启发式回退(失软不崩),happy 首试逐位保持。

**Architecture:** 单函数单处改动:`score_scenes`(`mining.py:226-228`)的单发 `cli.complete`+`_safe_json` 换 `complete_validated(..., schema=<scores是list>, retries=2, temperature=0.2)`;`None`(耗尽)时 stderr 浮现 + `r={}` 落入原 importance 启发式回退;其后 score_map/排序/keep_idx 三行不变。

**Tech Stack:** Python ≥3.10,标准库 + pytest。无新第三方依赖。`mining.py` 已 import `sys`(:11)与 `complete_validated`(:15)。

**设计依据:** `docs/superpowers/specs/2026-06-28-a3-wave5-score-scenes-silent-failure-design.md`(读它拿三站点判定 + happy 字节等价论证 + nets 不覆盖此路的告诫)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** 编码 UTF-8。
- **happy 首试字节等价**:`complete_validated(..., retries=2, temperature=0.2, json_mode=True, max_tokens=8000)` 首试 temp **0.2**(与原单发同)、二试 temp 0.3(仅首试败);LLM 正常响应时 score_map/排序/keep_idx 逐位同。
- **失软不崩 + 可见**:耗尽 → `None` → stderr 浮现 + `r={}` → 原 importance 启发式回退(`score_map.get(i, scenes[i].get("importance")=="高" and 70 or 40)`)**原样保留**。不 raise。
- **不动门**:score_scenes 输出喂 `_plan_macro` 场景选择,不进 `sig`/交付门;无门信号变动。
- **不动 `_plan_macro`/`reduce_bible`**(已响亮崩,语义不映射 `complete_validated` 的 None)。不加 config 旋钮。不改 `SCENE_SCORE` prompt / 启发式回退表达式 / `keep_idx` 原时间序。
- TDD:先写失败测。金标/装配网**不覆盖** mining/scoring 路 → 等价靠 happy 首试逐位同论证 + 焦点测,不靠网。

---

## Task 1: score_scenes 换 complete_validated + 耗尽 stderr 浮现

**Files:**
- Modify: `src/hiki/mining.py`(`score_scenes` `:218-234`,仅改 `:226-228` 两行为 5 行)
- Create: `tests/test_score_scenes_silent.py`
- Read first: `mining.py:218-234`(score_scenes 现状)、`mining.py:11,15`(sys / complete_validated 已 import)、`llm_validate.py:8`(complete_validated 签名)

**Interfaces:**
- Consumes: `llm_validate.complete_validated(cli, stage, sys_p, usr, *, schema, retries=3, **complete_kw) -> dict | None`(现存,不改);`schema` 可为 callable 谓词。
- Produces: `mining.score_scenes(cli, scenes, keep_n) -> list[dict]`(签名不变);LLM 解析耗尽时向 stderr 印 `⚠️ 场景打分LLM重试耗尽,回退importance启发式(场景池可能次优)`,并回退 importance 启发式排序(行为同今但现在可见)。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_score_scenes_silent.py`:
```python
"""A3 wave5: score_scenes 静默单发硬化 —— 唯一 0 重试站点换 complete_validated。
零 API; fake cli 按固定串回应。LLM分驱动选择 vs 耗尽可见回退 importance 启发式。"""
import asyncio
import json
from hiki import mining


class _Cli:
    """每次 complete 返回同一固定串; 记调用次数。"""
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def complete(self, *a, **k):
        self.calls += 1
        return self.reply


def _scenes() -> list[dict]:
    # scene0=高(启发式宠儿), scene1/2=低; LLM 给 scene2 最高分(与启发式分歧)
    return [
        {"summary": "S0", "scene_type": "战斗", "importance": "高"},
        {"summary": "S1", "scene_type": "日常", "importance": "低"},
        {"summary": "S2", "scene_type": "转折", "importance": "低"},
    ]


def test_valid_scores_drive_selection():
    cli = _Cli(json.dumps({"scores": [{"i": 0, "score": 10},
                                      {"i": 1, "score": 20},
                                      {"i": 2, "score": 99}]}))
    out = asyncio.run(mining.score_scenes(cli, _scenes(), 1))
    assert [s["summary"] for s in out] == ["S2"]      # LLM 选最高分 scene2
    assert cli.calls == 1                              # 首试通过即 break


def test_exhaustion_warns_and_falls_back_to_heuristic(capsys):
    cli = _Cli("这不是json <<<")
    out = asyncio.run(mining.score_scenes(cli, _scenes(), 1))
    assert [s["summary"] for s in out] == ["S0"]      # 回退: importance=高 的 scene0
    assert cli.calls == 2                              # retries=2 耗尽
    assert "场景打分LLM重试耗尽" in capsys.readouterr().err


def test_small_pool_short_circuits_no_llm():
    cli = _Cli("should-not-be-called")
    scenes = _scenes()
    out = asyncio.run(mining.score_scenes(cli, scenes, 5))   # keep_n >= len → 早返
    assert out == scenes
    assert cli.calls == 0
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_score_scenes_silent.py -q`
Expected: FAIL — `test_exhaustion_warns_and_falls_back_to_heuristic` 断 `cli.calls == 2`(现单发 → calls==1)及 stderr 缺失失败。(`test_valid_scores_drive_selection` 与 `test_small_pool_...` 可能已过:现单发对合法响应 calls==1、早返 calls==0 恰合。)

- [ ] **Step 3: 改 score_scenes(`mining.py:226-228`)**

把现(`mining.py:226-228`):
```python
    raw = await cli.complete("scene_score", sys_p, usr_t.format(scenes=listed),
                             json_mode=True, max_tokens=8000, temperature=0.2)
    r = gate._safe_json(raw) or {}
```
改为:
```python
    r = await complete_validated(cli, "scene_score", sys_p, usr_t.format(scenes=listed),
                                 schema=lambda r: isinstance(r, dict) and isinstance(r.get("scores"), list),
                                 retries=2, json_mode=True, max_tokens=8000, temperature=0.2)
    if r is None:
        print("⚠️ 场景打分LLM重试耗尽,回退importance启发式(场景池可能次优)", file=sys.stderr)
        r = {}
```
其后三行(`score_map` / `ranked` / `keep_idx`,`mining.py:229-234`)**逐字不动**。

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_score_scenes_silent.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 全量离线套 + 既有 mining 测**

Run: `python -m pytest tests/test_mining.py -q`(若存在)
Expected: 全绿(happy 首试逐位等价)。
Run: `python -m pytest -m 'not api' -q`
Expected: 全绿,报确切 passed/deselected 数。

- [ ] **Step 6: 刷新 `docs/design/tech-debt.md` A3 行**

A3 行备注追加:
```
A3 wave5 已落: score_scenes(唯一 0 重试站点) 换 complete_validated(0→2试) + 耗尽 stderr 浮现, 保留 importance 启发式回退(失软不崩)。happy 首试 temp0.2 字节同; 不动门。核实 _plan_macro/reduce_bible 均已响亮崩(RuntimeError), 不动。
```

- [ ] **Step 7: 提交**

```bash
git add src/hiki/mining.py tests/test_score_scenes_silent.py docs/design/tech-debt.md
git commit -m "feat(A3 wave5): score_scenes 换 complete_validated + 耗尽 stderr 浮现(失软+可见, happy 字节同)"
```

---

## Self-Review

- **Spec 覆盖**:① score_scenes 换 complete_validated + schema + 耗尽 stderr + 保留启发式回退 → Step 3;② happy 首试字节等价(temp 0.2/json_mode/max_tokens) → Global Constraints + Step 3 注释;③ 不动门/不动二兄弟/不加旋钮 → Global Constraints + Step 6 文档;④ 验证三轴(合法分驱动/耗尽可见回退/早返无调用)→ Step 1 三测。✅
- **占位**:无 TBD;Step 3 给完整前后码;测试文件完整。
- **类型一致**:`score_scenes(cli, scenes, keep_n) -> list[dict]` 签名跨 spec/plan/测一致;`complete_validated(..., schema, retries, **kw) -> dict|None` 与 `llm_validate.py:8` 现状一致;schema 谓词与下游 `r.get("scores", [])` 消费契约对齐。
- **温度等价**:Step 3 + Global Constraints 双记 `temperature=0.2,retries=2` → 首试 0.2(同原单发)、二试 0.3(仅败时)。
- **风险**:① stderr 新行被捕获 stderr 测看到 → 是焦点测断言点(预期);② 早返/合法两测 TDD 步可能先过 → Step 2 已注明,关键新行为测(耗尽 calls==2 + stderr)必失;③ nets 不覆盖此路 → 等价靠 happy 字节论证 + 焦点测(spec/plan 显记)。
