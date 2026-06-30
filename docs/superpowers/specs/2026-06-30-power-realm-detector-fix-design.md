# 修 power 境界检测器读错 bible 字段(Stage-0 假阳头号根因)设计 — 硬化 A

> 2026-06-30 · Stage-0 系统测试诊断的头号召回缺口。`power_order_from_bible` 读 `escalation_ladder`(剧情弧)而非 `power_system`(境界梯)→ 中文境界全 parse 失败 → plan 层修为预防 `fix_power_monotonic` 从不生效 → 边缘书境界乱序/修为倒退漏检。范围 = **硬化 A**(只动 audit.py power;codex 评审揭示 power_system 是异构散文,naive parse 会退化/误钉,故加 default-回退安全网)。基于 `master`。配套 `docs/design/e3-stage0-system-test.md` #1 诊断。

## 根因 + codex 揭示的复杂度(已核实 8 本真 bible)
1. `audit.py:255` 读错字段(escalation_ladder vs power_system)。
2. `power_system` **无 schema,高度异构**:
   - 干净境界列:`灵徒、灵师(1-9阶)…灵圣`(stage0_edge)、`灵者(1-3阶)→灵士→…`(CPBGX00192)
   - `"无"`(言情/种田 4 本,无修为体系)
   - 前缀+provenance:`修炼体系:丹武经传承,炼精化气、练气期(前/中/后)、筑基`(BPBXS00052)
   - 多梯 `；`:`散仙境界:散仙→…；圣人境界:…`(CPBGX00056)
   - 散文内嵌(CPBXN00188)
3. **naive 解析会退化**:BPBXS00052 解析出 `[丹武经传承,练气期,筑基]` —— ① 漏匹配 plan 的"练气中期/后期"(custom 独占会**压制**默认梯本能抓的"练气")② 含 provenance token → 理论 wrong-pin(R13c"钉反=主动造伤")。

## 目标 / 范围(硬化 A)
修 audit.py power **检测召回**,使 plan 层 `fix_power_monotonic`(预防)与 advisory `check_power_monotonic` 对真境界梯生效,**且绝不退化默认梯已有的检测、绝不误钉**。安全网 = **custom 梯只增不减覆盖**(default 始终逐值兜底)。不加门信号(prose 序数门检 = #2/B)。

## 架构(audit.py 内,3 处)

### 1) `power_order_from_bible` 改读+解析 power_system(尽力而为)
```python
_NON_REALM = ("传承", "属性", "体系", "系统", "境界", "修炼", "修为")  # provenance/标签词, 非境界

def power_order_from_bible(bible: dict) -> list[str] | None:
    """从 bible.power_system 尽力解析境界梯。异构散文(顿号/→/；分隔, (N阶)括注, 前缀)→ 尽力抽;
    抽不出≥3 干净境界 → None(退默认梯)。安全靠调用侧 default 回退, 不靠完美解析。"""
    raw = str((bible or {}).get("power_system") or "").strip()
    if not raw or raw in ("无", "—", "暂无"):
        return None
    head = re.split(r"[。;；]", raw)[0]                  # 首句/首梯(多梯只取第一段)
    head = re.sub(r"^[^:：]{0,8}[:：]", "", head)         # 剥"修炼境界:"类前缀(冒号前≤8字)
    stages = []
    for t in re.split(r"[、,，→>＞]+", head):
        t = re.sub(r"[（(][^)）]*[)）]", "", t).strip()    # 剥括注 (1-9阶)/(及以上)
        t = t.replace("及以上", "").strip()
        if 1 < len(t) <= 5 and not any(w in t for w in _NON_REALM):  # 过滤 provenance/标签词
            stages.append(t)
    return stages if len(stages) >= 3 else None
```

### 2) `_realm_rank(raw, custom)` 新纯助手 —— default 优先, custom 仅补默认未知境界(安全网核心)
```python
def _realm_rank(raw: str, custom: list[str] | None) -> int:
    """default _POWER_ORDER 权威优先; 仅当 default 判不出(-1, 如 灵*/散仙等非默认境界)才用 custom。
    → 默认梯能判的值(凡人/练气/筑基/金丹…)一律走 default(同一 index 空间, status quo 检测全保留);
    custom 只为 default 未知的境界系增覆盖。绝不混 custom-local idx 与 default-global idx 致漏判。"""
    r = _power_rank(raw, _POWER_ORDER)
    if r >= 0:
        return r
    return _power_rank(raw, custom) if custom else -1
```
> **为何 default 优先(codex r2 修正)**:custom-local 与 default-global 是**不同 index 空间**,逐值混用会漏判(例:custom`[练气,筑基,金丹]` 下 `练气`=0、回退 `凡人`=0 → `练气→凡人` 漏检,而纯 default 1→0 能检)。default 优先 → 默认梯可判的值全在 default 空间一致比较(检测零退化);灵* 书所有值 default 均 -1 → 全走 custom(同一 custom 空间一致);一书一体系 → 不跨空间。junk custom 梯(BPBXS00052)因其值(练气/筑基)走 default → **从不被查询** → 误钉风险一并消除。

### 3) `check_power_monotonic` + `fix_power_monotonic` 的 `_rank_fn` 改用 `_realm_rank`
两函数内 `order = power_order_from_bible(bible)` 保留;`_rank_fn` 由 `_power_rank(raw, order)` 改为 `_realm_rank(raw, order)`:
```python
    def _rank_fn(raw: str) -> float | None:
        r = _realm_rank(raw, order)
        return float(r) if r >= 0 else None
```
其余(PowerLedger/ordinal_comparator/_alias_map/钉回逻辑)不变。

**安全论证(default 优先)**:默认梯能判的值(凡人/练气/筑基/金丹…)一律走 default、在同一 index 空间一致比较 → **status quo 检测 0 退化**(此即 codex #1/#2 的根治)。custom 仅在 default 判不出(灵*/散仙等)时查询 → 灵* 书全值走 custom(同空间一致),练气书全值走 default。junk custom 梯(BPBXS00052)其值走 default → 从不被查 → 不误钉。一书一体系 → 不跨空间。解析<3级→None→纯默认梯(=status quo)。

## 验证
- **`power_order_from_bible` 单测**(`tests/test_audit.py` 改/补):
  - stage0_edge 式 `灵徒、灵师(1-9阶)…灵圣` → `["灵徒","灵师","大灵师","灵尊","灵宗","灵王","灵圣"]`(7级,顺序对)。
  - CPBGX00192 式 `灵者(1-3阶)→灵士→灵师→…` → 干净梯。
  - `"无"`→None;缺字段→None;BPBXS00052 式 `丹武经传承,炼精化气、练气期、筑基` → `丹武经传承` 被 `_NON_REALM` 剔(含"传承")→ 余 `[炼精化气,练气期,筑基]`(注:仍可能含非理想 token,但下条 default 回退保安全)。
  - 只有 escalation_ladder 无 power_system → None(不再误读剧情弧)。
- **`_realm_rank` 单测**(default 优先):`_realm_rank("灵王", 灵梯)` → default -1 → custom 灵王idx;`_realm_rank("大灵师",灵梯)`→custom 大灵师idx(非子串"灵师");`_realm_rank("练气中期", 灵梯)` → **default 直接命中"练气"**(custom 不查);`_realm_rank("练气中期", None)`→default 命中。**codex-r2 锁定例**:`_realm_rank("凡人", ["练气","筑基","金丹"])`=default 凡人 idx0、`_realm_rank("练气", 同custom)`=default idx1 → 故 `练气→凡人` 仍判回退(1→0),custom 不压制 default。
- **端到端载重测**:合成 bible(power_system=灵梯)+ scenes(power_after 灵王→灵师)→ `check_power_monotonic` **现检出回退**(修前默认梯无灵*→空)= 证 bug 真修。另:bible(power_system=BPBXS00052式)+ scenes(练气中期→练气后期→筑基 正常递进)→ **不误钉**(default 兜底,无 regression);scenes(筑基→练气 真回退)→ 检出。
- **重 pin** `tests/test_power_characterization.py` `_bible()` 夹具(escalation_ladder→power_system)+ 受影响断言(改钉正确行为)。
- **金标/装配回归网绿**(走 numeric cross_check + 冻结夹具,不涉 ordinal;Explore 确认)。`tests/test_power_ledger.py` 不受影响。
- 全量 `pytest -m 'not api'` 绿,报确切 passed/deselected。SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- **不**加 prose cross_check 序数门检 / 新门信号(#2/B)。
- **不**改 `_power_rank`/`PowerLedger`/`ordinal_comparator`/`_POWER_ORDER`(默认梯)。
- **不**追求完美解析异构 power_system —— 解析失败→default 兜底即安全(检测不退化)。
- **不**碰性别/共指/语义重复(#2 其余);不重跑金标书/不动冻结夹具。

## 风险
- **行为改变(有意)**:境界书 `fix_power_monotonic` 现钉回 plan 境界回退 → 草稿更净(Stage-0 假阳对症)。言情(power_system="无")→None→纯默认梯→行为不变。
- **检测不退化(安全网, default 优先)**:default 权威优先 → 默认梯本能判的值全在 default 空间一致判,custom 只补 default 未知境界。根治 codex #1(混 index 空间致漏判)+ #2(junk custom 因值走 default 从不被查→不误钉)。
- **误钉**:`_NON_REALM` 过滤 provenance token + default 优先(junk custom 不被查)+ "解析<3→None" → wrong-pin≈0。沿用 R13c"钉反=造伤"红线。
- **跨体系混书(degenerate)**:一书同时用 default 境界 + 灵* → 两值跨 index 空间,理论可误判;但单本混两套修为体系极罕见/本身设定崩,接受为已知边界。
- **多梯/内嵌散文**(CPBGX00056 `；`多梯 / CPBXN00188 内嵌):首句/首梯截断 → 取第一梯或 None → 安全退化(default 兜底),非误钉。
- **A 边界(诚实)**:A 在 plan 层预防;drafting 新引入(plan 没有)的境界乱序 A 不拦、门也不拦 → 需 #2/B 的 prose 序数门检。Stage-0 边缘书乱序主源是 plan 账(hfl 实证)→ A 对症,残留推 #2/B。

<!-- codex-peer-reviewed: 2026-06-30T04:09:39Z rounds=3 verdict=approved -->
