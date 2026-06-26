# 早段重复检测器(early_repeat)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增"早段重复"检测器,识别前 k 章里同一事件被重复叙述/版本互斥初遇(治 CPBGX00031 "第二章重复了"漏洞),填入既有 `signals.early_repeat` 占位位,并让交付门据此拦截。

**Architecture:** 新增一个 LLM-judge 检测器 `early_repeat_audit`,只看前 k 章,判"同一事件是否被叙述两遍/角色对已认识的人重新初次介绍"。检出数 `count` 填进既有冻结信号 `early_repeat`(signals.py 已留占位,不 bump schema)。门侧不新增门类型,而是**用 `early_repeat>0` 把 `开篇代入感` 封顶到 cap(默认30),复用既有 `opening_immersion_min=40` 硬门自然拦截**——最小侵入、复用 editor-eval-2 校准电平、语义自洽("第二章就重复=读者代入必崩")。

**Tech Stack:** Python `asyncio`,DeepSeek(经 `hiki.Client.complete`,bucket `pk_final`),`pytest`。

## Global Constraints

- **系统职责边界 = 方案A**:系统只产**客观信号**,不自动评主观四维(故事性/笔力/人)。本检测器属"承重·结构连续(早段重复)"客观信号。详见 memory `hiki-measurement-boundary`。
- **信号 schema v1 冻结**(`src/hiki/signals.py:10-14`):`early_repeat` 是**既有占位键**(`signals.py:44`),填充它**不 bump** `SIGNAL_SCHEMA_VERSION`;严禁改名/删除任何既有键。
- **门阈值改动须回放验证**(`src/hiki/gate.py:119` 纪律):新阈值 `early_repeat_immersion_cap` 默认 `30`(沿用 editor-eval-2 "代入感30→人承重40 该拦"电平),`config/pipeline.yaml` 的 `ship_gate` 可覆盖。
- **测试纪律**:纯函数测试**零 API**(直接调,assert 边界);LLM 函数用本计划自带的 `FakeClient` mock 控制流;需真实 API 的 golden 用 `@pytest.mark.api` 默认 skip。
- **运行测试**:`.venv\Scripts\python.exe -m pytest -q`(pyproject `pythonpath=["src","."]`,`testpaths=["tests"]`)。
- **模型**:DeepSeek-v4 only;检测器走 `cli.complete("pk_final", ...)` 既有通道,不新增模型。
- 不得破坏既有 `tests/test_gate.py`、`tests/test_signals.py`、`tests/test_produce_units.py`。

## File Structure

- `src/hiki/gate.py` — 修改 `SHIP_GATE_DEFAULTS`(加 `early_repeat_immersion_cap`)与 `evaluate_ship_gate`(early_repeat 封顶逻辑)。纯函数,门策略。
- `src/hiki/prompts.py` — 新增 `EARLY_REPEAT`(sys, usr 模板)。prompt 常量。
- `src/hiki/audit.py` — 新增 `early_repeat_audit(cli, ch_texts, k=3)`。LLM-judge 检测器。
- `src/hiki/produce.py` — 接线:调用检测器 → 填 `sig["早段重复"]` 与 `build_signal_vector(early_repeat=...)` → report 加一行。
- `tests/test_gate.py` — 加门封顶测试。
- `tests/test_audit_early_repeat.py`(新建) — 检测器 mock 测试。
- `tests/regression/test_cpbgx00031_early_repeat.py`(新建) — ch1/ch2 种子回归用例(确定性内核 + API-gated golden)。
- `tests/regression/fixtures/cpbgx00031_ch1_ch2.txt`(新建) — ch1+ch2 真实文本 fixture。

---

### Task 1: 门侧 early_repeat 封顶逻辑

**Files:**
- Modify: `src/hiki/gate.py:124-134`(`SHIP_GATE_DEFAULTS`)、`src/hiki/gate.py:168-171`(`evaluate_ship_gate` 的 opening_immersion 段)
- Test: `tests/test_gate.py`(追加)

**Interfaces:**
- Consumes: `evaluate_ship_gate(sig: dict, thr: dict) -> list[str]`(既有);新读 `sig["早段重复"]`(int,缺省视为0)。
- Produces: 门行为——`sig["早段重复"] > 0` 时,把用于判定的 `开篇代入感` 封顶为 `thr["early_repeat_immersion_cap"]`(默认30),再走既有 `opening_immersion_min` 判定。新阈值键 `early_repeat_immersion_cap`。

- [ ] **Step 1: Write the failing test**

在 `tests/test_gate.py` 末尾追加:

```python
def test_early_repeat_caps_immersion():
    # CPBGX00031: detector 误给 opening_immersion=90,但 ch1/ch2 同一"许安初访"重述。
    # early_repeat>0 → 封顶到 cap(30) → 触发 opening_immersion_min(40)硬门。
    assert gate.evaluate_ship_gate({"开篇代入感": 90}, D) == []                  # 无早段重复→90 安全
    assert len(gate.evaluate_ship_gate({"开篇代入感": 90, "早段重复": 1}, D)) == 1  # 有→封顶30→拦
    assert gate.evaluate_ship_gate({"开篇代入感": 90, "早段重复": 0}, D) == []     # =0 不封顶
    # 封顶值高于 min 时不拦(cap 可配)
    loose = {**D, "early_repeat_immersion_cap": 50}
    assert gate.evaluate_ship_gate({"开篇代入感": 90, "早段重复": 2}, loose) == []  # 封顶50≥40
    # 早段重复但 immersion 缺失/None → 不崩、不拦(保守)
    assert gate.evaluate_ship_gate({"早段重复": 1}, D) == []
    assert gate.evaluate_ship_gate({"开篇代入感": None, "早段重复": 1}, D) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_gate.py::test_early_repeat_caps_immersion -v`
Expected: FAIL —— `assert len(...) == 1` 处实际为 0(封顶逻辑尚未实现,90 不被拦)。

- [ ] **Step 3: 在 SHIP_GATE_DEFAULTS 增加阈值键**

`src/hiki/gate.py`,在 `SHIP_GATE_DEFAULTS` 字典内(`opening_immersion_min` 行之后)加一行:

```python
    "opening_immersion_min": 40,     # 开篇代入感分 < → 拦(读者无法代入的灾难地板)。editor-eval-2(量产盘10本)校准:
    "early_repeat_immersion_cap": 30,  # 早段重复(ch1-k 同事件重述)检出>0 → 代入感封顶此值,复用上面硬门。
}                                    #   买来代入感30→人承重40(最低,"第二章重复了")拦;其余≥65→承重≥50 安全;0=关闭。
```

(注:`early_repeat_immersion_cap` 行插在 `opening_immersion_min` 行与闭合 `}` 之间。)

- [ ] **Step 4: 在 evaluate_ship_gate 加封顶逻辑**

`src/hiki/gate.py`,把 opening_immersion 判定段(原 168-170 行)改为:

```python
    imm = sig.get("开篇代入感")
    if sig.get("早段重复", 0) and isinstance(imm, (int, float)):
        imm = min(imm, t.get("early_repeat_immersion_cap", 30))   # 早段同事件重述=代入崩,封顶
    if isinstance(imm, (int, float)) and t.get("opening_immersion_min", 0) and imm < t["opening_immersion_min"]:
        issues.append(f"开篇代入感{imm}<{t['opening_immersion_min']}(读者无法代入,editor-eval-2:30→人承重40)")
    return issues
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_gate.py -v`
Expected: PASS（含新测试与全部既有门测试，尤其 `test_opening_immersion_floor_gate` 不回归）。

- [ ] **Step 6: Commit**

```bash
git add src/hiki/gate.py tests/test_gate.py
git commit -m "feat(gate): early_repeat>0 caps opening_immersion to trigger floor gate"
```

---

### Task 2: early_repeat 检测器(prompt + audit 函数)

**Files:**
- Modify: `src/hiki/prompts.py`(新增 `EARLY_REPEAT` 常量)
- Modify: `src/hiki/audit.py`(新增 `early_repeat_audit`,放在 `opening_immersion_audit` 之后，约 `audit.py:448`)
- Test: `tests/test_audit_early_repeat.py`(新建)

**Interfaces:**
- Consumes: `cli.complete(bucket: str, sys: str, usr: str, *, json_mode: bool, max_tokens: int, temperature: float) -> str`(返回原始字符串);`gate._safe_json`;`prompts.EARLY_REPEAT`(tuple `(sys, usr_template)`,`usr_template` 含 `{text}` 占位)。
- Produces: `async early_repeat_audit(cli, ch_texts: list[str], k: int = 3) -> dict`,返回 `{"count": int, "pairs": list[str]}`。解析失败/异常/章数<2 → `{"count": 0, "pairs": []}`（保守不误拦）。

- [ ] **Step 1: Write the failing test**

新建 `tests/test_audit_early_repeat.py`:

```python
"""early_repeat 检测器：LLM-judge 控制流（FakeClient mock，零真实 API）。"""
import asyncio
import json
from hiki import audit


class FakeClient:
    """最小桩：complete 返回预置字符串，记录调用。"""
    def __init__(self, reply: str):
        self._reply = reply
        self.calls = 0

    async def complete(self, bucket, sys, usr, *, json_mode=False, max_tokens=0, temperature=0.0):
        self.calls += 1
        return self._reply


def _run(coro):
    return asyncio.run(coro)


def test_detects_repeat_pair():
    cli = FakeClient(json.dumps({"repeat": True, "count": 1,
                                 "pairs": ["第1章vs第2章:许安初遇被重述"]}, ensure_ascii=False))
    r = _run(audit.early_repeat_audit(cli, ["第一章 ...许安来访...", "第二章 ...许安又初次来访..."]))
    assert r["count"] == 1
    assert r["pairs"] == ["第1章vs第2章:许安初遇被重述"]
    assert cli.calls == 1


def test_clean_opening_no_repeat():
    cli = FakeClient(json.dumps({"repeat": False, "count": 0, "pairs": []}))
    r = _run(audit.early_repeat_audit(cli, ["第一章 开局", "第二章 推进", "第三章 冲突"]))
    assert r["count"] == 0 and r["pairs"] == []


def test_count_falls_back_to_pairs_len():
    # 模型给了 pairs 但漏填 count → 用 len(pairs) 兜底
    cli = FakeClient(json.dumps({"repeat": True, "pairs": ["a", "b"]}))
    r = _run(audit.early_repeat_audit(cli, ["c1", "c2"]))
    assert r["count"] == 2


def test_under_two_chapters_skips_llm():
    cli = FakeClient("should-not-be-called")
    r = _run(audit.early_repeat_audit(cli, ["only one chapter"]))
    assert r == {"count": 0, "pairs": []} and cli.calls == 0


def test_garbage_json_is_safe():
    cli = FakeClient("not json at all <<<")
    r = _run(audit.early_repeat_audit(cli, ["c1", "c2"]))
    assert r == {"count": 0, "pairs": []}


def test_complete_raises_is_safe():
    class Boom:
        calls = 0
        async def complete(self, *a, **k):
            raise RuntimeError("api down")
    r = _run(audit.early_repeat_audit(Boom(), ["c1", "c2"]))
    assert r == {"count": 0, "pairs": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audit_early_repeat.py -v`
Expected: FAIL —— `AttributeError: module 'hiki.audit' has no attribute 'early_repeat_audit'`。

- [ ] **Step 3: 新增 prompt 常量**

`src/hiki/prompts.py`,在文件中与其它 `OPENING_*` prompt 相邻处新增:

```python
EARLY_REPEAT = (
    # sys
    "你是中文网文连续性审查员。只判一种长线病:**早段同一事件被重复叙述**——"
    "前几章里,同一桩'初遇/到访/事件'被当成第一次发生写了两遍;或某角色明明已在前章登场互动,"
    "后章却让另一角色对其'初次自我介绍/初次相识'。这会让读者读到第二章就出戏。\n"
    "只看是否'同一事件重演成两版/失忆式重新初遇',不评文笔好坏,不管正常的回忆、伏笔回收、爽点循环。\n"
    "严格输出 JSON:{\"repeat\": true/false, \"count\": 重复对数(整数), "
    "\"pairs\": [\"第X章vs第Y章:一句话说明\"]}。无重复则 repeat=false、count=0、pairs=[]。",
    # usr template
    "下面是一本书的前几章节选,按章给出。判断有无'同一事件被重复叙述/失忆式重新初遇'。\n\n{text}",
)
```

- [ ] **Step 4: 新增 early_repeat_audit 函数**

`src/hiki/audit.py`,在 `opening_immersion_audit` 之后新增:

```python
async def early_repeat_audit(cli, ch_texts: list[str], k: int = 3) -> dict:
    """早段重复检测(填 signals.early_repeat):前 k 章是否同一事件被重述/失忆式重新初遇。
    治 CPBGX00031 "第二章重复了"——开篇代入感审计只看单章给了90,漏过整章重演。
    LLM-judge,返回 {"count": int, "pairs": [...]}。章数<2/解析失败/异常 → count=0(保守不误拦)。"""
    from .gate import _safe_json
    if len(ch_texts) < 2:
        return {"count": 0, "pairs": []}
    head = "\n\n".join(f"【第{i + 1}章】\n{t[:2500]}" for i, t in enumerate(ch_texts[:k]))
    sys_p, usr_t = prompts.EARLY_REPEAT
    try:
        raw = await cli.complete("pk_final", sys_p, usr_t.format(text=head[:9000]),
                                 json_mode=True, max_tokens=600, temperature=0.2)
    except Exception:
        return {"count": 0, "pairs": []}
    r = _safe_json(raw)
    if not isinstance(r, dict):
        return {"count": 0, "pairs": []}
    pairs = [str(p) for p in (r.get("pairs") or [])]
    cnt = r.get("count")
    if not isinstance(cnt, int) or isinstance(cnt, bool):
        cnt = len(pairs)
    return {"count": cnt, "pairs": pairs}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audit_early_repeat.py -v`
Expected: PASS（全 6 条）。

- [ ] **Step 6: Commit**

```bash
git add src/hiki/prompts.py src/hiki/audit.py tests/test_audit_early_repeat.py
git commit -m "feat(audit): early_repeat detector for same-event restatement in opening chapters"
```

---

### Task 3: produce 接线（检测器 → 信号 → 门 → report）

**Files:**
- Modify: `src/hiki/produce.py:1410-1418`（opening 审计与 `sig` 组装处）、`src/hiki/produce.py:1462-1469`（`build_signal_vector` 调用）、`src/hiki/produce.py:1440-1445` 附近（report 加一行）
- Test: 端到端验收交给 Task 4；本任务验收 = 既有 `tests/test_produce_units.py` 全绿 + 静态导入无误。

**Interfaces:**
- Consumes: `audit.early_repeat_audit`（Task 2）、`gate.evaluate_ship_gate` 经 `sig["早段重复"]`（Task 1）、`signals.build_signal_vector(early_repeat=...)`（既有占位 kwarg）。
- Produces: 每本 report 的 `signals.early_repeat` 被真实填充（不再恒为 None）；report 新增 `"早段重复(ch1-k)"` 字段；`sig["早段重复"]` 喂给门。

- [ ] **Step 1: 调用检测器（紧邻 opening 审计）**

`src/hiki/produce.py`,在 `immersion = await audit.opening_immersion_audit(...)`（约1412行）之后加一行:

```python
    immersion = await audit.opening_immersion_audit(cli, final, open_premise)   # 标注穿越/重生
    early_rep = await audit.early_repeat_audit(cli, ch_texts)                    # 早段同事件重述(填 signals.early_repeat)
```

- [ ] **Step 2: 把 early_repeat 喂给门 sig**

在 `sig = {...}` 字典（约1414-1418行）的 `"immersion_score"` 项后追加键:

```python
           "immersion_score": immersion.get("代入感分"),
           "早段重复": early_rep["count"]}
```

并确认 `_run_ship_gate` 内组装门 signal 时透传 `早段重复`（若 `_run_ship_gate` 自建门 sig，需在其内把 `sig["早段重复"]` 映射进去——检查 `produce._run_ship_gate` 实现，确保 `evaluate_ship_gate` 收到 `早段重复` 键）。

- [ ] **Step 3: 填冻结信号位**

`build_signal_vector(...)` 调用（约1462-1469行）追加 kwarg:

```python
        too_short_chapters=len([d for d in det if d.startswith("过短")]),
        final_consistent=final_consistent, intra_repeat_chapters=len(intra_rep),
        early_repeat=early_rep["count"])
```

- [ ] **Step 4: report 加可读字段**

在 report dict 里（紧邻 `"章缝_检出"` 行附近）加一行:

```python
        "早段重复(ch1-k)": early_rep["pairs"] or ["无"],
```

- [ ] **Step 5: Run existing units to verify no regression**

Run: `.venv\Scripts\python.exe -m pytest tests/test_produce_units.py tests/test_signals.py -v`
Expected: PASS（既有全绿；本任务不引入新单测，端到端由 Task 4 覆盖）。

- [ ] **Step 6: Commit**

```bash
git add src/hiki/produce.py
git commit -m "feat(produce): wire early_repeat detector into sig/gate/signals/report"
```

---

### Task 4: CPBGX00031 ch1/ch2 种子回归用例 + config 暴露

**Files:**
- Create: `tests/regression/__init__.py`(空)、`tests/regression/fixtures/cpbgx00031_ch1_ch2.txt`、`tests/regression/test_cpbgx00031_early_repeat.py`
- Modify: `config/pipeline.yaml`(`ship_gate` 下暴露 `early_repeat_immersion_cap`,可选)

**Interfaces:**
- Consumes: `gate.evaluate_ship_gate`(Task 1)、`audit.early_repeat_audit`(Task 2)。
- Produces: 校准集第一个回归用例——固定输入 → 期望系统判定。零 API 内核 + API-gated golden。

- [ ] **Step 1: 落 fixture（ch1+ch2 真实文本）**

从成品取前两章原文写入 fixture（保留章标题）:

```bash
.venv\Scripts\python.exe - <<'PY'
from pathlib import Path
src = Path("output/CPBGX00031我真不是大罗金仙带房穿越修仙世界73W_20260625_full/final.md")
lines = src.read_text(encoding="utf-8").splitlines()
# 第1章起始行0,第3章标题前为止(逐句核验得:第3章在 "# 第3章" 处)
buf, started = [], False
for ln in lines:
    if ln.startswith("# 第1章"):
        started = True
    if ln.startswith("# 第3章"):
        break
    if started:
        buf.append(ln)
out = Path("tests/regression/fixtures/cpbgx00031_ch1_ch2.txt")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(buf), encoding="utf-8")
print("wrote", out, len(buf), "lines")
PY
```

- [ ] **Step 2: Write the regression test（确定性内核 + API-gated golden）**

新建 `tests/regression/test_cpbgx00031_early_repeat.py`:

```python
"""校准集种子用例:CPBGX00031 ch1/ch2 是同一'许安初访'事件的两个版本(逐句通读 2026-06-26 确认)。
内核(零API):early_repeat>0 时 opening_immersion=90 也必须被门拦。
golden(需API):真实检测器对 ch1/ch2 应判 count>=1。"""
import asyncio
from pathlib import Path
import pytest
from hiki import gate, audit

D = gate.SHIP_GATE_DEFAULTS
FIXTURE = Path(__file__).parent / "fixtures" / "cpbgx00031_ch1_ch2.txt"


def test_early_repeat_forces_block_even_with_high_immersion():
    # 系统当时:opening_immersion=90 放行(假高分)。期望:early_repeat 存在 → 必拦。
    sig_bug = {"开篇代入感": 90}                       # 旧行为:漏过
    assert gate.evaluate_ship_gate(sig_bug, D) == []
    sig_fixed = {"开篇代入感": 90, "早段重复": 1}        # 新行为:封顶30→拦
    issues = gate.evaluate_ship_gate(sig_fixed, D)
    assert len(issues) == 1 and "开篇代入感" in issues[0]


def test_deliverable_false_when_early_repeat_present():
    # 端到端语义:有早段重复且无其它问题时,ship_issues 非空 → deliverable=false
    assert gate.evaluate_ship_gate({"开篇代入感": 90, "早段重复": 2}, D) != []


@pytest.mark.api
def test_real_detector_flags_cpbgx_ch1_ch2():
    # 默认 skip(需真实 API)。CI/手动带 -m api 时跑,验证检测器对真实病灶不漏。
    from hiki.client import Client          # 既有客户端入口
    text = FIXTURE.read_text(encoding="utf-8")
    # 以 "# 第2章" 为界切两章
    parts = text.split("# 第2章")
    ch1, ch2 = parts[0], "# 第2章" + parts[1]
    cli = Client()
    r = asyncio.run(audit.early_repeat_audit(cli, [ch1, ch2]))
    assert r["count"] >= 1, f"应检出早段重复,实得 {r}"
```

- [ ] **Step 3: 注册 api marker（避免 PytestUnknownMarkWarning）**

`pyproject.toml` 的 `[tool.pytest.ini_options]` 增加:

```toml
markers = ["api: 需要真实 DeepSeek API(默认不跑;用 -m api 显式选)"]
```

并确认默认运行排除 api 用例（在 `addopts` 现值 `-q` 上不强加；开发者用 `-m "not api"` 或 CI 配置）。若希望默认 skip，可改 `addopts = "-q -m 'not api'"`。

- [ ] **Step 4: Run deterministic kernel**

Run: `.venv\Scripts\python.exe -m pytest tests/regression/test_cpbgx00031_early_repeat.py -v -m "not api"`
Expected: PASS（两条确定性用例；golden 用例 deselected）。

- [ ] **Step 5: （可选）在 config 暴露阈值**

`config/pipeline.yaml` 的 `ship_gate` 段加注释项（值与默认一致，便于量产盘调参）:

```yaml
ship_gate:
  # ... 既有阈值 ...
  early_repeat_immersion_cap: 30   # 早段同事件重述检出>0 → 代入感封顶此值(0=关闭该联动)
```

- [ ] **Step 6: Commit**

```bash
git add tests/regression/ pyproject.toml config/pipeline.yaml
git commit -m "test(regression): CPBGX00031 ch1/ch2 early-repeat seed case + api marker"
```

---

## Self-Review

**1. Spec coverage（对照本计划 Goal）**
- 检测器(Task 2)✓ · 填 `early_repeat` 信号(Task 3)✓ · 门据此拦截(Task 1)✓ · ch1/ch2 种子用例(Task 4)✓。Goal 全覆盖。

**2. Placeholder scan** — 无 "TBD/TODO/类似Task N"；每个 code step 含完整代码；每个 test step 含完整断言。Task 3 Step 2 提示"检查 `_run_ship_gate` 是否透传 `早段重复`"——这是**真实条件分支**(取决于 `_run_ship_gate` 是直接传 `sig` 还是自建门 sig)，执行者须读该函数确认；非占位，是必要的代码核查点。

**3. Type consistency**
- `early_repeat_audit` 返回 `{"count": int, "pairs": list[str]}` — Task 2 定义、Task 3/4 一致消费。
- 门 sig 键 `"早段重复"`(中文) — Task 1 读、Task 3 写、Task 4 测，一致（注意:门内 sig 用中文键，`build_signal_vector` 用英文 kwarg `early_repeat`，二者是两套命名空间，分别在 Task1/3 各自正确使用）。
- 阈值键 `early_repeat_immersion_cap` — Task 1 定义默认、Task 4 config 暴露，一致。
- `signals.early_repeat`(英文) — 既有占位(`signals.py:44` + `test_signals.py:49,57` 已测可填)，Task 3 填充，不破 schema。

---

## 后续 Plan（各为独立子系统，单独成 plan；批次2/3 依赖多本校准）

> 本 plan 只做"早段重复"一个子系统(可独立交付)。其余按 memory `hiki-measurement-boundary` 的纪律排期:

1. **修复回读验证**(T0.1)：`_seam_pass`/`_adj_dup_pass` 修复后**重跑 detect**，`residual` 反映"修完仍断裂"而非"未采用修复"。独立子系统，下一个该做。
2. **抗注水量化**(T1.2)：依赖"逐章标签"先落地；按 rubric_260625 六形态算重复率(带章号区间)。
3. **逐章标签 pipeline**(T1.1)：`情绪极性|功能|爽点|钩子` 四标签，喂抗注水与人评底稿。
4. **生死语义升级**(T0.2)：双死=死亡版本互斥(硬拒)、夺舍(soul-death/body-persist)建模——**改 `verify_revival_beats` 语义，须先有 ≥3 本校准集护栏**。
5. **人称/性别一致性、时间锚/数值一致性检测器**(T3.1/T3.2)：纯盲区，需 ≥3 本校准。
