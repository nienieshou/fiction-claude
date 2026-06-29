# C7 余切 — 复活候选提取单源化 设计

> 2026-06-29 · 技术债 C7(检测器/连续性逻辑去重)余切。接 C7.1(共享 ending_check)、C1(RevivalLedger)、C2(PowerLedger)。基于:`master`。配套:`docs/design/tech-debt.md` C7 行。

## 背景(已核实,master)

生死类 finding → 复活候选(`cand`)的列表推导在两个入口**逐字重复**:

`produce._fact_audit_repair`(`produce.py:1068-1071`):
```python
        cand = [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
                 "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
                for f in ft["findings"] if f.get("cat") == "生死"
                and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(ch_texts)]
```
`point_repair._verified_revivals`(`point_repair.py:62-65`):
```python
    cand = [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
             "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
            for f in ft["findings"] if f.get("cat") == "生死"
            and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(chs)]
```
两者仅 `len(ch_texts)` vs `len(chs)` 之差,其余逐字同。承重过滤(`cat=="生死"` + `ch_b` 边界 + `revive_ch`/`death_ch` 0-based 转换)在两处各抄一份 → 易静默漂移(grep 实证仅此 2 处有该提取推导;其余 `revive_ch`/`death_ch` 命中均为 cand 的下游消费者或 `RevivalRecord` dataclass,非第三份)。

`prose_facts.py` 已有同类纯函数 `signal_counts_from_fact_table(ft)`(`:185`,findings→派生 dict)且构造这些 findings(`:113`)、owns `fact_table_audit` —— 是该提取器的天然单源宿主。两调用文件均已 `import ... prose_facts`(各自用 `prose_facts.fact_table_audit`)。

## 目标

把重复的复活候选提取抽成 `prose_facts` 的一个纯函数,两站点共用。**行为逐位保持**(逐字推导移入函数,零行为改动)。

**风险姿态**:纯重构, 字节等价;无门/序列/字段变动。

## 架构

### 单源纯函数(`prose_facts.py`,置于 `signal_counts_from_fact_table` 一带)

```python
def revival_candidates(findings: list[dict], n_ch: int) -> list[dict]:
    """从 fact_table findings 取生死类 → 复活候选(who/clue/revive_ch 0-based/death_ch 0-based|None)。
    单源: produce._fact_audit_repair 与 point_repair._verified_revivals 共用(曾逐字重复)。"""
    return [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
             "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
            for f in findings if f.get("cat") == "生死"
            and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= n_ch]
```

### 两站点改调用(字节等价)

- `produce.py:1068-1071` → `cand = prose_facts.revival_candidates(ft["findings"], len(ch_texts))`
- `point_repair.py:62-65` → `cand = prose_facts.revival_candidates(ft["findings"], len(chs))`

(均已 import prose_facts;无新 import。下游 `if cand:` / `verify_revivals(...)` 不动。)

### 范围 nuance(刻意保留)

仅抽**候选推导**,不抽整条 `fact_table_audit → cand → verify_revivals` 序列:`produce._fact_audit_repair` 复用其 `ft` 结果于 spine-net / `fact_adv` / 落盘(`fact_table.json`),若把 `fact_table_audit` 调用也包进 helper,produce 会**二次审计**(行为/成本变更)。故 `point_repair` 的独立 audit+verify 序列保持,仅候选提取走单源。

## 验证

- **纯函数单测**(新 `tests/test_revival_candidates.py`):
  - 生死类 + `ch_b` 合界 → 一条候选,`revive_ch==ch_b-1`、`death_ch==ch_a-1`。
  - 非生死类(数值/身份/体系/时间轴)→ 排除。
  - `ch_b` 越界(0 或 >n_ch)/非 int → 排除。
  - `ch_a` 非 int(缺/None)→ `death_ch is None`(但仍入候选)。
  - `clue` = `why[:30]` 截断;`why` 缺 → `""`。
- **金标/装配回归网绿**:覆盖 `produce` 路 → `cand` 字节等价 → `ft_deaths_verified`/`事实表生死_verify后` 信号不变。
- `point_repair` 提取逐字等价(非网覆盖,靠字节等价论证 + 单测)。
- 全量 `pytest -m 'not api'` 绿,报确切 passed/deselected。
- SDD:单任务 TDD + 两段复核 + opus 终审。

## 非目标

- **不动** audit/verify/repair 序列、候选字段名、`verify_revivals`/`verify_revival_beats`/`repair_revivals_smart`。
- **不折叠** `fact_table_audit` 调用进 helper(会双审计 produce)。
- 不碰 `audit.check_revival`(plan 元数据,非 prose)、`prose_continuity.find_revivals`(prose roster,另路)、`RevivalRecord`(char_ledger)。
- 不加 config/门信号。不改 B1 god-function 其余(另案)。

## 风险

- **纯重构字节等价**:逐字推导移入纯函数,两站点调用结果与原 inline 逐位同;金标/装配网守 produce 路。
- **`n_ch` 参数语义**:原 `len(ch_texts)`/`len(chs)` 即章数上界,helper 的 `n_ch` 同义;边界 `1 <= ch_b <= n_ch` 表达式逐字保留。
- **宿主选择**:`prose_facts`(findings 的生产者 + `signal_counts_from_fact_table` 同类纯函数邻居),非 `prose_continuity`(消费侧)——避免 produce/point_repair 对 continuity 的额外耦合,且 findings→派生纯函数同源聚拢。
