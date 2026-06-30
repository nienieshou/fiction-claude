# 修 power 境界检测器(读错 bible 字段)实现计划 — 硬化 A

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修 `audit.py` power 境界检测器:读 `power_system`(非 `escalation_ladder`)+ 解析异构散文 + `_realm_rank`(default 优先/custom 仅补默认未知境界)→ 让 plan 层 `fix_power_monotonic` 预防对真境界梯(灵*)生效,且检测零退化、不误钉。

**Architecture:** 全在 `src/hiki/audit.py`:① 重写 `power_order_from_bible`(读+解析 power_system,`_NON_REALM` 过滤,<3→None);② 新纯助手 `_realm_rank`(default 优先,custom 兜底默认未知境界);③ `check_power_monotonic`/`fix_power_monotonic` 的 `_rank_fn` 改调 `_realm_rank`。`_power_rank`/`PowerLedger`/`ordinal_comparator`/`_POWER_ORDER` 不动。

**Tech Stack:** Python(stdlib re);pytest。无新依赖。

配套 spec:`docs/superpowers/specs/2026-06-30-power-realm-detector-fix-design.md`(codex rounds=3 approved,实跑 8 本真 bible 验证)。

## Global Constraints

- **只动 `src/hiki/audit.py` 的 power 部分** + 重 pin `tests/test_audit.py`、`tests/test_power_characterization.py`。不碰门/prose cross_check/建模/性别/共指/重复。
- **`_realm_rank` = default 优先**:`r=_power_rank(raw,_POWER_ORDER); if r>=0: return r; return _power_rank(raw,custom) if custom else -1`。默认梯能判的值一律走 default(同 index 空间,status quo 检测全保留);custom 只补 default 未知境界(灵*/散仙)。**绝不混 custom-local idx 与 default-global idx**。
- **`power_order_from_bible` 读 `power_system`**(非 escalation_ladder);`_NON_REALM=("传承","属性","体系","系统","境界","修炼","修为")` 过滤 provenance/标签词;首句/首梯截断;剥前缀/括注/"及以上";token 长 `1<len<=5`;**解析<3 干净境界→None**(退默认梯)。
- **fail-safe / 不误钉**(R13c"钉反=造伤"):解析失败→None→纯默认梯;junk custom 因其值走 default 从不被查。
- **不改** `_power_rank`/`PowerLedger`/`ordinal_comparator`/`_POWER_ORDER`(默认梯仍作回退源)。
- **回归网**:`tests/test_gold_regression.py`/`test_assembly_regression.py`/`test_power_ledger.py` 全绿(走 numeric cross_check + 冻结夹具 / 纯比较器,不涉本改 ordinal 路)。
- **提交** trailer:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EoVNZMK1aq3D44jknQ18bq
  ```

---

### Task 1: 重写 `power_order_from_bible`(读+解析 power_system)

**Files:**
- Modify: `src/hiki/audit.py`(`_POWER_ORDER` 旁加 `_NON_REALM`;重写 `power_order_from_bible`,现 ~255-261)
- Test: `tests/test_audit.py`(重 pin `test_power_order_from_bible`,现 ~71-73)

**Interfaces:**
- Consumes: 现有 `re`(audit.py 已 import)。
- Produces: `power_order_from_bible(bible) -> list[str]|None`(改读 `power_system`);`_NON_REALM: tuple[str,...]`。`_power_rank`/调用点不变(Task 2 才改 _rank_fn)。

- [ ] **Step 1: 重写失败测试**

`tests/test_audit.py` 把 `test_power_order_from_bible`(71-73)整体替换为:
```python
def test_power_order_from_bible():
    # 读 power_system(散文格式: 顿号 + (N阶) + 前缀 + 及以上)
    edge = {"power_system": "修炼境界：灵徒、灵师（1-9阶）、大灵师（1-9阶）、灵尊（1-9阶）、灵宗（1-9阶）、灵王（1-9阶）、灵圣（及以上）。灵力属性：火、冰。"}
    assert power_order_from_bible(edge) == ["灵徒", "灵师", "大灵师", "灵尊", "灵宗", "灵王", "灵圣"]
    # → 分隔的干净梯
    assert power_order_from_bible({"power_system": "灵者（1-3阶）→灵士→灵师→大灵师→灵尊"}) == ["灵者", "灵士", "灵师", "大灵师", "灵尊"]
    # 无修为体系 / 缺字段 → None(退默认梯)
    assert power_order_from_bible({"power_system": "无"}) is None
    assert power_order_from_bible({}) is None
    # provenance/标签词被 _NON_REALM 过滤; 干净境界<3 → None
    assert power_order_from_bible({"power_system": "修炼体系：丹武经传承，筑基（暂未现）"}) is None
    # 标签前缀(修炼境界:)剥; 真境界名前缀(灵徒)不被误剥(codex r1)
    assert power_order_from_bible({"power_system": "灵徒、灵师、灵尊、灵王"}) == ["灵徒", "灵师", "灵尊", "灵王"]
    # 逗号作首段边界 → 尾注'赌注升级'不混入
    assert power_order_from_bible({"power_system": "练气→筑基→金丹→元婴，赌注升级"}) == ["练气", "筑基", "金丹", "元婴"]
    # 不再误读剧情弧 escalation_ladder
    assert power_order_from_bible({"escalation_ladder": "练气→筑基→金丹，赌注…"}) is None
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_audit.py::test_power_order_from_bible -v`
Expected: FAIL — 旧码读 escalation_ladder:power_system 各例返 None≠期望;末例 escalation_ladder 旧码返 `["练气","筑基","金丹"]`≠None。

- [ ] **Step 3: 实现**

`src/hiki/audit.py`,在 `_POWER_ORDER = [...]`(~239)**之后**加:
```python
_NON_REALM = ("传承", "属性", "体系", "系统", "境界", "修炼", "修为")  # provenance/标签词, 非境界名
```
把 `power_order_from_bible`(~255-261)整体替换为:
```python
def power_order_from_bible(bible: dict) -> list[str] | None:
    """从 bible.power_system 尽力解析本书境界梯(灵徒→…→灵圣)。power_system 是异构散文
    ('修炼境界:灵徒、灵师(1-9阶)、…、灵圣(及以上)。…' / '灵者→灵士→…' / '无'):取首句首梯、
    剥前缀/括注/尾注、按顿号|→拆、过滤 provenance 词。<3 干净境界→None(调用方退默认梯;宁缺勿错)。"""
    raw = str((bible or {}).get("power_system") or "").strip()
    if not raw or raw in ("无", "—", "暂无"):
        return None
    head = re.split(r"[。;；，,]", raw)[0]                # 首段(到首个 句号/分号/逗号 边界, 切掉 '…，赌注升级' 类尾注)
    m = re.match(r"^([^:：]{0,8})[:：]", head)            # 仅剥**含标签词**的前缀(修炼境界:/修炼体系:),
    if m and any(w in m.group(1) for w in _NON_REALM):  # 不剥真境界名(灵徒:…)—— codex r1 修
        head = head[m.end():]
    stages = []
    for t in re.split(r"[、→>＞]+", head):                # 顿号/→ 拆境界(逗号已作首段边界)
        t = re.sub(r"[（(][^)）]*[)）]", "", t).strip()    # 剥括注 (1-9阶)/(及以上)
        t = t.replace("及以上", "").strip()
        if 1 < len(t) <= 5 and not any(w in t for w in _NON_REALM):
            stages.append(t)
    return stages if len(stages) >= 3 else None
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_audit.py::test_power_order_from_bible -v`
Expected: PASS。

- [ ] **Step 5: 回归 + 提交**

Run: `python -m pytest tests/test_audit.py tests/test_power_characterization.py -q`
Expected: 全 PASS —— test_power_characterization 的 `_bible()` 现用 escalation_ladder → 本函数改读 power_system → order=None → 退默认梯,而其夹具值(练气/筑基/金丹/元婴)**在默认梯内**,排序一致 → 检测不变,仍绿。
```bash
git add src/hiki/audit.py tests/test_audit.py
git commit -m "fix(power): power_order_from_bible 读+解析 power_system(非 escalation_ladder)+ _NON_REALM 过滤"
```

---

### Task 2: `_realm_rank`(default 优先)+ 接入 _rank_fn + 端到端 + 重 pin

**Files:**
- Modify: `src/hiki/audit.py`(`_power_rank` 后加 `_realm_rank`;`check_power_monotonic`/`fix_power_monotonic` 的 `_rank_fn` 改调 `_realm_rank`)
- Test: `tests/test_audit.py`(加 `_realm_rank` 单测 + 端到端);`tests/test_power_characterization.py`(`_bible`/`_bible_with_alias`/too-short 夹具 escalation_ladder→power_system)

**Interfaces:**
- Consumes: Task 1 的 `power_order_from_bible`(读 power_system);现有 `_power_rank`/`_POWER_ORDER`/`PowerLedger`/`ordinal_comparator`。
- Produces: `_realm_rank(raw: str, custom: list[str]|None) -> int`(default 优先);两检测函数对真境界梯生效。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_audit.py`(顶部 import 处补 `from hiki.audit import _realm_rank, check_power_monotonic`):
```python
def test_realm_rank_default_first():
    LING = ["灵徒", "灵师", "大灵师", "灵尊", "灵宗", "灵王", "灵圣"]
    # 默认梯未知境界(灵*)→ 用 custom
    assert _realm_rank("灵王巅峰", LING) == LING.index("灵王")
    assert _realm_rank("大灵师", LING) == LING.index("大灵师")   # 非子串"灵师"(earliest-pos)
    # 默认梯能判的值 → 走 default(custom 不查), 即使 custom 是默认境界子集
    sub = ["练气", "筑基", "金丹"]
    assert _realm_rank("练气中期", sub) == _power_rank("练气中期", _POWER_ORDER)
    # codex-r2 锁定: 练气(default1) vs 凡人(default0) 同空间 → 仍可判回退
    assert _realm_rank("练气", sub) > _realm_rank("凡人", sub)
    # 默认+custom 均判不出 → -1
    assert _realm_rank("莫名其妙", LING) == -1


def test_check_power_monotonic_detects_realm_regression_via_power_system():
    """bug 真修: 修仙 power_system(灵*)下, 灵王→灵师 回退被检出(修前默认梯无灵*→空)。"""
    bible = {"power_system": "修炼境界：灵徒、灵师、大灵师、灵尊、灵宗、灵王、灵圣。"}
    scenes = [{"power_after": [["云朝歌", "灵王巅峰"]]},
              {"power_after": [["云朝歌", "灵师"]]}]
    issues = check_power_monotonic(bible, scenes)
    assert any("云朝歌" in s and "回退" in s for s in issues)


def test_check_power_monotonic_subset_power_system_no_degrade():
    """power_system 只列默认境界子集(缺凡人)→ default 优先兜底, 凡人仍判 → 练气后退凡人被检出。"""
    bible = {"power_system": "练气、筑基、金丹"}
    scenes = [{"power_after": [["甲", "练气中期"]]},
              {"power_after": [["甲", "凡人"]]}]
    issues = check_power_monotonic(bible, scenes)
    assert any("甲" in s and "回退" in s for s in issues)
```
`_power_rank`/`_POWER_ORDER` 已在 test_audit.py import(Step 顶部确认;缺则补 `from hiki.audit import _power_rank, _POWER_ORDER`)。

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/test_audit.py -k "realm_rank or realm_regression or subset_power_system" -v`
Expected: FAIL — `_realm_rank` 不存在(ImportError/AttributeError);端到端测因 _rank_fn 仍用 `_power_rank(raw, order)`(subset 例 凡人在 custom -1→漏)。

- [ ] **Step 3: 实现**

`src/hiki/audit.py`,在 `_power_rank`(~242-252)**之后**加:
```python
def _realm_rank(raw: str, custom: list[str] | None) -> int:
    """default _POWER_ORDER 权威优先; 仅当 default 判不出(-1, 灵*/散仙等非默认境界)才用 custom。
    → 默认梯能判的值全在 default 空间一致比较(status quo 检测零退化); custom 只补默认未知境界。
    绝不混 custom-local idx 与 default-global idx 致漏判(codex r2)。"""
    r = _power_rank(raw, _POWER_ORDER)
    if r >= 0:
        return r
    return _power_rank(raw, custom) if custom else -1
```
在 `check_power_monotonic`(~295-314)与 `fix_power_monotonic`(~264-292)内,各把:
```python
    def _rank_fn(raw: str) -> float | None:
        r = _power_rank(raw, order)
        return float(r) if r >= 0 else None
```
改为:
```python
    def _rank_fn(raw: str) -> float | None:
        r = _realm_rank(raw, order)
        return float(r) if r >= 0 else None
```
(`order = power_order_from_bible(bible)` 不动;PowerLedger/钉回逻辑不动。)

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/test_audit.py -v`
Expected: PASS(含 3 新测)。

- [ ] **Step 5: 重 pin test_power_characterization 夹具到 power_system**

`tests/test_power_characterization.py`:把 `_bible`(~23-25)的 `{"escalation_ladder": ladder}` 改为 `{"power_system": ladder}`;`_bible_with_alias`(~28-)里 `"escalation_ladder": "练气→筑基→金丹→元婴，赌注升级"` 改键为 `"power_system"`;`test_check_power_monotonic_default_ladder_when_bible_too_short`(~113)的 `{"escalation_ladder": "练气→筑基，其他"}` 改为 `{"power_system": "练气→筑基，其他"}`。
(夹具值仍是默认境界 练气/筑基/金丹/元婴 → `_realm_rank` 走 default → 排序/检测与原一致 → 全测保持绿,且现真正经 power_system 路径。)

- [ ] **Step 6: 跑确认通过**

Run: `python -m pytest tests/test_power_characterization.py -v`
Expected: 全 PASS(行为不变,改走 power_system)。

- [ ] **Step 7: 回归网 + 全量 + 提交**

Run: `python -m pytest tests/test_audit.py tests/test_power_characterization.py tests/test_power_ledger.py tests/test_gold_regression.py tests/test_assembly_regression.py -q`
Expected: 全 PASS(金标/装配/power_ledger 不涉本改 ordinal 路 → 平凡绿)。

Run: `python -m pytest -m "not api" -q`
Expected: 全绿;报确切 passed/deselected。
```bash
git add src/hiki/audit.py tests/test_audit.py tests/test_power_characterization.py
git commit -m "fix(power): _realm_rank default优先/custom补默认未知境界 + 接入 check/fix _rank_fn(灵*检出/不退化/不误钉)"
```

---

## Self-Review

**1. Spec 覆盖:** power_order_from_bible 读+解析 power_system + _NON_REALM=Task1✅;`_realm_rank` default 优先=Task2 Step3✅;接入 check/fix _rank_fn=Task2 Step3✅;灵* 检出端到端=Task2(detects_realm_regression)✅;subset 不退化(codex-r2)=Task2(subset_power_system + realm_rank_default_first)✅;不误钉(_NON_REALM/default 优先)=Task1 过滤 + Task2 default 优先✅;重 pin test_audit=Task1 Step1、test_power_characterization=Task2 Step5✅;金标/装配/power_ledger 网绿=Task2 Step7✅;非目标(不加门信号/不改 _power_rank/_POWER_ORDER/PowerLedger)=计划无相关改动✅。

**2. 占位扫描:** 无 TBD;每 code step 全代码;命令具体;重 pin 给精确字段/行锚。✅

**3. 类型一致:** `power_order_from_bible(bible)->list|None`(T1)与 T2 `order=power_order_from_bible(bible)` 一致;`_realm_rank(raw, custom)->int`(T2 定义)与两 `_rank_fn` 调用一致;`_NON_REALM`(T1)仅 power_order_from_bible 用;`_POWER_ORDER`/`_power_rank`(现有)在 `_realm_rank` 内用,签名不变。✅

<!-- codex-peer-reviewed: 2026-06-30T04:32:09Z rounds=2 verdict=approved -->
