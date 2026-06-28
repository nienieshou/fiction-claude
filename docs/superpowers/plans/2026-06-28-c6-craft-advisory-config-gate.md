# C6 子项目② — config 门控 craft_audit 白烧 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给唯一的默认白烧 advisory `craft_audit` 加 `config.advisories.craft_audit` 开关,默认开(行为保持),量产精简可置 false 省 ~2500tk/本。

**Architecture:** `config.advisory_on(cfg, name, default=True)` 单源助手读 `cfg["advisories"][name]`;`config/pipeline.yaml` 加 `advisories` 块;`produce._stage_finalize` 加尾参 `craft_advisory: bool = True` 门控 craft try-块;`run()` 传 `config.advisory_on(_cfg, "craft_audit")`。

**Tech Stack:** Python ≥3.10,标准库 + PyYAML(已用),pytest(asyncio.run + monkeypatch + tmp_path)。无新依赖。

**设计依据:** `docs/superpowers/specs/2026-06-28-c6-craft-advisory-config-gate-design.md`(读它拿三扫描器表 + early_repeat/event_state 为何不动 + 调用点行号)。

## Global Constraints

- **Python ≥3.10;无新第三方依赖。**
- **默认行为保持**:`craft_advisory` 默认 `True` → craft 照跑、报告键 `"audit_人+故事性_craft(advisory)"` 逐字同;金标/装配网天然绿(craft 非冻结信号向量成员)。
- **只动 craft_audit**:`early_repeat`(gating-leak:封顶代入感→硬门)与 `event_state`/`HIKI_SPINE`(Spine 特性主开关)**绝不碰**。
- **不改** craft_audit 自身逻辑/报告键名/任何阈值/信号/gating 路径。
- canonical 默认在 `advisory_on` 的 `default` 参;`config.py` `_DEFAULTS` 无需加(无 yaml 时 load 返 `_DEFAULTS`,缺 `advisories` 键→走 `default=True`,语义同)。
- `pytest -m 'not api'` 离线全绿。编码 UTF-8。

---

## Task 1: config.advisory_on 单源助手 + pipeline.yaml advisories 块

**Files:**
- Modify: `src/hiki/config.py`(`load` 之后加 `advisory_on`)
- Modify: `config/pipeline.yaml`(加 `advisories` 块)
- Test: `tests/test_config_advisory.py`
- Read first: `config.py:33-43`(`load` 现状)

**Interfaces:**
- Produces: `config.advisory_on(cfg: dict, name: str, default: bool = True) -> bool`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_config_advisory.py`:
```python
"""C6②: config.advisory_on 单源 advisory 开关助手。"""
from hiki import config


def test_advisory_on_missing_block_returns_default():
    assert config.advisory_on({}, "craft_audit") is True
    assert config.advisory_on({}, "anything", default=False) is False


def test_advisory_on_none_block_returns_default():
    assert config.advisory_on({"advisories": None}, "craft_audit") is True


def test_advisory_on_block_present_key_missing_returns_default():
    assert config.advisory_on({"advisories": {}}, "craft_audit") is True


def test_advisory_on_explicit_value_wins():
    assert config.advisory_on({"advisories": {"craft_audit": False}}, "craft_audit") is False
    assert config.advisory_on({"advisories": {"craft_audit": True}}, "craft_audit", default=False) is True
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_config_advisory.py -q`
Expected: FAIL — `AttributeError: module 'hiki.config' has no attribute 'advisory_on'`

- [ ] **Step 3: 加 `advisory_on`(`config.py`,`load` 函数之后)**

```python


def advisory_on(cfg: dict, name: str, default: bool = True) -> bool:
    """C6②: advisory 扫描器是否启用(config.advisories.<name>, 缺省 default)。
    advisory 开关单一来源, 不影响 gating。"""
    return (cfg.get("advisories") or {}).get(name, default)
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_config_advisory.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: `config/pipeline.yaml` 加 `advisories` 块(文件末尾,顶层)**

在文件末尾追加(顶层缩进,与 `ship_gate:` 同级):
```yaml

advisories:                 # C6②: 白烧 advisory 开关(不影响 gating)
  craft_audit: true         # 门后 craft 人/故事性评审(~2500tk/本, 纯报告); 量产精简可关
```

- [ ] **Step 6: 跑确认 yaml 可载 + 默认解析为 True**

Run: `python -c "from hiki import config; c=config.load('pipeline'); print(config.advisory_on(c,'craft_audit'))"`
Expected: `True`

- [ ] **Step 7: 全量 + 提交**

```bash
python -m pytest -q
git add src/hiki/config.py config/pipeline.yaml tests/test_config_advisory.py
git commit -m "feat(C6②): config.advisory_on 单源 advisory 开关 + pipeline.yaml advisories.craft_audit(默认开)"
```

---

## Task 2: _stage_finalize 门控 craft + run() 接线 + 焦点测 + 文档 + 终验

**Files:**
- Modify: `src/hiki/produce.py`(`_stage_finalize` 签名:1223-1225;craft try-块:1241-1244;`run()` 调用处:1488-1489)
- Test: `tests/test_craft_gate.py`
- Modify: `docs/design/tech-debt.md`(C6 行)
- Read first: `produce.py:1223-1258`(`_stage_finalize` 全体)、`produce.py:1486-1489`(run() 调用处)

**Interfaces:**
- Consumes: `config.advisory_on`(Task 1)。`produce` 已 import `config`、`audit`。

- [ ] **Step 1: 写焦点失败测试**

新建 `tests/test_craft_gate.py`:
```python
"""C6②: _stage_finalize 的 craft_advisory 门控(开→调craft, 关→跳过+占位)。零真实 API。"""
import asyncio
from hiki import produce, audit


def _patch(monkeypatch, craft_tracker):
    async def _fake_title(cli, bible, ending=""):
        return {"title": "T", "tagline": "标语", "alts": []}
    async def _fake_craft(cli, text):
        craft_tracker.append(True)
        return ["craft发现X"]
    monkeypatch.setattr(produce, "gen_title", _fake_title)
    monkeypatch.setattr(audit, "craft_audit", _fake_craft)


def _finalize(out, craft_advisory):
    return asyncio.run(produce._stage_finalize(
        object(), out / "src.txt", out, {"protagonist": {}}, "正文内容",
        True, [], {}, open_premise="", immersion={}, craft_advisory=craft_advisory))


def test_craft_off_skips_and_placeholder(tmp_path, monkeypatch):
    tracker = []
    _patch(monkeypatch, tracker)
    out = tmp_path / "bk"; out.mkdir()
    report = _finalize(out, craft_advisory=False)
    assert tracker == []                                          # craft 未被调用(省 token)
    assert "已关" in report["audit_人+故事性_craft(advisory)"][0]   # 报告占位浮现


def test_craft_on_calls_and_records(tmp_path, monkeypatch):
    tracker = []
    _patch(monkeypatch, tracker)
    out = tmp_path / "bk"; out.mkdir()
    report = _finalize(out, craft_advisory=True)
    assert tracker == [True]                                      # craft 被调用
    assert report["audit_人+故事性_craft(advisory)"] == ["craft发现X"]
```

- [ ] **Step 2: 跑确认失败(现 `_stage_finalize` 无 `craft_advisory` 参)**

Run: `python -m pytest tests/test_craft_gate.py -q`
Expected: FAIL — `TypeError: _stage_finalize() got an unexpected keyword argument 'craft_advisory'`

- [ ] **Step 3: `_stage_finalize` 签名加尾参(`produce.py:1223-1225`)**

把:
```python
async def _stage_finalize(cli: Client, src: Path, out_dir: Path, bible: dict, final: str,
                          deliverable: bool, ship_issues: list, report: dict,
                          open_premise: str = "", immersion: dict | None = None) -> dict:
```
改为:
```python
async def _stage_finalize(cli: Client, src: Path, out_dir: Path, bible: dict, final: str,
                          deliverable: bool, ship_issues: list, report: dict,
                          open_premise: str = "", immersion: dict | None = None,
                          craft_advisory: bool = True) -> dict:
```

- [ ] **Step 4: 门控 craft try-块(`produce.py:1241-1244`)**

把:
```python
    try:                                          # craft 仅 advisory，绝不为它丢成品/报告
        audit_craft = await audit.craft_audit(cli, final[:9000])
    except Exception as e:
        audit_craft = [f"(craft审计跳过:{type(e).__name__})"]
```
改为:
```python
    if craft_advisory:                            # C6②: config.advisories.craft_audit 关→跳过省token
        try:                                      # craft 仅 advisory，绝不为它丢成品/报告
            audit_craft = await audit.craft_audit(cli, final[:9000])
        except Exception as e:
            audit_craft = [f"(craft审计跳过:{type(e).__name__})"]
    else:
        audit_craft = ["(craft advisory 已关:config.advisories.craft_audit)"]
```

- [ ] **Step 5: run() 传入(`produce.py:1488-1489`)**

把:
```python
    return await _stage_finalize(cli, src, out_dir, bible, final, deliverable, ship_issues, report,
                                 open_premise, immersion)         # C: 复用门前算好的 immersion(不重算)
```
改为:
```python
    return await _stage_finalize(cli, src, out_dir, bible, final, deliverable, ship_issues, report,
                                 open_premise, immersion,         # C: 复用门前算好的 immersion(不重算)
                                 craft_advisory=config.advisory_on(_cfg, "craft_audit"))
```

- [ ] **Step 6: 跑焦点测 + happy 网守**

Run: `python -m pytest tests/test_craft_gate.py tests/test_produce_units.py tests/test_stages.py -q`
Expected: 全绿(开关两向 + 既有 produce 行为默认不变)。

- [ ] **Step 7: 金标/装配网(craft 非信号向量,天然不受影响)**

Run: `python -m pytest tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全绿。

- [ ] **Step 8: 刷新 `docs/design/tech-debt.md` C6 行**

`| C6 |` 备注追加:`C6② 已落: craft_audit(唯一默认白烧~2500tk/本)经 config.advisories.craft_audit 门控(默认开行为保持, 量产置false省token), config.advisory_on 单源助手。early_repeat(gating-leak)/event_state(HIKI_SPINE特性) 不动。残: 让门读目录gating(③)`。

- [ ] **Step 9: 全量 + 确认 grep**

Run: `python -m pytest -q`
Expected: 全绿,`1 deselected`。报告确切 passed/deselected 数。
Run: `grep -n "craft_advisory\|advisory_on" src/hiki/produce.py`
Expected: `_stage_finalize` 签名 1 + craft 门控 1 + run() 调用 1(`config.advisory_on`)。

- [ ] **Step 10: 提交**

```bash
git add src/hiki/produce.py tests/test_craft_gate.py docs/design/tech-debt.md
git commit -m "feat(C6②): _stage_finalize craft_advisory 门控 + run() 接 config.advisory_on(默认开行为保持) + tech-debt 刷新"
```

---

## Self-Review

- **Spec 覆盖**:① `advisory_on` → Task 1 Step 3;② yaml advisories 块 → Task 1 Step 5;③ `_stage_finalize` 加参 + 门控 → Task 2 Step 3/4;④ run() 接线 → Task 2 Step 5;⑤ 验证(advisory_on 单测 / 焦点测两向 / 金标网) → Task 1 + Task 2 Step 1/6/7。✅
- **行为保持**:默认 True → craft 照跑;Task 2 Step 6/7 既有 produce 测 + 金标/装配网守。
- **占位**:无 TBD;新代码(advisory_on、yaml 块、签名/门控、run() 接线、两测文件)给完整代码;Step 3/4/5 给精确 before→after。
- **类型一致**:`config.advisory_on(cfg, name, default=True) -> bool`、`_stage_finalize(..., craft_advisory: bool = True)` 跨 spec/plan/测一致;焦点测调用参数顺序与签名一致(`open_premise=""`/`immersion={}`/`craft_advisory=`)。
- **风险**:① early_repeat/event_state 误动 → 非目标显式 + 只改 craft 块;② 加参破调用 → 尾 kwarg 默认 True;③ 默认行为变 → 焦点测 `craft_on` + 既有 produce 测 + 金标网三重守。
