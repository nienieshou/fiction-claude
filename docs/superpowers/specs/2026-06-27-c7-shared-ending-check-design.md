# C7.1 共享 ending_check 设计

> 2026-06-27 · 技术债 C7(point_repair 重实现 produce 尾门,手工同步)首切。范围:**仅 ENDING_CHECK 检测抽共享**。
> C7 全量(revival/ending/continuity dedup)— 本 spec 只做 ending 检测;revival/continuity 余切后续(缠 B1 尾门)。
> 基于:`master`(独立)。配套:`docs/design/tech-debt.md` C7 行。

## 目标

把 `produce._ending_guard` 与 `point_repair.run()` 里**逐字重复**的 ENDING_CHECK 检测循环抽成单一 `gate.ending_check`,两处都 call,消手工同步。**行为逐位保持**。

**风险姿态:行为保持**——纯债务消减,零产品变化。

## 现状(已核实,master)

两处的 ENDING_CHECK 检测循环**逐字相同**:`for t in range(3): cli.complete("chunk_extract", ENDING_CHECK, usr_ec.format(prev_tail, tail), json_mode=True, max_tokens=400, temperature=0.1+0.1*t); ec=_safe_json(raw) or {}; if "ok" in ec: break`。

- **`produce._ending_guard`**(`produce.py:1044-1071`):`prev_tail = ch_texts[-2][-800:]`;`tail = ch_texts[-1][-2500:]`;循环用 `for-else`(无 break → `ec={}`);下游:`ec.get("skipped")` → climax_skipped;`ec.get("ok") is False` → ENDING_FIX 补收束拍;返回 `{ch_texts, ending_fixed, climax_skipped}`。
- **`point_repair.run`**(`point_repair.py:155-170`):`prev_tail = chs[-2][-800:]`;`tail_blob = last if len(last)<=4500 else (last[:2000]+"……(中略)……"+last[-2000:])`(点修把补演加在末章**开头**,需看头→FP 修复实证);循环前 `ec={}`;下游:`ec.get("skipped") is True` → flag `预告事件仍被跳过`(**不修**)。

**唯一差异 = tail 输入**(produce 末尾 2500 / point_repair 头+尾 blob),是各调用方**设计需要**,非 drift。检测循环本身 + 调用参数完全一致。

## 架构

### 共享函数(家:`gate.py`,与 `continuity_check`/`gold_pk` 同列 LLM 门检测)
`gate.py` 已 `from . import prompts`、`from .client import Client`、本地 `_safe_json`,是天然家。加:
```python
async def ending_check(cli: Client, prev_tail: str, tail: str) -> dict:
    """ENDING_CHECK 检测(3-retry-on-empty)。共享: produce._ending_guard + point_repair 两处 call。
    返回 ec dict({ok, problem, skipped, skipped_what} 等); 3 次仍无 "ok" 键 → {}。
    调用方各自算 prev_tail/tail(point_repair 头+尾 blob vs produce last[-2500:], tail 差异是设计)。"""
    sys_ec, usr_ec = prompts.ENDING_CHECK
    for t in range(3):
        raw = await cli.complete("chunk_extract", sys_ec,
                                 usr_ec.format(prev_tail=prev_tail, tail=tail),
                                 json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
        ec = _safe_json(raw) or {}
        if "ok" in ec:
            return ec
    return {}
```
`return {}` 末尾 = produce `for-else: ec={}` 与 point_repair 全失败→{} 的统一(消费方查 `ok`/`skipped`,等价)。

### 两处 adapter(各保留下游,行为逐位保持)
- **`produce._ending_guard`**:删内联检测循环,改 `ec = await gate.ending_check(cli, prev_tail, ch_texts[-1][-2500:])`(prev_tail 算法不变);**下游修复(climax_skipped/ENDING_FIX 补收束/返回 dict)逐字不变**。
- **`point_repair.run`**:删内联检测循环(:160-168),改 `ec = await gate.ending_check(cli, prev_tail, tail_blob)`(prev_tail/tail_blob 算法不变);**下游 flag 逐字不变**。

## 验证
- `tests/test_ending_check.py`(或并入既有):`gate.ending_check` 单测(mock cli)——返 `{"ok":True}` 即返、前 N 次畸形→重试、全畸形→`{}`、`skipped`/`problem` 字段透传、温度递增 0.1/0.2/0.3。
- 两 adapter 行为逐位保持:既有测试(`test_stages`/`test_produce_units`/`test_point_repair_units`)+ 全量绿。
- `for-else`→`return {}` 等价:全失败时两处都得 `{}`,消费方 `ec.get("skipped")`/`ec.get("ok")` 行为不变。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- revival dedup(`point_repair._verified_revivals` vs produce `_fact_audit_repair`)/ continuity dedup(3 窗 continuity_check + _verify_advisories)—— C7 余切,缠 produce 尾门(B1),后续。
- 不改 tail 输入差异(各调用方设计)/ 不改下游修复/flag 逻辑 / 不动 ENDING_FIX。

## 风险
- **tail 差异必须保留**:produce `ch_texts[-1][-2500:]` / point_repair `tail_blob` —— 若误统一会改两处检测输入(point_repair 看不到末章开头 → FP 回归,有实证注释)。adapter 各传各的 tail。
- **`for-else` 等价**:produce 现状全失败→`ec={}`;point_repair 现状全失败→last `_safe_json or {}`(通常 {})。统一为 `return {}`——point_repair 在"末次畸形但前次返了无 ok 的部分 dict"极罕见情形下由 partial-dict 变 {};消费方只查 `skipped`/`ok`,partial-dict 无这些键时行为同 {},等价。
