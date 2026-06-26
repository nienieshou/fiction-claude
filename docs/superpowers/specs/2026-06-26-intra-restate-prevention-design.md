# 章内重述事前规避 — 设计文档

**日期**: 2026-06-26
**状态**: 已批准设计，待转写实现计划
**来源**: 保留集验证读（docs/evidence/readthrough_defect_catalog.md）+ 本轮根因诊断证实"改写式章内重述"有统一的生成侧根因。

## 问题

同一事件/桥段在**同一章内换措辞演两遍**（读者可见的注水/重复）。现有 `_intra_repeat`（produce.py:1410）是 12-gram **词面**检测，抓逐字双写（ch59 飞升写两遍），但漏**改写式**重述（措辞不同，词面重合低）。

根因诊断（4 例，跨题材，统一机制）：

| 案例 | 题材 | end_hook 复述了正文已演的 |
|---|---|---|
| CPBXN00188 ch2 | 系统流 | 系统奖励徐冰冰+秘术 |
| CPBGX00192 ch1 | 系统流 | 系统提示"需材料学知识解锁" |
| ZYGGY02079 ch1 | 古言 | 场景结尾决意"不再被欺负"的复述 |
| ZYGGY02079 ch30 | 古言 | 绑架"拖上马车疾驰而去"（正文已完整演完） |

机制：plan 的 `end_hook`（prompts.py:264 规划器生成）复述了本章 scene 正文已交代完成的事件；产线 **章尾钩纪律**（produce.py:909-913）把 end_hook 追加进最后一个 scene 的 brief（`本章必须收在钩子上:{end_hook}`），drafter 忠实地把该事件**写两遍**（正文一遍 + 结尾钩子一遍）。R15（produce.py:914-938）已有 scene 间 anti-重演铁律，但**不覆盖 end_hook 复述本 scene 自身 payload** 这个洞。

## 目标

生成侧事前规避：让 end_hook 不复述本章已交代事件，从源头消除改写式章内双演。不建语义检测器、零 per-chapter LLM 成本、无新信号 schema、无闸门改动。现有词面 `章内双版本` 硬门保留做逐字双写安全网。

## 非目标（YAGNI 边界）

- 不建事后语义检测器（事前治根即可）。
- 不改现有词面 `_intra_repeat` / `章内双版本` 硬门。
- 不动 R15 高潮章/非高潮章 scene 间铁律逻辑（与本修复正交）。
- 不做 plan+draft 全链重跑验证（plan-only 已证复述源移除；端到端为可选）。

## 修复（两点，mirror R15 铁律话术）

### (a) end_hook 生成纪律 — prompts.py:264

当前（chapter-plan prompt 模板里的字段）:
```
  "end_hook":"本章结尾钩子(收在悬念/危机/反转上,给读者追下一章的理由,一句)",
```
改为:
```
  "end_hook":"本章结尾钩子(一句,强悬念/危机/威胁,给读者追下一章的理由;须**推进性**——指向下一章的新威胁/未答问题/逼近变故,或本章高潮的最终一刻;**严禁复述本章 key_events 已交代完成的事件**,钩子不是本章事件的二次概括)",
```
保持钩子强度（章尾钩纪律本治"钩子弱"，不得为去重写软——"逼近的威胁"本身是强钩）。

### (b) 章尾钩注入护栏 — produce.py:909-913

当前:
```python
    for ch in plan["chapters"]:                          # 章尾钩纪律(治'每章结尾钩子弱')
        hk = (ch.get("end_hook") or "").strip()
        if hk and ch["scenes"]:
            last = ch["scenes"][-1]
            last["brief"] = (last.get("brief") or "") + f"；本章必须收在钩子上:{hk}(结尾留悬念/危机,不写圆满收场)"
```
改最后一行的追加话术为（mirror R15 "绝不重写/重演"铁律）:
```python
            last["brief"] = (last.get("brief") or "") + (
                f"；本章必须收在钩子上:{hk}(结尾留悬念/危机,不写圆满收场;"
                f"铁律:若该钩子事件正文已演出,只让正文自然收束于此刻,绝不在正文先演一遍再于结尾重述一遍——同一事件全章只演一次)")
```

## 确定性回归护栏 + 验证度量（0-LLM, advisory）

plan 阶段加一个确定性 advisory：量 end_hook 与本章 key_events 的词面重合，高→疑复述。**只打印**（mirror place_drift/R15 的 plan 阶段打印，不进报告、不进门、不进 signals）。

```python
def _hook_restate_ratio(ch: dict) -> float:
    """end_hook 的 char-3gram 有多大比例落在 key_events 内。高=钩子疑复述本章已交代事件。"""
    hk = _re.sub(r"\s", "", ch.get("end_hook") or "")
    kev = _re.sub(r"\s", "", "".join(str(k) for k in (ch.get("key_events") or [])))
    if len(hk) < 6 or len(kev) < 6:
        return 0.0
    g_hk = {hk[i:i + 3] for i in range(len(hk) - 3)}
    g_kev = {kev[i:i + 3] for i in range(len(kev) - 3)}
    return (len(g_hk & g_kev) / len(g_hk)) if g_hk else 0.0
```
放在 produce.py 章尾钩注入循环（909-913）**之前**（量原始 end_hook，未被注入污染）。阈值起点 **0.35**，实现时按 flagged 集（4 章应跳、clean 章不应跳）微调。打印 `章尾钩疑复述key_event(advisory): [第N章 0.XX, ...]`。

**诚实局限**：词面度量对系统流高词面复述（CPBXN/CPBGX00192）灵敏；对纯语义改写（ZYGGY ch30 绑架）召回弱（与 12-gram 同源局限）；且无法区分"正当高潮钩子"与"冗余复述"（两者都与 key_events 重合）。故为**advisory 噪声 tripwire**：用途是 (1) 验证时量 flagged 集的 before/after 趋势，(2) 长线回归可见性——非精确检测器。

## 验证

### 修复验收（plan-only，便宜；draft 是贵的大头，规划是零头）

对含 flagged 章的 3 本（CPBXN00188 / CPBGX00192 / ZYGGY02079）**只重跑规划阶段**，生成新 plan：
- 4 个 flagged 章（CPBXN ch2 / CPBGX00192 ch1 / ZYGGY ch1+ch30）的新 end_hook **不再复述** key_events（`_hook_restate_ratio` 掉 + 人眼判推进性）。
- 钩子未变软（仍悬念/危机/威胁，非圆满收场）。
- **验收门槛**：4 章全部不再复述且钩子强度不降。

### 单测回归

- 现有套件绿。**特别核对**：无测试断言 produce.py:909-913 章尾钩 append 的精确字符串（改注入话术别撞测试）；无测试断言 prompts.py end_hook 字段精确文本。
- 为 `_hook_restate_ratio` 加纯函数单测（0-LLM）：构造 end_hook 复述 key_event 的章 → 高比例；前瞻钩子章 → 低比例；空/短字段 → 0.0。

### 可选端到端（若要眼见 draft 不再双演）

用修后 plan 重画 1-2 个 flagged 章，确认 draft 正文不再把该事件演两遍。贵，非验收必需。

## 受影响文件

- `src/hiki/prompts.py` — end_hook 字段话术（生成纪律）。
- `src/hiki/produce.py` — 章尾钩注入护栏（909-913）+ 新增 `_hook_restate_ratio` + plan 阶段 advisory 打印。
- `tests/test_produce_units.py`（或就近测试文件）— `_hook_restate_ratio` 纯函数单测。
- scratchpad 验收脚本（一次性，plan-only 重跑 + 度量，不入库）。
