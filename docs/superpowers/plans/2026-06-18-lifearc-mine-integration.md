# 生死弧并入 mine + 和解感知生死门 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 v3 验证过的"全文窗读生死弧抽取"并入 mine 的现有 map-reduce，并据此把 fact_audit 的生死门从"一刀切死后又活=拒"改成"对源书生死弧和解"——源书确有死而复生（桑念）→放行；源书永久死却被复写写活（袁麟）→仍拦。

**Architecture:** mine 已对全书分窗 LLM 通读（`EXTRACT_CHUNK`）。给每窗抽取追加 `life_events`（死亡/复活事件），用确定性聚合器 `collect_life_events` 跨窗串成每角色生死弧，冻进 `bible["life_arcs"]`。fact_audit 的生死门在判 deliverable 前查 `life_arcs`：`dies_returns/fake_death` 的角色降级 advisory，其余维持现行拦截。纯抽取/聚合/判定均为可单测纯函数；prompt 与接线改动用集成探针对 v3 真值（桑念=dies_returns、袁麟=dies_final）校验。

**Tech Stack:** Python 3.11, asyncio, DeepSeek（`hiki.client`），pytest。零新依赖。

**范围说明（Scope）：** 本计划只覆盖 **(A) 抽取 + (C) 和解感知门**——这是能独立产出可交付、可测软件的最小闭环（生死弧落库 + 停止误杀 + 仍逮真 bug）。**(B) 事前预防**（把 `_spine_alive_baseline` 从"默认健在"升级为"遵从源弧"喂 plan/draft）依赖同一份 `life_arcs`，留作**后续单独计划** `2026-XX-lifearc-forward-injection.md`，不在本计划内。

**关键文件：**
- `src/hiki/prompts.py` — `EXTRACT_CHUNK`（MAP 抽取）追加 `life_events` 字段
- `src/hiki/mining.py` — 新增 `collect_life_events`（聚合，sibling of `collect_places`）；`mine_book` 落 `bible["life_arcs"]`
- `src/hiki/audit.py` — 新增 `reconcile_revival`（判定，sibling of `check_places`）
- `src/hiki/produce.py` — `_fact_audit_repair` 接收 `life_arcs`，残留复活拆 gate/advisory；改其调用点
- `tests/test_mining.py` — `collect_life_events` 单测（文件可能需新建）
- `tests/test_audit.py` — `reconcile_revival` 单测（追加）
- `scripts/arc_integ_probe.py` — 集成探针，对 v3 真值校验（新建）

---

### Task 1: MAP 抽取追加 `life_events` 字段

**Files:**
- Modify: `src/hiki/prompts.py`（`EXTRACT_CHUNK`，约 L10-31）

无独立单测（prompt 文本），由 Task 7 集成探针校验真值召回。

- [ ] **Step 1: 在 `EXTRACT_CHUNK` 的 JSON schema 里 `places` 之后追加 `life_events`**

把 `EXTRACT_CHUNK` 末尾的 `"places":[...]` 那一项后面（同级，`}}` 之前）加入新字段，并在说明段补一句抽取纪律：

```python
 "places":["本段出现的**主要地点/城市/机构/势力名**(角色常驻或反复出现的,如'云城''帝景集团''武王府';一次性路过的小地点不列)",],
 "life_events":[{{"who":"人物本名","type":"死亡|复活","quote":"≤30字源文引证"}}]}}
**life_events 只抽确定性事件**:type=死亡 仅限**本人真实死亡**(被杀/确认陨落/身亡,**排除**比喻'吓死/想死'、威胁、担心'没死吧?'、假死存疑、他人之死);type=复活 仅限**本人**复活/重生/转世/还魂/被证实诈死归来后**实际继续活动**(排除仅从睡梦中醒来、他人复活、回忆)。诗化死亡(如'闭上眼,气息消散''长枪结果了性命')算死亡。没有则空数组。
```

> 注意：原 schema 末尾是 `"places":["…"]}}`（紧跟 `**fact_observations 只抽…**` 说明段）。改为在 `places` 项加尾逗号、追加 `life_events` 项后再 `}}`，并把上面的 `**life_events 只抽…**` 说明插在 `**fact_observations 只抽…**` 同一说明区。保持 `.format(chunk=...)` 占位不变。

- [ ] **Step 2: 验证 prompt 仍能 format 且含新字段**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "import hiki.prompts as P; s=P.EXTRACT_CHUNK[1].format(chunk='x'); print('life_events' in s, 'places' in s)"`
Expected: `True True`（无 KeyError/IndexError）

- [ ] **Step 3: Commit**

```bash
git add src/hiki/prompts.py
git commit -m "feat(arc): EXTRACT_CHUNK 追加 life_events 抽取(死亡/复活事件)"
```

---

### Task 2: `collect_life_events` 跨窗聚合生死弧

**Files:**
- Modify: `src/hiki/mining.py`（紧接 `collect_places` 之后，约 L108-117）
- Test: `tests/test_mining.py`（若不存在则新建）

- [ ] **Step 1: 写失败测试**

新建（或追加）`tests/test_mining.py`：

```python
"""mining.py 纯函数:生死弧聚合。零 API。"""
from hiki.mining import collect_life_events


def test_collect_life_events_arc():
    # 窗序=时间序:死@w0 + 复活@w1(后窗) → dies_returns;只死 → dies_final
    cr = [
        {"life_events": [{"who": "桑念", "type": "死亡", "quote": "长剑刺进心口"}]},
        {"life_events": [{"who": "桑念", "type": "复活", "quote": "我又活过来了"}]},
        {"life_events": [{"who": "袁麟", "type": "死亡", "quote": "红缨枪结果了性命"}]},
    ]
    arcs = collect_life_events(cr)
    assert arcs["桑念"]["fate"] == "dies_returns"
    assert arcs["袁麟"]["fate"] == "dies_final"
    assert "心口" in arcs["桑念"]["death_q"]


def test_collect_life_events_ignores_revive_only_and_empty():
    # 只复活无死亡 → 不建弧(噪声);无 life_events → 空
    cr = [{"life_events": [{"who": "甲", "type": "复活", "quote": "x"}]},
          {"scene_cards": []}]
    assert collect_life_events(cr) == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_mining.py -q`
Expected: FAIL — `ImportError: cannot import name 'collect_life_events'`

- [ ] **Step 3: 实现 `collect_life_events`**

在 `src/hiki/mining.py` 的 `collect_places` 函数之后插入：

```python
def collect_life_events(chunk_results: list[dict]) -> dict:
    """跨窗归并人物生死事件 → 生死弧。chunk_results 按窗序(=时间序)排列。
    有死亡且其后(含同窗)有复活 → dies_returns;只死 → dies_final;只复活无死亡 → 不建弧(噪声)。
    供 mine 冻进 bible['life_arcs'],喂和解感知生死门(audit.reconcile_revival)。"""
    ev: dict = {}
    for wi, r in enumerate(chunk_results):
        if not isinstance(r, dict):
            continue
        for e in (r.get("life_events") or []):
            who = (e.get("who") or "").strip()
            t = e.get("type")
            if not who or t not in ("死亡", "复活"):
                continue
            d = ev.setdefault(who, {"deaths": [], "returns": [], "death_q": "", "return_q": ""})
            if t == "死亡":
                d["deaths"].append(wi)
                d["death_q"] = d["death_q"] or (e.get("quote") or "")[:30]
            else:
                d["returns"].append(wi)
                d["return_q"] = d["return_q"] or (e.get("quote") or "")[:30]
    arcs = {}
    for who, d in ev.items():
        if not d["deaths"]:
            continue
        fate = "dies_returns" if (d["returns"] and max(d["returns"]) >= min(d["deaths"])) else "dies_final"
        arcs[who] = {"fate": fate, "death_q": d["death_q"], "return_q": d["return_q"],
                     "deaths": sorted(d["deaths"]), "returns": sorted(d["returns"])}
    return arcs
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_mining.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/hiki/mining.py tests/test_mining.py
git commit -m "feat(arc): collect_life_events 跨窗聚合生死弧"
```

---

### Task 3: `mine_book` 落 `bible["life_arcs"]`

**Files:**
- Modify: `src/hiki/mining.py`（`mine_book`，约 L258-266）

- [ ] **Step 1: 在 `mine_book` 里聚合并写入 bible**

`mine_book` 当前末尾（`bible = await reduce_bible(...)` 之后、`return {...}` 之前）插入：

```python
    bible["life_arcs"] = collect_life_events(results)   # 生死弧冻进 bible,喂和解感知生死门
```

> `results` 即 `map_extract` 的返回（已按窗序）。放在 `bible` 已成型之后、`return` 之前即可。

- [ ] **Step 2: 验证不破坏现有 mine 测试 + import**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "import hiki.mining; print('ok')"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `ok` + 全绿（现有测试数 + Task2 的 2 条）

- [ ] **Step 3: Commit**

```bash
git add src/hiki/mining.py
git commit -m "feat(arc): mine_book 落 bible.life_arcs"
```

---

### Task 4: `reconcile_revival` 和解判定

**Files:**
- Modify: `src/hiki/audit.py`（紧接 `enrich_places` 之后）
- Test: `tests/test_audit.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/test_audit.py` 顶部 import 行追加 `reconcile_revival`，并加测试：

```python
from hiki.audit import (broken_prose, _power_rank, power_order_from_bible,
                        check_places, enrich_places, reconcile_revival)


def test_reconcile_revival():
    la = {"桑念": {"fate": "dies_returns"}, "袁麟": {"fate": "dies_final"},
          "甲": {"fate": "fake_death"}}
    assert reconcile_revival(la, "桑念") == "advisory"   # 源书确有复活 → 放行(门误杀那类)
    assert reconcile_revival(la, "甲") == "advisory"     # 假死归来 → 放行
    assert reconcile_revival(la, "袁麟") == "gate"        # 源书永久死却被写活 → 仍拦(真矛盾)
    assert reconcile_revival(la, "无名") == "gate"        # 无弧 → 保守拦(沿用现行,绝不放过未知)
    assert reconcile_revival({}, "谁") == "gate"          # 无 life_arcs(老书/抽取失败)→ 保守拦
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_audit.py -k reconcile -q`
Expected: FAIL — `ImportError: cannot import name 'reconcile_revival'`

- [ ] **Step 3: 实现 `reconcile_revival`**

在 `src/hiki/audit.py` 的 `enrich_places` 之后插入：

```python
def reconcile_revival(life_arcs: dict, who: str) -> str:
    """和解感知生死门:据源书生死弧判一处"死后又活"该 gate 还是 advisory。
    源书确有死而复生/假死归来(dies_returns/fake_death)→ advisory(复写忠实复活,不进门,误杀那类);
    其余(dies_final/never_dies/无弧/无 life_arcs)→ gate(源永久死却被写活=真矛盾,或未知→保守拦)。"""
    arc = (life_arcs or {}).get(who) or {}
    return "advisory" if arc.get("fate") in ("dies_returns", "fake_death") else "gate"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m pytest tests/test_audit.py -k reconcile -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hiki/audit.py tests/test_audit.py
git commit -m "feat(arc): reconcile_revival 和解判定(dies_returns放/dies_final拦)"
```

---

### Task 5: 生死门按源弧拆 gate/advisory

**Files:**
- Modify: `src/hiki/produce.py`（`_fact_audit_repair` 签名与残留复活处理，约 L1054 / L1075-1080；以及其唯一调用点）

- [ ] **Step 1: 给 `_fact_audit_repair` 加 `life_arcs` 形参**

把签名（约 L1054）：

```python
async def _fact_audit_repair(cli: Client, ch_texts: list[str], out_dir: Path) -> dict:
```

改为：

```python
async def _fact_audit_repair(cli: Client, ch_texts: list[str], out_dir: Path,
                             life_arcs: dict | None = None) -> dict:
```

并在函数体开头（`ft_deaths_verified: list[dict] = []` 之前）加：

```python
    life_arcs = life_arcs or {}
```

- [ ] **Step 2: 残留复活按源弧拆分（gate 才进门，忠实复活降 advisory）**

把现有残留处理块（约 L1075-1080）：

```python
        if ft_deaths_verified:                        # R9b: 拦不如修——verify过的复活直喂修复器
            ch_texts = await prose_continuity.repair_revivals_smart(cli, ch_texts, ft_deaths_verified)
            residual = await prose_continuity.verify_revivals(cli, ch_texts, ft_deaths_verified)
            print(f"事实表生死: {len(ft_deaths_verified)} 处verify确认 → 定向修复 → 残留{len(residual)}")
            ft_deaths_verified = residual
```

改为：

```python
        if ft_deaths_verified:                        # R9b: 拦不如修——verify过的复活直喂修复器
            ch_texts = await prose_continuity.repair_revivals_smart(cli, ch_texts, ft_deaths_verified)
            residual = await prose_continuity.verify_revivals(cli, ch_texts, ft_deaths_verified)
            # 和解感知:源书确有死而复生(dies_returns)→降advisory不进门(治桑念类误杀);源永久死却被写活→仍进门(逮袁麟类真矛盾)
            gate_rev = [r for r in residual if audit.reconcile_revival(life_arcs, r.get("who")) == "gate"]
            adv_rev = [r for r in residual if r not in gate_rev]
            print(f"事实表生死: {len(ft_deaths_verified)}处verify → 修复 → 残留{len(residual)}"
                  f"(进门{len(gate_rev)}/源弧和解降级{len(adv_rev)})")
            if adv_rev:
                fact_adv += [f"{r.get('who')}源书死而复生(dies_returns),复写复活beat或欠铺垫(建议补,非死人复活硬伤)"
                             for r in adv_rev]
            ft_deaths_verified = gate_rev
```

> `audit` 已在 produce.py 顶部 import（现有 `audit.fix_entourage` 等用法可证）。`fact_adv` 在本函数已定义（`fact_adv: list[str] = []`）。

- [ ] **Step 3: 改调用点传入 life_arcs**

Run（先定位唯一调用点）: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "import re;s=open('src/hiki/produce.py',encoding='utf-8').read();import sys;[print(i+1,l) for i,l in enumerate(s.splitlines()) if '_fact_audit_repair(' in l and 'async def' not in l]"`

把那一行（形如 `fa = await _fact_audit_repair(cli, ch_texts, out_dir)`）改为：

```python
    fa = await _fact_audit_repair(cli, ch_texts, out_dir, bible.get("life_arcs"))
```

> 调用点所在函数作用域内有 `bible`（finalize 阶段持有 bible）。若该作用域变量名不是 `bible`，用实际持有厚 bible 的变量；用 grep 确认：`$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "print([l for l in open('src/hiki/produce.py',encoding='utf-8') if 'bible' in l and ('def ' in l or '= ' in l)][:5])"`

- [ ] **Step 4: 回归 + import 检查**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "import hiki.produce; print('ok')"; .venv\Scripts\python.exe -m pytest tests/ -q`
Expected: `ok` + 全绿

- [ ] **Step 5: Commit**

```bash
git add src/hiki/produce.py
git commit -m "feat(arc): 生死门按源弧和解(dies_returns降advisory/dies_final进门)"
```

---

### Task 6: 集成探针——对 v3 真值校验抽取与判定

**Files:**
- Create: `scripts/arc_integ_probe.py`

目的：用现成产物校验"MAP+collect_life_events"在真书上能否复现 v3 真值（桑念=dies_returns、袁麟/卢炳元=dies_final），且 `reconcile_revival` 判定正确。仅跑 mine 的 MAP 抽取（flash，~¥0.3/本），不起草。

- [ ] **Step 1: 写探针**

```python
"""集成探针:在真书源上跑 mine 的 MAP+生死弧聚合,核对 v3 真值。零起草。
真值(独立grep/v3全读坐实):桑念=dies_returns、袁麟/卢炳元=dies_final。"""
import asyncio, glob, json, os, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
os.environ["HIKI_SPINE"] = "1"
from hiki.client import Client
from hiki import mining, audit

CASES = [("output/ZTGGX02751听说我死后成了反派白月光_20260617_full", {"桑念": "dies_returns"}),
         ("output/_rerun_ZYGGX02148", {"袁麟": "dies_final", "卢炳元": "dies_final"})]


async def main():
    cli = Client()
    for book, gt in CASES:
        clean = Path(next(iter(glob.glob(book + "/source/*.txt")))).read_text(encoding="utf-8", errors="ignore")
        chunks = mining.split_chunks(clean, 60, 12) if hasattr(mining, "split_chunks") else None
        # 若无 split_chunks,退回按字均分 12 窗
        if chunks is None:
            L = len(clean); step = L // 12
            chunks = [clean[i*step:(i+1)*step] for i in range(12)]
        results = await mining.map_extract(cli, chunks)
        arcs = mining.collect_life_events(results)
        print(f"\n== {os.path.basename(book)[:20]} | 抽到 {len(arcs)} 条生死弧 ==")
        for who, want in gt.items():
            got = arcs.get(who, {}).get("fate", "(无弧)")
            verdict = audit.reconcile_revival(arcs, who)
            ok = "✅" if got == want else "❌"
            print(f"   {who}: 弧={got} 真值={want} {ok} | 门判定={verdict}")
    print(f"\n¥{cli.cost_cny:.2f} | {cli.calls} calls")

asyncio.run(main())
```

> `split_chunks` 的真实函数名见 `mining.py`（切窗函数，约 L20-37）。执行时先 grep 确认：`$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "import hiki.mining as m;print([n for n in dir(m) if 'chunk' in n.lower() or 'split' in n.lower() or 'window' in n.lower()])"`，把探针里的切窗调用对齐到真实函数（参数同 mine_book 用法）。

- [ ] **Step 2: 跑探针**

Run: `$env:PYTHONPATH="src"; .venv\Scripts\python.exe scripts/arc_integ_probe.py`
Expected（判据）：桑念 `弧=dies_returns ✅ 门判定=advisory`；袁麟/卢炳元 `弧=dies_final ✅ 门判定=gate`。成本 ~¥0.5-1。

- [ ] **Step 3: 若桑念未达 dies_returns（召回不足）**

不改判据糊弄。按 v3 教训：先看是否 MAP 窗太大漏掉复活事件 → 调小窗（提高 `n_chunks`）或在 `EXTRACT_CHUNK` 的 life_events 说明里加强"诗化/转世/树灵化"复活的识别样例，重跑 Step 2。记录召回数，<100% 命中则在交付门保留 advisory 兜底（勿设前向权威）。

- [ ] **Step 4: Commit**

```bash
git add scripts/arc_integ_probe.py
git commit -m "test(arc): 集成探针对 v3 真值校验生死弧抽取+门判定"
```

---

### Task 7: 文档与边界标注

**Files:**
- Modify: `docs/USAGE.md`（§5 交付门与拒收，约 L178-190）

- [ ] **Step 1: 在交付门说明里登记和解感知**

在"维14 死人复活"那条后补一句：

```markdown
> **生死门和解（R16）**：死人复活门现按 `bible.life_arcs`（mine 全文窗读抽的源书生死弧）和解——
> 源书确有死而复生（dies_returns/fake_death）的角色，复写让其"死后又活"**不进门**（降 advisory，治忠实复活误杀）；
> 源书永久死（dies_final）却被复写写活、或无弧/抽取失败的，**仍进门**（保守拦真矛盾）。
> 局限：当前只据源弧 fate 判 gate/advisory，未校验复写是否真渲染了复活 beat（"漏复活情节"类暂随 advisory）；
> 该校验与"事前喂 plan/draft 遵从源弧"留作后续 forward-injection 计划。
```

- [ ] **Step 2: Commit**

```bash
git add docs/USAGE.md
git commit -m "docs(arc): 登记生死门和解感知(R16)与边界"
```

---

## 后续计划（不在本计划内）

- **(B) 事前预防 forward-injection**：把 `_spine_alive_baseline`（produce.py L372）从"主要人物默认健在"升级为"遵从 `life_arcs`"——dies_final 角色禁复写写活、dies_returns 角色要求复写同时渲染死亡+复活 beat、per-scene cast 对 `life_arcs` 核验不让永久死者进场。另起 `2026-XX-lifearc-forward-injection.md`。
- **"漏复活情节"判定**：在 advisory 分支里进一步校验复写 ch_a..ch_b 是否含复活 beat，区分 ②漏复活（应补 beat）与 ③忠实复活（真放行）。
- **扩展其他弧**：阵营弧（治阵营串线门）、修为弧（治数值真矛盾）——同 `collect_life_events` 模式。

## Self-Review

- **Spec 覆盖**：(A) 抽取 = Task 1-3；(C) 和解门 = Task 4-5；校验 = Task 6；文档/边界 = Task 7。(B) 明确划出范围作后续计划。✅
- **占位符扫描**：各步含真实代码/命令/期望输出；切窗函数名与调用点用 grep 现场确认（已给命令），非占位。✅
- **类型一致性**：`life_arcs` 结构 `{who: {fate, death_q, return_q, deaths, returns}}` 在 Task 2 定义，Task 4/5/6 一致引用 `.get("fate")`；`reconcile_revival(life_arcs, who)->str("gate"|"advisory")` 在 Task 4 定义、Task 5/6 一致调用。✅
