# A3 wave5 — score_scenes 静默单发硬化(失软+可见)设计

> 2026-06-28 · 技术债 A3(LLM 输出契约校验)第五波。接 wave4(verify_identity 静默失败硬化)。
> 基于:`master`。配套:`docs/design/tech-debt.md` A3 行。

## 背景(已核实,master)

三个生产路 LLM 调用点(`_plan_macro`/`reduce_bible`/`score_scenes`)解析失败行为各异。逐一核验下游:

| 站点 | 位置 | 重试 | 解析失败下游 | 判定 |
|---|---|---|---|---|
| `_plan_macro` | `produce.py:654-674` | 3 | 空 chapters → 调用方 `produce.py:826-829` `len(beats)<0.7*n_ch` **raise RuntimeError** | **已响亮崩** |
| `reduce_bible` | `mining.py:198-213` | 3 | partial bible → `_bible_ok` False → `produce.py:784-786` **raise RuntimeError** | **已响亮崩** |
| `score_scenes` | `mining.py:218-234` | **0** | 静默回退 `importance=="高"?70:40` 启发式, 无 stderr | **真·静默漏** |

**命门(`score_scenes`)**:唯一 **0 重试**——单发 `cli.complete`+`_safe_json or {}`(`mining.py:226-228`)。flaky/截断响应一次失败即静默落 importance 启发式。场景分**承重**:打分选 top-`keep_n` 场景(`mining.py:233`)→ 喂 `_plan_macro`(`produce.py:826`)→ 塑造出货书。单发静默降级 = 场景池次优, 书照出, 无声。

`mining.py` 已 import `sys`(`:11`)与 `complete_validated`(`:15`,来自 `.llm_validate`,wave2 共享 infra:validate→retry→None)。

## 目标

把唯一静默单发 `score_scenes` 换共享重试 infra + 耗尽 stderr 浮现, **保留** importance 启发式回退(失软不崩)。happy 路逐位保持(首试 temp 0.2 同今), flaky 时多试一次再**可见**回退而非静默单发降级。

**风险姿态**:happy 路字节同(首试同一调用/解析/排序);仅新增"首试败→二试→可见回退"。**不动门**(场景分喂选择非交付门)。

## 架构

### 唯一改动:`score_scenes` 换 complete_validated(`mining.py:226-228`)

把现:
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
其后三行(`score_map` / `ranked` / `keep_idx`,`mining.py:229-234`)**逐字不变**——importance 启发式回退(`score_map.get(i, ...)`)原样保留。

**温度/调用逐位等价(happy 首试)**:`complete_validated` `base_t=complete_kw.pop("temperature",0.2)`;传 `temperature=0.2,retries=2` → 首试 temp **0.2**(与原单发同)、二试 temp 0.3(仅首试败时)。`json_mode=True/max_tokens=8000` 同。`_safe_json` 同(infra 内部用同一 `gate._safe_json`)。故 LLM 正常响应(常态)时,score_map/排序/keep_idx 字节同。

**schema 谓词**:`isinstance(r, dict) and isinstance(r.get("scores"), list)` —— 与下游 `r.get("scores", [])` 消费契约对齐。缺 `scores` 键或非 dict → 重试 → 耗尽 None → 可见回退。退化空 `{"scores": []}` 通过 schema(list)→ score_map 空 → 启发式回退(同今, 不视为失败)。

**retries=2 取数**:1→2 试。比兄弟站 `tries=3` 少——因 score_scenes 有合法启发式安全网(非 must-succeed), 多一试已显著降 flaky 静默率, 成本最小。

## 验证

- **焦点测**(新 `tests/test_score_scenes_silent.py`,fake cli):
  - 合法 `{"scores": [{"i":0,"score":90}, ...]}` → LLM 分驱动排序(高分场景入选)、`cli.calls==1`(首试成功)、无 stderr。
  - 两试均不可解析 → `capsys` 见 stderr `场景打分LLM重试耗尽`、`cli.calls==2`、回退 importance 排序(`importance=="高"` 场景排前)。
  - `len(scenes) <= keep_n` 早返(`mining.py:220-221`)→ 无 LLM 调用(保持)。
- **门无关**:score_scenes 输出喂 `_plan_macro` 场景选择,不进 `sig`/交付门;无门信号变动。
- **金标/装配回归网**:这两网重放 `cross_check` 事实语料, **不经** mining/scoring 路 → 不覆盖本改;等价依据为"happy 首试逐位同"论证 + 焦点测(spec 显记, 不靠网)。
- 既有 `tests/test_mining.py`(若有 score_scenes 测)绿。
- 全量 `pytest -m 'not api'` 绿,报确切 passed/deselected。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标

- **不动 `_plan_macro`/`reduce_bible`**:均已响亮崩(RuntimeError);二者手抄"留最完整 partial 跨试兜底"语义与 `complete_validated` 的 None-on-exhaustion 不对应 → 迁移是行为变更非整合, YAGNI 留。
- **不动门**:不加门信号、不 fail-closed(score_scenes 非交付硬拦)。
- **不加 config 旋钮**(YAGNI)。
- 不改 `SCENE_SCORE` prompt、不改 importance 启发式回退表达式、不改 `keep_idx` 原时间序。

## 风险

- **为何失软不崩**:场景评分是**质量**影响非交付硬拦;importance 启发式是合法降级(高重要度优先), 崩掉长/贵的整本运行不值。失软 + 可见 = 既保运行又让人工校准环看见"次优场景池"信号(同 wave4 神, 测量边界备忘)。
- **happy 字节同**:首试同一调用 + 同 `_safe_json` + 同三行排序 → LLM 正常时 keep_idx 逐位同;金标/装配网虽不覆盖此路, 但常态行为不变, 焦点测兜回退/重试两轴。
- **stderr 新行**:可能被捕获 stderr 的测看到;wave4/wave3/wave2 同式浮现先例。
- **retries 成本**:仅首试败才触二试(temp 0.3, max_tokens 8000), 单本运行内边际极小。
