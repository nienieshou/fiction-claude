# A3 wave 3 — seam/adj_dup/handshake/ending 共享检测环 + fail-closed 浮现 设计

> 2026-06-28 · 技术债 A3 第三波(接 A3.1 / wave2)。范围:**seam / adj_dup / handshake 三检 + 顺收 ending_check** 的共享检测环。
> 基于:`master`(独立)。配套:`docs/design/tech-debt.md` A3/A1/C7 行、C7.1 spec(`gate.ending_check` 来源)。

## 目标(双赢)

1. **A3 加固**:`produce` 的 seam/adj_dup/handshake 三个检测 pass(及 `gate.ending_check`)在 LLM 重试耗尽时**静默当"衔接正常/无重演/无收尾问题"**(Class B 静默假阴)。改成 validate→retry→**stderr 浮现**"该对按未检出计(可能漏检)"。
2. **C 去重**:四处**几乎逐字相同**的 3-retry 检测环(`for t in range(3): cli.complete(...); r=_safe_json(raw) or {}; if key in r: return r; return {}`)收进**一个** `gate.detect_retry`,消检测器 sprawl,且避免"新建一个与 `ending_check` 并行的第二个共享环"(那反而是新 sprawl)。

**风险姿态(同 wave2):happy-path 逐位保持,失败路径有意 fail-closed(仅 stderr 浮现,不改任何计数/返回元组/门信号)。**

## 现状(已核实,master)

四处检测环结构同款,差异仅 (prompt 形状, 判定 key, max_tokens):

| 处 | 位置 | key | max_tokens | isinstance 守卫 | 失败 → |
|---|---|---|---|---|---|
| seam | `produce.py:154` `_seam_pass._check(i)` | `"ok"` | 400 | 无 | `{}` → `r.get("ok") is False` 假,不入 bad → **静默当衔接正常** |
| adj_dup | `produce.py:218` `_adj_dup_pass._check(i)` | `"dup"` | 300 | **有** | `{}` → `r.get("dup") is True` 假,不入 bad → **静默当无重演** |
| handshake | `produce.py:732` `_handshake_pass._check(j)` | `"ok"` | 300 | 无 | `{}` → 不入 bad → **静默当衔接正常**(`HIKI_HANDSHAKE=1` 才启,默认关) |
| ending | `gate.py:119` `ending_check` | `"ok"` | 400 | 无 | `{}` → 消费方 `ec.get("ok")`/`ec.get("skipped")` 全假 → **静默当无收尾问题** |

- 四处温度斜坡均 `0.1 + 0.1 * t`、`retries=3`、stage 均 `"chunk_extract"`、`json_mode=True`。
- `_safe_json` 返 `dict | list | None`;`or {}` 把 None 兜成 `{}`。
- ending_check 由 `produce._ending_guard` + `point_repair.run` 两处 call(C7.1 已抽),消费 `ec.get("ok")`/`ec.get("skipped")`。

## 架构

### ① 新增共享 helper(家:`gate.py`,与 `ending_check`/`continuity_check` 同列 LLM 门检测)
```python
async def detect_retry(cli: Client, sys_p: str, usr: str, key: str, *,
                       max_tokens: int, label: str, retries: int = 3) -> dict:
    """共享 LLM 检测环(N-retry-on-empty)。seam/adj_dup/handshake/ending 四处 call。
    成功 = 解析出 dict 且含 key(各契约判定键 "ok"/"dup")→ 返该 dict。
    retries 次仍无 → stderr 浮现(label 标 pass+对) + 返 {}(调用方按"未检出"消费,同现状保守不误修)。
    调用方各自 format usr(prompt 形状各异),传自己的 key/max_tokens/label。"""
    for t in range(retries):
        raw = await cli.complete("chunk_extract", sys_p, usr,
                                 json_mode=True, max_tokens=max_tokens, temperature=0.1 + 0.1 * t)
        r = _safe_json(raw) or {}
        if isinstance(r, dict) and key in r:
            return r
    print(f'⚠ {label} 校验重试{retries}次仍无效,按"未检出"计(可能漏检)', file=sys.stderr)
    return {}
```
- 加 `import sys`(gate.py 现无)。
- 温度斜坡 `0.1+0.1*t`、`retries=3` 默认 = 四处现状,逐位一致。

### ② `ending_check` 改委托(收编,顺修其同款静默 bug)
```python
async def ending_check(cli: Client, prev_tail: str, tail: str) -> dict:
    """ENDING_CHECK 检测,委托 detect_retry。供 produce._ending_guard + point_repair 两处 call。"""
    sys_ec, usr_ec = prompts.ENDING_CHECK
    return await detect_retry(cli, sys_ec, usr_ec.format(prev_tail=prev_tail, tail=tail),
                              "ok", max_tokens=400, label="ENDING_CHECK")
```
消费方(`ec.get("ok")`/`ec.get("skipped")`)逐字不变;新增 stderr 浮现修其静默 bug。

### ③ 三检 `_check` 闭包改调(`produce.py`)
- **seam** `_check(i)`:
  ```python
  return await gate.detect_retry(
      cli, sys_c, usr_c.format(prev=ch_texts[i-1][-700:], head=ch_texts[i][:900]),
      "ok", max_tokens=400, label=f"SEAM 第{i+1}章")
  ```
- **adj_dup** `_check(i)`:
  ```python
  return await gate.detect_retry(
      cli, sys_c, usr_c.format(prev=ch_texts[i-1][-1800:], head=ch_texts[i][:2200]),
      "dup", max_tokens=300, label=f"ADJ_DUP 第{i+1}章")
  ```
- **handshake** `_check(j)`:保留 `prev/cur/sc0/brief` 计算行,
  ```python
  return await gate.detect_retry(
      cli, sys_h, usr_h.format(prev_exit=prev.get("exit_state") or "（未知）",
                               hook=prev.get("end_hook") or "（无）",
                               start=cur.get("start_state") or "（未填）",
                               brief=brief or "（无）"),
      "ok", max_tokens=300, label=f"HANDSHAKE 第{j+1}章")
  ```
下游(`r.get("ok") is False`→bad / `r.get("dup") is True`→bad / 回读复检 `_check` 复用)**逐字不变**。

### 一个有意的微差(诚实标注)
seam & handshake 经 `detect_retry` 新获 `isinstance(r, dict)` 守卫(adj_dup 现已有、原 ending 无)。dict 响应上**完全透明**;仅当 `_safe_json` 返非 dict(list)且 `key` 作其成员存在时行为变——极罕见且严格更安全(JSON list 非合法检测结果,旧码 `"ok" in [...]` 走元素成员判定属偶然)。同 C7.1 标注 for-else 等价的方式记录。

**更强的正确性论据(opus 终审补)**:旧码该路径不仅是"静默放过"——`"ok" in [...]` 为真时旧码**返回该 list**,下游 `r.get("ok")` 对 list 调 `.get` → **AttributeError 沿 gather 抛出 → 整跑 abort**。新守卫把这个潜在崩溃转成有文档的保守 `{}`(+ stderr)。故微差是修复一个潜在崩溃,非仅治静默;happy-path(dict)永不触及,金标/装配网零影响。

## 验证

- 新 `tests/test_detect_retry.py`(mock cli):含 key 的 dict → 返(1 调用);先畸形后有效 → 重试到有效;全畸形 → `{}` + stderr 浮现(capsys)+ N 调用;key/max_tokens/温度斜坡(0.1/0.2/0.3)透传;isinstance 守卫(list 响应 → 重试不误返)。
- `ending_check`:现 5 测(`tests/test_ending_check.py`)保持绿 + 加"全畸形 → stderr 浮现"断言。
- 三检:既有 `tests/test_stages.py`/`tests/test_produce_units.py` 绿(happy 逐位不变);加一焦点测——某 pass 喂 2 章 + 全畸形检测响应 → stderr 浮现 + 不误修。
- **金标 + 装配回归网全绿**:happy 逐位 → 门信号向量零变化;失败路径仅加 stderr,网兜不到 → 自然绿。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- `gate.continuity_check`(2-retry、返 `{"consistent": None, "issues":[...]}` 哨兵、形不同)、其余 Class A/B 契约(`reduce_bible`/`_plan_macro`/`fact_audit`/`extract_facts` 等)—— 不在本波。
- 不搬 `_safe_json`。不改下游修复/采用守卫/回读复检/门信号/返回元组。
- 不做 A1 的"checked-vs-unknown 进 ship 信号"(浮现层够本波;门计 unknown 改信号向量 = 非行为保持,归后续)。

## 风险
- **共享 helper 参数化**:四处 prompt 形状/key/max_tokens 各异,由调用方 format usr + 传 key/max_tokens/label;温度斜坡与 retries 默认硬编进 helper(= 四处现状),不暴露以防漂移。
- **收编 ending_check 动 C7.1 已上线码**:其 5 测 + 两调用方(produce/point_repair)守不退化;委托后 happy 逐位、仅加 stderr。
- **isinstance 守卫微差**:见上,dict happy 透明,严格更安全,显式标注。
- **happy-path**:四处正常返回(含 key 的 dict)时行为同原(1 次调用、同 prompt/温度/max_tokens),门信号零变化。
