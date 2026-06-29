# B1 wave2 — run() 清晰块外提 设计

> 2026-06-29 · 技术债 B1(god-function `produce.run()` 拆解)第二波。接 B1 既有外提(`_fact_audit_repair`/`_plane_check`/`_run_ship_gate`/`_stage_finalize`/`_ending_guard` 等)。基于:`master`。配套:`docs/design/tech-debt.md` B1 行。

## 背景(已核实,master)

`produce.run()`(`produce.py:~1265-1494`,~230 行)是出货主管线。前几波已外提多个相位 helper;`run()` 内仍残留若干干净内联块。本波抽 **4 个边界清晰**的块成具名 helper(纯机械移动,行为保持)。

**关键安全姿态(诚实)**:C7 终审已确认 金标/装配回归网测的是 `run()` 的**邻函数纯函数**(`signal_counts_from_fact_table`/装配),**不**端到端驱动 `run()`(其为 async LLM 路)。故:2 个**纯** helper 加**真单测**;2 个 **async** helper 靠**字符级字节等价移动 + 复核**(C7 验证过的纪律)。无网兜底,等价靠逐字。

## 目标

把 4 个干净内联块外提为具名 helper,`run()` 各调用点收成一行;`run()` ~230→~190 行,可读性/可测性升,**行为逐位保持**。

**风险姿态**:纯重构字节等价;每 helper 体 = 原内联块逐字,locals→参数,原地改的 `ch_texts` 返回(调用点等价),所有 `print` 保留。

## 架构

### ① `_collect_valid_names(p: dict, bible: dict) -> set[str]`(纯,源 `produce.py:1330-1340`)
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
```
调用:`valid_names = _collect_valid_names(p, bible)`。

### ② `_detect_intra_repeats(ch_texts, thr) -> list[tuple[int, float]]`(纯,源 `1391-1403`)
把当前**嵌套**于 run() 的 `_intra_repeat` 提到模块级(逐字,含**保留**未用的 `thr=0.08` 形参),加过滤函数:
```python
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
调用:`intra_rep = _detect_intra_repeats(ch_texts, gate_thr["intra_repeat_thr"])`;其后 `if intra_rep: print(...)` **留在** run()(措辞不变)。

### ③ `_refit_short_chapters(cli, ch_texts, target_chars) -> list[str]`(async,源 `1301-1306`)
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
```
调用:`ch_texts = await _refit_short_chapters(cli, ch_texts, target_chars)`。

### ④ `_fix_pov_outliers(cli, ch_texts, p) -> list[str]`(async,源 `1310-1322`)
```python
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
调用:`ch_texts = await _fix_pov_outliers(cli, ch_texts, p)`。

(④ 用的 `_pov_outliers`/`_first_person_ratio`/`_strip_markers`/`prompts.POV_FIX`、③ 用的 `_fit_chapter`、② 用的 `_re` 均为现有模块级符号,无新 import。)

## 验证

- **纯 helper 单测**(新 `tests/test_run_extractions.py`):
  - `_collect_valid_names`: 主角名 + 别名按 `、`/`/` 拆;角色名/别名收;空/None/非 str 别名跳;去重(set)。
  - `_intra_repeat`: <800 字 → 0.0;两半 12-gram 全重合 → 高比率;无重合 → 0.0。
  - `_detect_intra_repeats`: 仅 `>thr` 的章入列,返 `(idx, ratio)`。
- **async helper 字节等价**:`_refit_short_chapters`/`_fix_pov_outliers` 体与原内联逐字(复核字符级核验,同 C7 纪律);调用点 `ch_texts = await ...` 与原地改语义等价。
- **金标/装配网绿**:虽不端到端覆盖 `run()`,跑以确认无附带破坏(信号向量构建路径不变)。
- 既有 `tests/test_produce_units`/`test_stages` 等绿。
- 全量 `pytest -m 'not api'` 绿,报确切 passed/deselected。
- SDD:逐任务 TDD(纯)/字节移动(async)+ 两段复核 + opus 终审。

## 非目标

- **不抽** `sig` dict(`1429-1434`,~11 locals)与 `report` dict(`1440-1490`,~40 locals)—— helper 取 40 参比内联更糟(违"清晰单元"),需 dataclass 式重构 = 另波 B1,不混本波。
- 不改任何信号/门/相位顺序/`print` 措辞;不动 `_intra_repeat` 未用 `thr` 形参(逐字保留);不删既有 helper。
- 不加 config/依赖。不碰 `run()` 其余块(ingest/mining/draft/seam/fact-audit 等均已是 helper 或留待)。

## 风险

- **无网兜底**:`run()` 非金标/装配网端到端覆盖 → async 块等价靠逐字移动 + 字符级复核(C7 已证此纪律可靠);纯块另有真单测。
- **`ch_texts` 原地改 vs 返回**:原内联 `ch_texts[i]=t` 原地改列表;helper 同样原地改 + return,调用点 `ch_texts = await helper(...)` 拿回同一(已改)列表 → 等价。下游对 `ch_texts` 的后续使用不变。
- **嵌套→模块级 `_intra_repeat`**:闭包无外部自由变量(只用入参 `t` + 模块 `_re`)→ 提级零语义变。`thr` 形参原就未用(比较在外),逐字保留避免无谓 diff。
- **块移动顺序**:四块在 run() 内位置不变(原地替换为调用),相位先后逐位保持。
