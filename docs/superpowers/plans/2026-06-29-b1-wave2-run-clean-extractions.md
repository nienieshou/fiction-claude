# B1 wave2 — run() 清晰块外提 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `produce.run()` 内 4 个边界清晰的内联块外提为具名 helper(2 纯 + 2 async),`run()` 各调用点收成一行,行为逐位保持。

**Architecture:** 纯机械外提:每 helper 体 = 原内联块逐字,locals→参数,原地改的 `ch_texts` 返回(调用点 `ch_texts = await helper(...)` 等价)。所有 `print` 保留。T1 两纯 helper 加真单测;T2 两 async helper 字节移动靠字符级复核(`run()` 非金标/装配网端到端覆盖,同 C7 姿态)。

**Tech Stack:** Python ≥3.10,标准库 + pytest。无新第三方依赖。所用符号(`_pov_outliers`/`_first_person_ratio`/`_strip_markers`/`prompts.POV_FIX`/`_fit_chapter`/`_re`)均现有模块级。

**设计依据:** `docs/superpowers/specs/2026-06-29-b1-wave2-run-clean-extractions-design.md`(读它拿四块全文 + 排除 sig/report 的理由 + 无网兜底姿态)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。** 编码 UTF-8。
- **字节等价**:每 helper 体逐字搬原内联块;`ch_texts` 原地改 + 返回;`print` 措辞与位置语义不变;不动 `_intra_repeat` 未用的 `thr=0.08` 形参(逐字保留)。
- **定位靠锚点内容**(非裸行号:T1 加模块级 def 会下移 run() 行号)。用 Edit 精确字符串匹配。
- **不抽** `sig` dict / `report` dict(40 参比内联糟,另波)。不改信号/门/相位顺序/`print` 措辞。不删既有 helper。不加 config/依赖。
- `run()` 非金标/装配网端到端覆盖 → T2 async 块等价靠逐字移动 + 字符级复核;T1 纯块另有真单测。
- 金标/装配网 + 全量 `pytest -m 'not api'` 跑以确认无附带破坏。

---

## Task 1: 两纯 helper 外提(`_collect_valid_names` + `_detect_intra_repeats`)+ 单测

**Files:**
- Modify: `src/hiki/produce.py`(模块级加 3 函数:`_collect_valid_names`/`_intra_repeat`(提级)/`_detect_intra_repeats`;`run()` 内 2 调用点替换)
- Create: `tests/test_run_extractions.py`
- Read first: `produce.py` 内 `run()` 的 valid_names 块(锚:`valid_names = set()`)与 intra 块(锚:`def _intra_repeat(t: str, thr: float = 0.08)`)、模块级 helper 群(`_ending_guard`/`_run_ship_gate` 一带,放新 def 处)

**Interfaces:**
- Produces:
  - `produce._collect_valid_names(p: dict, bible: dict) -> set[str]`
  - `produce._intra_repeat(t: str, thr: float = 0.08) -> float`(模块级,原 run() 内嵌套提级)
  - `produce._detect_intra_repeats(ch_texts: list[str], thr: float) -> list[tuple[int, float]]`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_run_extractions.py`:
```python
"""B1 wave2: run() 清晰块外提的纯 helper 单测(零 API)。"""
from hiki import produce


def test_collect_valid_names_splits_dedups_and_filters():
    p = {"name": "张三/张三丰", "aliases": ["老张、小张"]}
    bible = {"characters": [{"name": " 李四 ", "aliases": ["四爷", 123, ""]}]}
    assert produce._collect_valid_names(p, bible) == {"张三", "张三丰", "老张", "小张", "李四", "四爷"}


def test_collect_valid_names_empty_inputs():
    assert produce._collect_valid_names({}, {}) == set()


def test_intra_repeat_short_text_returns_zero():
    assert produce._intra_repeat("甲" * 799) == 0.0          # <800 字短路


def test_intra_repeat_identical_halves_high():
    half = "甲乙丙丁戊己庚辛壬癸" * 50                          # 500 字
    assert produce._intra_repeat(half + half) > 0.5           # 两半同 → 高重合


def test_intra_repeat_distinct_halves_zero():
    a = "甲乙丙丁戊己庚辛壬癸" * 50
    b = "子丑寅卯辰巳午未申酉" * 50
    assert produce._intra_repeat(a + b) == 0.0                # 两半无共 12-gram


def test_detect_intra_repeats_filters_by_threshold():
    half = "甲乙丙丁戊己庚辛壬癸" * 50
    clean = "甲乙丙丁戊己庚辛壬癸" * 50 + "子丑寅卯辰巳午未申酉" * 50
    out = produce._detect_intra_repeats([clean, half + half], 0.08)
    assert [i for i, _ in out] == [1]                          # 仅第2章超阈
    assert out[0][1] > 0.08
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_run_extractions.py -q`
Expected: FAIL — `AttributeError: module 'hiki.produce' has no attribute '_collect_valid_names'`。

- [ ] **Step 3: 加 3 个模块级函数(`produce.py`,放 `run()` 前的 helper 群,如 `_run_ship_gate` 之后)**

```python
def _collect_valid_names(p: dict, bible: dict) -> set[str]:
    """收集冻结 canon 名(主角名/别名按 、// 拆 + 各角色名/别名), 供 continuity 归一守卫。"""
    valid_names: set[str] = set()
    for nm in [p.get("name", "")] + (p.get("aliases") or []):
        for part in str(nm).replace("、", "/").split("/"):
            if part.strip():
                valid_names.add(part.strip())
    for c in bible.get("characters", []):
        if c.get("name"):
            valid_names.add(c["name"].strip())
        for a in c.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                valid_names.add(a.strip())
    return valid_names


def _intra_repeat(t: str, thr: float = 0.08) -> float:
    s = _re.sub(r"\s", "", t or "")
    if len(s) < 800:
        return 0.0
    h = len(s) // 2
    g1 = {s[i:i + 12] for i in range(0, h - 12, 3)}
    g2 = {s[i:i + 12] for i in range(h, len(s) - 12, 3)}
    return (len(g1 & g2) / max(1, min(len(g1), len(g2)))) if g1 and g2 else 0.0


def _detect_intra_repeats(ch_texts: list[str], thr: float) -> list[tuple[int, float]]:
    """R14 章内自重复(0-LLM): 每章 12-gram 两半重合 > thr → (章idx, 比率)。"""
    return [(i, r) for i, t in enumerate(ch_texts) if (r := _intra_repeat(t)) > thr]
```

- [ ] **Step 4: `run()` 内替 valid_names 块为调用**

把(锚:以 `valid_names = set()` 起的 11 行):
```python
    valid_names = set()
    for nm in [p.get("name", "")] + (p.get("aliases") or []):
        for part in str(nm).replace("、", "/").split("/"):
            if part.strip():
                valid_names.add(part.strip())
    for c in bible.get("characters", []):
        if c.get("name"):
            valid_names.add(c["name"].strip())
        for a in c.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                valid_names.add(a.strip())
```
替为:
```python
    valid_names = _collect_valid_names(p, bible)
```

- [ ] **Step 5: `run()` 内替 intra 块(删嵌套 def + 换调用)**

把(锚:`def _intra_repeat(t: str, thr: float = 0.08) -> float:` 起到 `intra_rep = [...]` 行,共 9 行):
```python
    def _intra_repeat(t: str, thr: float = 0.08) -> float:
        s = _re.sub(r"\s", "", t or "")
        if len(s) < 800:
            return 0.0
        h = len(s) // 2
        g1 = {s[i:i + 12] for i in range(0, h - 12, 3)}
        g2 = {s[i:i + 12] for i in range(h, len(s) - 12, 3)}
        return (len(g1 & g2) / max(1, min(len(g1), len(g2)))) if g1 and g2 else 0.0
    intra_rep = [(i, r) for i, t in enumerate(ch_texts) if (r := _intra_repeat(t)) > gate_thr["intra_repeat_thr"]]
```
替为(仅留调用;其上 R14 两行注释与其下 `if intra_rep: print(...)` 不动):
```python
    intra_rep = _detect_intra_repeats(ch_texts, gate_thr["intra_repeat_thr"])
```

- [ ] **Step 6: 跑确认通过 + 金标/装配 + 全量**

Run: `python -m pytest tests/test_run_extractions.py -q`
Expected: PASS（6 passed）
Run: `python -m pytest tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全绿。
Run: `python -m pytest -m 'not api' -q`
Expected: 全绿,报确切 passed/deselected。

- [ ] **Step 7: 提交**

```bash
git add src/hiki/produce.py tests/test_run_extractions.py
git commit -m "refactor(B1): 外提 _collect_valid_names/_detect_intra_repeats 纯 helper(字节等价, +单测)"
```

---

## Task 2: 两 async helper 外提(`_refit_short_chapters` + `_fix_pov_outliers`)

**Files:**
- Modify: `src/hiki/produce.py`(模块级加 2 async 函数;`run()` 内 2 调用点替换)
- Modify: `docs/design/tech-debt.md`(B1 行)
- Read first: `produce.py` 内 `run()` 的短章再扩块(锚:`short = [i for i, t in enumerate(ch_texts) if len(t) < target_chars * 0.7]`)与 POV 块(锚:`person, outliers = _pov_outliers(ch_texts)`)、Task 1 已加的模块级 helper 群(放新 async def 同处)

**Interfaces:**
- Produces:
  - `produce._refit_short_chapters(cli: Client, ch_texts: list[str], target_chars: int) -> list[str]`
  - `produce._fix_pov_outliers(cli: Client, ch_texts: list[str], p: dict) -> list[str]`
- Consumes(现有,不改):`_fit_chapter`、`_pov_outliers`、`_first_person_ratio`、`_strip_markers`、`prompts.POV_FIX`。

- [ ] **Step 1: 加 2 个 async 模块级函数(`produce.py`,helper 群)**

```python
async def _refit_short_chapters(cli: Client, ch_texts: list[str], target_chars: int) -> list[str]:
    """扩写 flaky 残留: <0.7×target 的章再 _fit 一次(过短≥3章会被交付门拦)。"""
    short = [i for i, t in enumerate(ch_texts) if len(t) < target_chars * 0.7]
    if short:
        refit = await asyncio.gather(*[_fit_chapter(cli, ch_texts[i], target_chars) for i in short])
        for i, t in zip(short, refit):
            ch_texts[i] = t
        print(f"控字: {len(short)} 章过短二次扩写")
    return ch_texts


async def _fix_pov_outliers(cli: Client, ch_texts: list[str], p: dict) -> list[str]:
    """POV: 把误用人称的离群章统一回全书主人称(治整章第一人称误用)。"""
    person, outliers = _pov_outliers(ch_texts)
    if outliers:
        print(f"POV: 第{person}人称书，{len(outliers)}个离群章定向重写: {outliers}")
        sys_pv, usr_pv = prompts.POV_FIX
        fixed = await asyncio.gather(*[
            cli.complete("draft", sys_pv, usr_pv.format(person=person, name=p.get("name", "他"),
                                                        text=ch_texts[i]),
                         max_tokens=8000, temperature=0.3) for i in outliers])
        for i, t in zip(outliers, fixed):
            t = _strip_markers(t)
            if t and _first_person_ratio(t) < 0.5:
                ch_texts[i] = t
    return ch_texts
```

- [ ] **Step 2: `run()` 内替短章再扩块为调用**

把(锚:`short = [i for i, t in enumerate(ch_texts) if len(t) < target_chars * 0.7]` 起的 6 行):
```python
    short = [i for i, t in enumerate(ch_texts) if len(t) < target_chars * 0.7]   # 扩写flaky残留→再试一次
    if short:                                                            # (过短≥3章会被交付门拦)
        refit = await asyncio.gather(*[_fit_chapter(cli, ch_texts[i], target_chars) for i in short])
        for i, t in zip(short, refit):
            ch_texts[i] = t
        print(f"控字: {len(short)} 章过短二次扩写")
```
替为:
```python
    ch_texts = await _refit_short_chapters(cli, ch_texts, target_chars)
```

- [ ] **Step 3: `run()` 内替 POV 块为调用**

把(锚:`person, outliers = _pov_outliers(ch_texts)` 起到 `ch_texts[i] = t` 收尾,共 13 行,含其上一行注释 `# 4a) POV...` 保留):
```python
    person, outliers = _pov_outliers(ch_texts)
    if outliers:
        print(f"POV: 第{person}人称书，{len(outliers)}个离群章定向重写: {outliers}")
        sys_pv, usr_pv = prompts.POV_FIX
        fixed = await asyncio.gather(*[
            cli.complete("draft", sys_pv, usr_pv.format(person=person, name=p.get("name", "他"),
                                                        text=ch_texts[i]),
                         max_tokens=8000, temperature=0.3) for i in outliers])
        for i, t in zip(outliers, fixed):
            t = _strip_markers(t)
            if t and _first_person_ratio(t) < 0.5:    # 修成功才采用
                ch_texts[i] = t
```
替为:
```python
    ch_texts = await _fix_pov_outliers(cli, ch_texts, p)
```

- [ ] **Step 4: 金标/装配 + 全量(字节等价无附带破坏)**

Run: `python -m pytest tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全绿。
Run: `python -m pytest -m 'not api' -q`
Expected: 全绿(导入/收集无破坏),报确切 passed/deselected。

- [ ] **Step 5: 刷新 `docs/design/tech-debt.md` B1 行**

B1 行备注追加:
```
B1 wave2 已落: run() 再外提 4 干净块 —— 2纯(_collect_valid_names/_detect_intra_repeats, +真单测) + 2async(_refit_short_chapters/_fix_pov_outliers, 字节移动+字符级复核)。run ~230→~190。刻意不抽 sig/report dict(40参比内联糟, 待 dataclass 式另波)。
```

- [ ] **Step 6: 提交**

```bash
git add src/hiki/produce.py docs/design/tech-debt.md
git commit -m "refactor(B1): 外提 _refit_short_chapters/_fix_pov_outliers async helper(字节移动)"
```

---

## Self-Review

- **Spec 覆盖**:① `_collect_valid_names` → T1;② `_detect_intra_repeats`(+`_intra_repeat` 提级)→ T1;③ `_refit_short_chapters` → T2;④ `_fix_pov_outliers` → T2;排除 sig/report → 两 Task 均不碰(Global Constraints);验证(纯 6 测 + 金标/装配 + 全量)→ T1 Step 6 / T2 Step 4。✅
- **占位**:无 TBD;每代码步给完整前后码;测试完整。
- **类型一致**:`_collect_valid_names(p,bible)->set[str]`、`_intra_repeat(t,thr=0.08)->float`、`_detect_intra_repeats(ch_texts,thr)->list[tuple[int,float]]`、`_refit_short_chapters(cli,ch_texts,target_chars)->list[str]`、`_fix_pov_outliers(cli,ch_texts,p)->list[str]` 跨 spec/plan/测一致。
- **字节等价**:每 helper 体与 run() 原内联块逐字(T1 Step 3 vs Step 4/5 删除块、T2 Step 1 vs Step 2/3 删除块对照);`_intra_repeat` 提级体逐字含 `thr=0.08`;`ch_texts` 原地改+返回。
- **任务独立**:T1(纯,有单测)/T2(async,字节移动)各自可被复核独立否决;T1 加 def 在 run 上方→T2 块行号下移, 故 T2 靠锚点定位(非裸行号)。
- **风险**:① 锚点匹配失败(行号漂移)→ 用 Edit 精确字符串(给全前码);② async 块无网兜底 → 字符级复核(T2)+ 全量收集 sanity;③ 提级闭包变量 → `_intra_repeat` 仅用入参 `t` + 模块 `_re`,无外部自由变量, 提级零语义变。
