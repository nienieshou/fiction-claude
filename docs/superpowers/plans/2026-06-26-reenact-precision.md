# D2 重演精度修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 reenact_hits 喂交付门前去除"视角转述"假阳性，得到干净的真重演信号，解除阈值重标定的前置阻塞。

**Architecture:** 检出→裁决两段。`_plane_check`（produce.py）第一段 PLANE_CHECK 保持高召回不动；新增第二段裁决器 `_adjudicate`（用新 prompt `REENACT_ADJUDICATE`）对每个 raw hit 判"真重演 vs 视角转述"，存疑保留，只把真重演喂闸门，视角转述进 advisory 留痕。

**Tech Stack:** Python 3 / asyncio / DeepSeek async client / pytest（FakeClient 零真实 API）。

设计文档：`docs/superpowers/specs/2026-06-26-reenact-precision-design.md`

## Global Constraints

- `_plane_check` 返回类型从 `list[str]` 改为 `tuple[list[str], list[str]]` = `(真重演清单, 视角转述滤除清单)`。所有 return 路径（含 `len(ch_texts)<2` 无对应、`not raw_pairs` 早返、except 兜底、正常返回）都返回 2-tuple。
- 裁决存疑保留偏向：仅当裁决器显式返回 `{"reenact": false}` 才判视角转述（丢弃）；其余（true / 缺键 / 空响应 / 解析失败）一律保留为真重演。判别式 `r.get("reenact") is not False`。
- hit 标签格式保持 `第{ci+1}章重演[{event}]`（与现 produce.py:1180 一致，event 已 `[:40]` 截断），使 scripts/repair_replay.py 的正则 `第(\d+)章重演\[(.*?)\]` 仍可解析。
- 无 schema 变更：`SIGNAL_SCHEMA_VERSION` 维持 1；`signals.build_signal_vector` 签名不动；`reenact_hits` 既有 key，值变干净。
- 单一来源变量 `reenact_hits` 喂全部三个消费者（闸门 via `sig["reenact_hits"]`→`_run_ship_gate` 的 `事件重演`、报告 `控制面重演核对`、`signals.reenact_hits`）。把清后真重演列表赋给该变量即三处自动干净；**不**新增 gate 映射。
- advisory 字段 `控制面重演_视角转述滤除` **只**进报告 dict，不进 `sig`、不喂闸门、不进 signals。
- 不动 PLANE_CHECK 第一段召回逻辑；不动 adj-dup 通道；不做阈值重标定（清信号后的独立下一步）。
- 校准验收门槛：标注样本上 **0 漏真重演**（漏一个真重演=不通过）；FP 滤除率尽量高。标注：ZYGGY02252 ch29/ch38 必丢、CPBXN00188 ch49/ch18 必留。

---

## File Structure

- `src/hiki/prompts.py` — 新增 `REENACT_ADJUDICATE`（紧邻 PLANE_CHECK，prompts.py:530-537）。
- `src/hiki/produce.py` — `_plane_check`（1163-1187）二段化、返回 2-tuple；调用点（~1387）解包；报告 dict（~1453）新增 advisory 字段。
- `tests/test_reenact_precision.py`（新）— FakeClient 单测，覆盖裁决分类 / 保守保留 / 无 hit 跳过 / 多 hit 不串位。
- `scripts/reenact_precision_calib.py`（新）— 标注集校准脚本（真实 API，手动跑一次，非 pytest）。

---

## Task 1: 裁决器 prompt + `_plane_check` 二段化 + 单测

**Files:**
- Modify: `src/hiki/prompts.py`（在 PLANE_CHECK 之后追加 REENACT_ADJUDICATE）
- Modify: `src/hiki/produce.py:1163-1187`（`_plane_check`）
- Test: `tests/test_reenact_precision.py`（新建）

**Interfaces:**
- Consumes: `prompts.PLANE_CHECK`（既有，`(sys, usr)` 二元组，usr 含 `{exclusion}`/`{text}`）；`gate._safe_json(raw) -> dict|None`（既有）；`plan["chapters"][j]["key_events"]`（既有结构）。
- Produces: `prompts.REENACT_ADJUDICATE = (sys: str, usr: str)`，usr 含 `{event}`/`{text}` 占位符。`produce._plane_check(cli, ch_texts: list[str], plan: dict) -> tuple[list[str], list[str]]`，返回 `(真重演清单, 视角转述滤除清单)`，标签格式 `第{ci+1}章重演[{event}]`。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_reenact_precision.py`：

```python
"""重演精度: PLANE_CHECK 高召回 + 裁决器滤除视角转述。FakeClient(零真实 API)。"""
import asyncio
import json
from hiki import produce


class FakeClient:
    """按 bucket 分队列返回预置响应。detect 与 裁决 都走 'chunk_extract',
    按调用顺序出队(detect 先于裁决, ci 升序)。complete 无内部 await →
    gather 下按列表顺序跑完, 出队确定。"""
    def __init__(self, by_bucket: dict):
        self.q = {k: list(v) for k, v in by_bucket.items()}
        self.calls = []

    async def complete(self, bucket, sys, usr, *, json_mode=False, max_tokens=0, temperature=0.0):
        self.calls.append(bucket)
        return self.q[bucket].pop(0)


def _run(coro):
    return asyncio.run(coro)


# 2章: ci=0 exclusion 空(不调用 detect), ci=1 exclusion=ch0 的 key_events → 1 次 detect
PLAN2 = {"chapters": [{"key_events": ["甲事件"]}, {"key_events": []}]}
CH2 = ["第一章正文", "第二章正文" * 50]


def test_adjudicate_true_keeps_as_reenact():
    cli = FakeClient({"chunk_extract": [
        json.dumps({"reenacted": ["第1章:甲事件"]}),       # detect → 1 hit
        json.dumps({"reenact": True, "why": "镜头重搭"}),  # 裁决 → 真重演
    ]})
    kept, filtered = _run(produce._plane_check(cli, CH2, PLAN2))
    assert kept == ["第2章重演[第1章:甲事件]"]
    assert filtered == []


def test_adjudicate_false_drops_as_relay():
    cli = FakeClient({"chunk_extract": [
        json.dumps({"reenacted": ["第1章:甲事件"]}),
        json.dumps({"reenact": False, "why": "对话转述"}),  # 裁决 → 视角转述
    ]})
    kept, filtered = _run(produce._plane_check(cli, CH2, PLAN2))
    assert kept == []
    assert filtered == ["第2章重演[第1章:甲事件]"]


def test_adjudicate_empty_conservative_keeps():
    # 裁决空响应 → {} → r.get("reenact") is not False == True → 存疑保留(判真重演)
    cli = FakeClient({"chunk_extract": [
        json.dumps({"reenacted": ["第1章:甲事件"]}),
        "",                                                  # 裁决空
    ]})
    kept, filtered = _run(produce._plane_check(cli, CH2, PLAN2))
    assert kept == ["第2章重演[第1章:甲事件]"]
    assert filtered == []


def test_no_raw_hits_skips_adjudication():
    cli = FakeClient({"chunk_extract": [json.dumps({"reenacted": []})]})  # detect 无 hit
    kept, filtered = _run(produce._plane_check(cli, CH2, PLAN2))
    assert kept == [] and filtered == []
    assert cli.calls == ["chunk_extract"]                    # 只 detect, 无裁决调用


def test_multi_hit_classified_no_crosstalk():
    # 3章: ci=1, ci=2 各产 1 hit; 裁决 A=keep, B=drop, 归类不串位
    plan = {"chapters": [{"key_events": ["甲"]}, {"key_events": ["乙"]}, {"key_events": []}]}
    ch = ["第一章", "第二章" * 50, "第三章" * 50]
    cli = FakeClient({"chunk_extract": [
        json.dumps({"reenacted": ["第1章:甲"]}),   # detect ci=1 → hit A
        json.dumps({"reenacted": ["第2章:乙"]}),   # detect ci=2 → hit B
        json.dumps({"reenact": True}),              # 裁决 A → keep
        json.dumps({"reenact": False}),             # 裁决 B → drop
    ]})
    kept, filtered = _run(produce._plane_check(cli, ch, plan))
    assert kept == ["第2章重演[第1章:甲]"]
    assert filtered == ["第3章重演[第2章:乙]"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd "E:/Project_Python/hiki-fiction-cli/claude" && python -m pytest tests/test_reenact_precision.py -v`
Expected: FAIL — 现 `_plane_check` 返回 list（非 2-tuple），解包 `kept, filtered = ...` 报 `ValueError`/`too many values`，且 `prompts.REENACT_ADJUDICATE` 不存在。

- [ ] **Step 3: 加 REENACT_ADJUDICATE prompt**

在 `src/hiki/prompts.py` 的 PLANE_CHECK 定义（结尾 `{text}""")`，约 537 行）之后追加：

```python
# R13b: 重演裁决(精度) — 区分"真重演(镜头重搭/伪进展)"与"视角转述(对话/回忆转告)", 存疑保留
REENACT_ADJUDICATE = ("你是重演裁决员,只区分'真重演'与'视角转述',存疑判真重演。", """下面是一个"疑似被重演的已演出事件"和本章正文。判断本章对该事件的处理属于:
A.真重演(缺陷):叙事镜头把该事件当作新发生的事**重新搬演**——角色再次现场行动/说原话、零新进展;或同一场景仅改细微数值/措辞制造**伪推进**。
B.视角转述(正常):某角色在**对话或回忆中转述**该事件给另一方,镜头不重搭场景,且听者由此获知/决定/反应、推进了关系或情节。
存疑、或两者皆像 → 判 A。
【疑似事件】:{event}
输出 JSON:{{"reenact":true或false,"why":"<15字>"}} (true=真重演A保留, false=视角转述B丢弃)
本章正文:
{text}""")
```

- [ ] **Step 4: `_plane_check` 二段化**

把 `src/hiki/produce.py` 的 `_plane_check`（1163-1187）整体替换为：

```python
async def _plane_check(cli: Client, ch_texts: list[str], plan: dict) -> tuple[list[str], list[str]]:
    """4j 控制面核对: 章正文 vs 近3章 exclusion 清单, 检版本互斥重演(高召回第一段)。
    第二段裁决: 对每个 raw hit 判 真重演 vs 视角转述(存疑保留), 只把真重演喂闸门。
    返回 (真重演清单, 视角转述滤除清单)。"""
    try:
        sys_pc, usr_pc = prompts.PLANE_CHECK
        sys_aj, usr_aj = prompts.REENACT_ADJUDICATE

        async def _pc(ci: int) -> list[tuple[int, str]]:
            excl = []
            for j in range(max(0, ci - 3), ci):
                for k in (plan["chapters"][j].get("key_events") or []):
                    if str(k).strip():
                        excl.append(f"第{j + 1}章:{str(k)[:40]}")
            if not excl:
                return []
            raw = await cli.complete("chunk_extract", sys_pc,
                                     usr_pc.format(exclusion="\n".join(excl[-6:]), text=ch_texts[ci][:6000]),
                                     json_mode=True, max_tokens=300, temperature=0.1)
            r = gate._safe_json(raw) or {}
            return [(ci, str(x)[:40]) for x in (r.get("reenacted") or []) if str(x).strip()]

        async def _adjudicate(ci: int, event: str) -> bool:
            raw = await cli.complete("chunk_extract", sys_aj,
                                     usr_aj.format(event=event, text=ch_texts[ci][:6000]),
                                     json_mode=True, max_tokens=200, temperature=0.1)
            r = gate._safe_json(raw) or {}
            return r.get("reenact") is not False        # 存疑保留: 仅显式 false 判视角转述

        raw_pairs = [p for lst in await asyncio.gather(*[_pc(ci) for ci in range(len(ch_texts))]) for p in lst]
        if not raw_pairs:
            return [], []
        keeps = await asyncio.gather(*[_adjudicate(ci, ev) for ci, ev in raw_pairs])
        reenact_hits, filtered = [], []
        for (ci, ev), keep in zip(raw_pairs, keeps):
            label = f"第{ci + 1}章重演[{ev}]"
            (reenact_hits if keep else filtered).append(label)
        if reenact_hits or filtered:
            print(f"控制面核对: {len(reenact_hits)} 真重演 + {len(filtered)} 视角转述滤除")
        return reenact_hits, filtered
    except Exception as e:
        print(f"控制面核对跳过:{type(e).__name__}")
        return [], []
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd "E:/Project_Python/hiki-fiction-cli/claude" && python -m pytest tests/test_reenact_precision.py -v`
Expected: PASS — 5/5。

- [ ] **Step 6: 提交**

```bash
cd "E:/Project_Python/hiki-fiction-cli/claude"
git add src/hiki/prompts.py src/hiki/produce.py tests/test_reenact_precision.py
git commit -m "feat(produce): _plane_check 二段化, 裁决器滤除视角转述FP; 返回(真重演,滤除)"
```

注：此步后调用点（produce.py:1387）仍按单值解包 `reenact_hits = await _plane_check(...)`，会拿到 2-tuple。该路径在 api-marked 整本流程内，非 api 套件不触发，故全套件仍绿；Task 2 修正调用点。

---

## Task 2: 调用点解包 + advisory 留痕字段

**Files:**
- Modify: `src/hiki/produce.py:1387`（调用点解包）
- Modify: `src/hiki/produce.py:1453`（报告 dict 新增 advisory 字段）

**Interfaces:**
- Consumes: `produce._plane_check(...) -> tuple[list[str], list[str]]`（Task 1 产出）。
- Produces: 调用点局部变量 `reenact_hits`（清后真重演 list，喂 sig/报告/signals）与 `reenact_filtered`（视角转述 list，只进报告 advisory 字段 `控制面重演_视角转述滤除`）。

- [ ] **Step 1: 解包调用点**

`src/hiki/produce.py:1387` 当前：

```python
    reenact_hits = await _plane_check(cli, ch_texts, plan)
```

改为：

```python
    reenact_hits, reenact_filtered = await _plane_check(cli, ch_texts, plan)
```

（`reenact_hits` 现为清后真重演列表，原样流入 `sig["reenact_hits"]`（1430）→ `_run_ship_gate` 的 `事件重演`（1212）、报告 `控制面重演核对`（1453）、`signals.build_signal_vector(reenact_hits=len(reenact_hits))`（1482），三处自动取清后数，无需其它改动。）

- [ ] **Step 2: 报告 dict 加 advisory 字段**

`src/hiki/produce.py:1453` 当前：

```python
        "控制面重演核对": reenact_hits or ["无"],
```

在其后紧接一行（即 `"邻章版本_检出"` 之前）插入：

```python
        "控制面重演核对": reenact_hits or ["无"],
        "控制面重演_视角转述滤除": reenact_filtered or ["无"],
```

- [ ] **Step 3: 跑全套件确认绿（回归）**

Run: `cd "E:/Project_Python/hiki-fiction-cli/claude" && python -m pytest -q`
Expected: PASS — 全绿（199 passed, 1 deselected：Task 1 的 5 个新测 + 既有 194；api golden 测仍被 `-m 'not api'` deselect）。

注：闸门/报告/signals 取清后真重演数的活路径只在 api-marked 整本流程内（golden 测 + Task 3 校准跑覆盖），非 api 套件不触发；本步只验回归不破。

- [ ] **Step 4: 提交**

```bash
cd "E:/Project_Python/hiki-fiction-cli/claude"
git add src/hiki/produce.py
git commit -m "feat(produce): 解包_plane_check 2-tuple; 报告加'控制面重演_视角转述滤除'advisory"
```

---

## Task 3: 标注集校准脚本 + 验收跑

**Files:**
- Create: `scripts/reenact_precision_calib.py`

**Interfaces:**
- Consumes: `produce._plane_check(cli, ch_texts, plan)`（Task 1/2 产出）；两本 output 目录的 `final.md` + `plan.json`。
- Produces: 命令行报告 — 每本的 真重演清单 / 视角转述滤除清单，并断言标注门槛（ZYGGY ch29/ch38 在滤除集、CPBXN ch49/ch18 在真重演集）。

- [ ] **Step 1: 写校准脚本**

新建 `scripts/reenact_precision_calib.py`：

```python
"""重演精度校准(2026-06-26): 在标注 holdout 上实跑 _plane_check 二段, 验收:
ZYGGY02252 ch29/ch38 应被滤除(视角转述FP), CPBXN00188 ch49/ch18 应保留(真重演TP), 0 漏真重演。
用法: PYTHONPATH=src python scripts/reenact_precision_calib.py
"""
import asyncio, json, re, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki import produce

ROOT = Path("E:/Project_Python/hiki-fiction-cli/claude")
_HDR = re.compile(r"^# 第\d+章.*$", re.M)
# (final.md, plan.json, 应被滤除章集, 应保留章集)
BOOKS = {
    "CPBXN00188": (ROOT / "output/CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full/final.md",
                   ROOT / "output/CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full/plan.json",
                   set(), {49, 18}),
    "ZYGGY02252": (ROOT / "output/ZYGGY02252归隐田园：执子手共白头/final.md",
                   ROOT / "output/ZYGGY02252归隐田园：执子手共白头/plan.json",
                   {29, 38}, set()),
}
_CHNO = re.compile(r"第(\d+)章重演")


def split_chapters(md: str) -> list[str]:
    return [b.strip() for b in _HDR.split(md)[1:] if b.strip()]


def chap_nums(hits: list[str]) -> set[int]:
    return {int(m.group(1)) for h in hits if (m := _CHNO.search(h))}


async def main():
    cli = Client()
    ok = True
    for tag, (md_p, plan_p, must_drop, must_keep) in BOOKS.items():
        ch = split_chapters(md_p.read_text(encoding="utf-8"))
        plan = json.loads(plan_p.read_text(encoding="utf-8"))
        kept, filtered = await produce._plane_check(cli, ch, plan)
        kept_n, filt_n = chap_nums(kept), chap_nums(filtered)
        print(f"\n[{tag}] 真重演 {len(kept)} 章{sorted(kept_n)} | 视角转述滤除 {len(filtered)} 章{sorted(filt_n)}")
        # 验收: must_drop 必须在滤除集(不在真重演集); must_keep 必须在真重演集
        drop_fail = must_drop - filt_n
        keep_fail = must_keep - kept_n
        leak = must_drop & kept_n          # 标注FP却被判真重演 = 精度未达(非致命)
        miss = must_keep - kept_n          # 标注真重演却漏 = 0漏门槛违反(致命)
        if drop_fail or keep_fail:
            ok = False
        print(f"   应丢{sorted(must_drop)}→{'OK' if not drop_fail else f'未滤{sorted(drop_fail)}'}"
              f" | 应留{sorted(must_keep)}→{'OK' if not keep_fail else f'漏{sorted(keep_fail)}'}")
        if miss:
            print(f"   ✗ 致命: 漏真重演 {sorted(miss)}")
    print(f"\n总 calls={cli.calls}  cost=¥{cli.cost_cny:.2f}  验收={'通过' if ok else '不通过'}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 跑校准（真实 API，约几十 calls，¥<1）**

Run: `cd "E:/Project_Python/hiki-fiction-cli/claude" && PYTHONPATH=src python scripts/reenact_precision_calib.py`
Expected: 末行 `验收=通过`；ZYGGY 应丢 `[29,38]→OK`、CPBXN 应留 `[18,49]→OK`；无 `✗ 致命` 行。

若 `✗ 致命: 漏真重演`（CPBXN ch18/ch49 被误滤）→ 不通过：裁决 prompt 偏向过松，回 Task 1 收紧 REENACT_ADJUDICATE 的 A 类定义（强调"镜头重搭/伪进展即 A"），重跑。
若仅"未滤"（ZYGGY ch29/ch38 没全滤掉）→ 精度未尽但非致命：记录残留，可接受（偏向召回）。

- [ ] **Step 3: 提交脚本**

```bash
cd "E:/Project_Python/hiki-fiction-cli/claude"
git add scripts/reenact_precision_calib.py
git commit -m "test(calib): 重演精度标注集校准脚本(ZYGGY ch29/38滤除, CPBXN ch49/18保留)"
```

---

## Self-Review

**Spec coverage:**
- 检出→裁决两段、PLANE_CHECK 不动 → Task 1 ✓
- REENACT_ADJUDICATE prompt + 判别规则 + 存疑保留 → Task 1 Step 3/4 ✓
- 返回 2-tuple、标签格式保持 → Task 1 ✓（Global Constraints 锁定）
- 单一变量喂三消费者、无 gate 映射、无 schema 变更 → Task 2 ✓
- advisory 留痕 `控制面重演_视角转述滤除` 只进报告 → Task 2 Step 2 ✓
- FakeClient 单测（分类/保守/无 hit/多 hit）→ Task 1 Step 1 ✓
- 标注集校准 0 漏真重演 → Task 3 ✓
- 不做阈值重标定 → 不在任何 task（YAGNI 边界）✓

**Placeholder scan:** 无 TBD/TODO；每个代码步含完整代码。

**Type consistency:** `_plane_check -> tuple[list[str], list[str]]` 在 Task 1 定义、Task 2 解包、Task 3 调用一致；`REENACT_ADJUDICATE` 二元组 `(sys, usr)` 与 PLANE_CHECK 同形；`reenact: false` 判别式 `is not False` 在 prompt 输出契约、_adjudicate、单测三处一致。
