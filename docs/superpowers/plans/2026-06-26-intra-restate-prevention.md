# 章内重述事前规避 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从生成侧消除"改写式章内重述"——让 plan 的 end_hook 不复述本章已交代事件，使 drafter 不再把同一事件正文+结尾各演一遍。

**Architecture:** 两点 prompt/注入纪律修复（end_hook 生成 + 章尾钩注入护栏，mirror 现有 R15 铁律话术）+ 一个 0-LLM 确定性 advisory（end_hook↔key_events 词面重合，兼回归护栏与验证度量）。不建检测器、无 schema、无闸门改动；现有词面 `章内双版本` 硬门保留做安全网。

**Tech Stack:** Python 3 / asyncio / DeepSeek planner / pytest（纯函数 0-LLM 单测）。

设计文档：`docs/superpowers/specs/2026-06-26-intra-restate-prevention-design.md`

## Global Constraints

- 不改现有 `_intra_repeat`（produce.py:1410）/ `章内双版本` 硬门；不改 R15 高潮/非高潮 scene 间铁律（produce.py:914-938）。
- `_hook_restate_ratio` 必须是 **produce.py 模块级**函数（test_produce_units.py 通过 `from hiki.produce import ...` 引入测试）。
- 章尾钩 advisory **只打印**（mirror place_drift/R15 plan 阶段打印）——不进报告、不进 `sig`、不进 signals、不进闸门。
- 注入护栏改的是 produce.py:909-913 追加给 `last["brief"]` 的话术；`ch["end_hook"]` 字段本身不被改动（advisory 量的是原始 end_hook）。
- end_hook 生成纪律不得削弱钩子强度（章尾钩纪律本治"钩子弱"；推进性钩子如"逼近威胁"仍是强钩）。
- 已核对：现有测试**无**断言 produce.py:909-913 字符串或 prompts.py end_hook 字段文本（改话术不撞测试）。
- advisory 阈值常量只活在 Task 2 的注入处，不进 `_hook_restate_ratio` 函数体（函数返回原始比值，单测断言比值量级、不绑阈值）。

---

## File Structure

- `src/hiki/produce.py` — 新增模块级 `_hook_restate_ratio`；章尾钩注入护栏（909-913）；plan 阶段 advisory 打印（紧接 913 后）。
- `src/hiki/prompts.py` — end_hook 字段话术（约 264 行）。
- `tests/test_produce_units.py` — `_hook_restate_ratio` 纯函数单测（扩 import + 3 测例）。
- `scratchpad/intra_restate_validate.py`（一次性，不入库）— plan-only 重跑验收。

---

## Task 1: `_hook_restate_ratio` 纯函数 + 单测

**Files:**
- Modify: `src/hiki/produce.py`（在模块级助手区，如 `_trim_tail`(193) 之后新增）
- Test: `tests/test_produce_units.py`

**Interfaces:**
- Consumes: `_re`（produce.py:23 `import re as _re`，既有）。
- Produces: `produce._hook_restate_ratio(ch: dict) -> float` —— 返回 end_hook 的 char-3gram 落在 key_events 内的比例（0.0–1.0）。高=钩子疑复述本章已交代事件。

- [ ] **Step 1: 写失败测试**

在 `tests/test_produce_units.py` 顶部 import 增加 `_hook_restate_ratio`：

```python
from hiki.produce import (_wave_bounds, _control_plane, _settle_facts, _run_ship_gate, _open_premise,
                         _source_id, _book_filename, _delivery_path, _started_at, _spine_alive_baseline,
                         _hook_restate_ratio)
```

并追加测例（文件末尾）：

```python
def test_hook_restate_ratio_flags_restatement():
    # end_hook 复述 key_event(系统流型高词面) → 高比值
    ch = {"key_events": ["陆景尝试将两块石头放入合成栏，系统提示需要材料学知识才能合成"],
          "end_hook": "合成栏中两块石头纹丝不动，系统提示：需要材料学知识解锁"}
    assert _hook_restate_ratio(ch) > 0.4


def test_hook_restate_ratio_low_for_forward_hook():
    # 前瞻钩子(指向下一章新威胁,与本章已演事件词面几乎不重合) → 低比值
    ch = {"key_events": ["陆景尝试将两块石头放入合成栏，系统提示需要材料学知识才能合成"],
          "end_hook": "远处天际裂开一道黑色缝隙，一只血红巨眼缓缓睁开，锁定了城市"}
    assert _hook_restate_ratio(ch) < 0.15


def test_hook_restate_ratio_empty_short():
    assert _hook_restate_ratio({"key_events": [], "end_hook": ""}) == 0.0
    assert _hook_restate_ratio({"key_events": ["短"], "end_hook": "也短"}) == 0.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd "E:/Project_Python/hiki-fiction-cli/claude" && python -m pytest tests/test_produce_units.py -q`
Expected: FAIL（ImportError: cannot import name `_hook_restate_ratio`）。

- [ ] **Step 3: 实现函数**

在 `src/hiki/produce.py` 的 `_trim_tail`（结尾约 202 行）之后新增：

```python
def _hook_restate_ratio(ch: dict) -> float:
    """end_hook 的 char-3gram 有多大比例落在本章 key_events 内。高=钩子疑复述本章已交代事件
    (改写式章内重述根因: drafter 把该事件正文+结尾各演一遍)。0-LLM, 纯函数。"""
    hk = _re.sub(r"\s", "", ch.get("end_hook") or "")
    kev = _re.sub(r"\s", "", "".join(str(k) for k in (ch.get("key_events") or [])))
    if len(hk) < 6 or len(kev) < 6:
        return 0.0
    g_hk = {hk[i:i + 3] for i in range(len(hk) - 3)}
    g_kev = {kev[i:i + 3] for i in range(len(kev) - 3)}
    return (len(g_hk & g_kev) / len(g_hk)) if g_hk else 0.0
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd "E:/Project_Python/hiki-fiction-cli/claude" && python -m pytest tests/test_produce_units.py -q`
Expected: PASS（全部，含 3 新测）。

- [ ] **Step 5: 提交**

```bash
cd "E:/Project_Python/hiki-fiction-cli/claude"
git add src/hiki/produce.py tests/test_produce_units.py
git commit -m "feat(produce): _hook_restate_ratio 纯函数(end_hook↔key_events 词面重合)+单测"
```

---

## Task 2: 生成纪律修复 + 章尾钩 advisory 接线

**Files:**
- Modify: `src/hiki/prompts.py`（end_hook 字段，约 264 行）
- Modify: `src/hiki/produce.py:909-913`（注入护栏 + advisory 打印）

**Interfaces:**
- Consumes: `_hook_restate_ratio`（Task 1 产出）。
- Produces: 修后 plan 的 end_hook 不复述 key_events；章尾钩注入带"全章只演一次"铁律；plan 阶段打印 `章尾钩疑复述key_event(advisory)`。

- [ ] **Step 1: end_hook 生成纪律（prompts.py）**

`src/hiki/prompts.py` 约 264 行，当前：

```python
  "end_hook":"本章结尾钩子(收在悬念/危机/反转上,给读者追下一章的理由,一句)",
```

改为：

```python
  "end_hook":"本章结尾钩子(一句,强悬念/危机/威胁,给读者追下一章的理由;须**推进性**——指向下一章的新威胁/未答问题/逼近变故,或本章高潮的最终一刻;**严禁复述本章 key_events 已交代完成的事件**,钩子不是本章事件的二次概括)",
```

- [ ] **Step 2: 注入护栏 + advisory（produce.py:909-913）**

`src/hiki/produce.py` 当前 909-913：

```python
    for ch in plan["chapters"]:                          # 章尾钩纪律(治'每章结尾钩子弱')
        hk = (ch.get("end_hook") or "").strip()
        if hk and ch["scenes"]:
            last = ch["scenes"][-1]
            last["brief"] = (last.get("brief") or "") + f"；本章必须收在钩子上:{hk}(结尾留悬念/危机,不写圆满收场)"
```

替换为：

```python
    for ch in plan["chapters"]:                          # 章尾钩纪律(治'每章结尾钩子弱')
        hk = (ch.get("end_hook") or "").strip()
        if hk and ch["scenes"]:
            last = ch["scenes"][-1]
            last["brief"] = (last.get("brief") or "") + (
                f"；本章必须收在钩子上:{hk}(结尾留悬念/危机,不写圆满收场;"
                f"铁律:若该钩子事件正文已演出,只让正文自然收束于此刻,绝不在正文先演一遍再于结尾重述一遍——同一事件全章只演一次)")
    # 章尾钩疑复述 key_event(确定性 advisory, 0-LLM): 高比值=钩子复述本章已交代事件,drafter 易双演
    # (改写式章内重述根因)。仅打印,不进门/报告/signals。词面度量,系统流型灵敏、纯语义改写召回弱(诚实局限)。
    hook_restate = [(i, r) for i, ch in enumerate(plan["chapters"])
                    if (r := _hook_restate_ratio(ch)) > 0.35]
    if hook_restate:
        print(f"章尾钩疑复述key_event(advisory): {[(f'第{i+1}章', f'{r:.0%}') for i, r in hook_restate]}")
```

- [ ] **Step 3: 跑全套件确认绿（回归）**

Run: `cd "E:/Project_Python/hiki-fiction-cli/claude" && python -m pytest -q`
Expected: PASS（全绿，无新增/无回归；prompt 与注入话术改动不被任何测试断言）。

- [ ] **Step 4: 提交**

```bash
cd "E:/Project_Python/hiki-fiction-cli/claude"
git add src/hiki/prompts.py src/hiki/produce.py
git commit -m "feat(plan): end_hook 生成纪律+章尾钩注入护栏(全章只演一次)+疑复述advisory"
```

---

## Task 3: plan-only 重跑验收

**Files:**
- Create: `scratchpad/intra_restate_validate.py`（一次性，不入库）

**Interfaces:**
- Consumes: `produce._stage_plan(cli, bible, scenes, out_dir, n_ch, force)`（produce.py:827）；`produce._hook_restate_ratio`；各 flagged 本 output 目录的 `bible.json`/`scenes.json`/`plan.json`。
- Produces: 4 个 flagged 章的 before/after end_hook + 比值对照，确认修后不再复述。

- [ ] **Step 1: 写验收脚本**

新建 `scratchpad/intra_restate_validate.py`：

```python
"""章内重述事前规避验收(plan-only): 用修后 prompt 重跑 _stage_plan(从已存 bible/scenes,
不重 mine/draft), 对 flagged 章看 end_hook 是否不再复述 key_events。
用法: PYTHONPATH=src python scratchpad/intra_restate_validate.py
"""
import asyncio, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki import produce

ROOT = Path("E:/Project_Python/hiki-fiction-cli/claude")
# (output 目录, flagged 章 1-based)
BOOKS = [
    ("output/CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full", [2]),
    ("output/CPBGX00192灵气复苏：开局无限合成_20260625_full", [1]),
    ("output/ZYGGY02079农女为后：皇上独宠我", [1, 30]),
]


async def main():
    cli = Client()
    scratch = Path(tempfile.mkdtemp(prefix="intra_val_"))
    for rel, flagged in BOOKS:
        d = ROOT / rel
        bible = json.loads((d / "bible.json").read_text(encoding="utf-8"))
        scenes = json.loads((d / "scenes.json").read_text(encoding="utf-8"))
        old_plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
        print(f"\n{'='*68}\n[{d.name[:30]}]")
        # BEFORE: 现产 plan
        for ci in flagged:
            ch = old_plan["chapters"][ci - 1]
            print(f"  第{ci}章 BEFORE 比值={produce._hook_restate_ratio(ch):.0%} hook={ch.get('end_hook')[:60]}")
        # AFTER: 修后 prompt 重跑 plan(写到 scratch, 不动产物)
        sub = scratch / d.name
        sub.mkdir(parents=True, exist_ok=True)
        pl = await produce._stage_plan(cli, bible, scenes, sub, len(old_plan["chapters"]), True)
        new_plan = pl["plan"]
        for ci in flagged:
            ch = new_plan["chapters"][ci - 1]
            print(f"  第{ci}章 AFTER  比值={produce._hook_restate_ratio(ch):.0%} hook={ch.get('end_hook')[:60]}")
    print(f"\n总 calls={cli.calls} cost=¥{cli.cost_cny:.2f}  scratch={scratch}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 跑验收（真实 API，plan 阶段，约几本×规划，¥个位数）**

Run: `cd "E:/Project_Python/hiki-fiction-cli/claude" && PYTHONPATH=src python scratchpad/intra_restate_validate.py`
Expected: 每个 flagged 章 AFTER 的比值显著低于 BEFORE，且 AFTER 的 end_hook 人眼判为**推进性/单次**（指向下一章威胁或本章最终一刻，不再是已演事件的二次概括）。

**验收门槛**：4 章全部 AFTER 不再复述（比值掉 + 人眼判推进性），且钩子未变软（仍悬念/危机/威胁）。
若某章 AFTER 仍复述（比值未掉或人眼仍是二次概括）→ 不通过：回 Task 2 收紧 prompt（强化"钩子指向下一章、不概括本章"），重跑。
注：`_stage_plan` 为 LLM 随机；个别章可重跑 1-2 次确认稳定，非单次偶然。

- [ ] **Step 3: 记录验收结论**

把 before/after 对照写入 `docs/evidence/readthrough_defect_catalog.md` 末尾"章内重述事前规避验收"一节（脚本不入库，结论入库）。

```bash
cd "E:/Project_Python/hiki-fiction-cli/claude"
git add docs/evidence/readthrough_defect_catalog.md
git commit -m "docs(evidence): 章内重述事前规避 plan-only 验收(4 flagged 章 end_hook 不再复述)"
```

---

## Self-Review

**Spec coverage:**
- end_hook 生成纪律 → Task 2 Step 1 ✓
- 章尾钩注入护栏（mirror R15 铁律）→ Task 2 Step 2 ✓
- 0-LLM 确定性 advisory（验证度量+回归护栏）→ Task 1（函数+单测）+ Task 2 Step 2（接线打印）✓
- plan-only 验收（3 本重跑、4 章不再复述、钩子不软）→ Task 3 ✓
- 不建检测器/不改词面硬门/不动 R15 → 不在任何 task（Global Constraints 锁定）✓
- 单测核对无字符串撞测 → 已在 Global Constraints 核对 ✓

**Placeholder scan:** 无 TBD/TODO；每个代码步含完整代码；阈值 0.35（advisory，Task 2）与单测断言量级（0.4/0.15，Task 1，不绑阈值）均具体。

**Type consistency:** `_hook_restate_ratio(ch: dict) -> float` 在 Task 1 定义、Task 2 接线、Task 3 验收三处签名一致；`_stage_plan(cli, bible, scenes, out_dir, n_ch, force)` 调用与 produce.py:827 签名一致；advisory 阈值 0.35 只在 Task 2 注入处。
