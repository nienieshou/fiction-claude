# C2 修为 PowerLedger 设计

> 2026-06-27 · 技术债 C2(检测器 sprawl,接 C1 之后)。范围:**仅修为单调合并**(2 引擎→可插拔比较器 PowerLedger)。
> 基于分支 `feat/c1-revival-ledger`(PowerLedger 与 RevivalLedger 同住 `char_ledger.py`,长成 CharacterStateLedger)。
> 配套:`docs/design/tech-debt.md`(C 类登记)、`docs/design/techdebt-sweep-roadmap.md`。

## 目标

把"修为/战力单调"的 **2 套引擎**(audit 序数阶梯 on plan / prose_facts 数值-5% on cross_check)收口为**一个可插拔比较器的 `PowerLedger`**;两引擎 + 修复函数变薄 adapter。

**风险姿态:行为保持**——纯债务消减,**零产品变化**,输出逐位等价,characterization 网证等价。principled 改判留 follow-up。两引擎**都不是硬门**(维5 advisory;cross_check power 的 `conf="中"` 数值不入 `spine_net_num`),故无金标信号牵连,风险低于 C1 的 P2。

## 现状(已核实的合并目标)

### 引擎 1 — `audit.py`(序数,plan 层)
- `check_power_monotonic(bible, scenes) -> list[str]`(`audit.py:283-301`):`order = power_order_from_bible(bible)`(解析 bible.escalation_ladder,<3级退默认梯);`_power_rank(pw, order)` 取序数;`cur[who]` 追 max rank;`r < cur[who]` → `"场景{i}: 「{who}」修为回退到{pw}(战力崩坏)"`;每值后 `cur[who]=max(cur,r)`。
- `fix_power_monotonic(bible, scenes) -> list[str]`(`audit.py:254-280`):同序数判据,但回退时把 `sc["power_after"]` 的该值**就地钉回** `cur` 的当前最高串 `cs`,产 `"场景{i}:{who} {p}→{cs}"`;非回退才 `cur[who]=(r,p)`。**会改写 scenes。**
- 输入:plan `scenes[i]["power_after"] = [[who, 境界串], ...]`(定性)。
- 维5 = **advisory**(在 `audit_struct` 但不入 `ship_signals`)。

### 引擎 2 — `prose_facts.cross_check` power 段(数值,prose 层)
- `prose_facts.py:112-133`:`powers[(who, unit)]` 收 `(ch, value)`,unit=`_NUM.sub("#", val)`,value=`_num_of(val)`;按 ch 排序,`v < hi*0.95`(>5%跌)→ `{cat:"数值", who, ch_a, ch_b, why:"...倒退", conf:"中"}`;`hi` 追 max。
- 输入:prose 逐章 LLM 抽取的 `power: [[who, 值串], ...]`。
- `conf="中"` 数值**不入** `spine_net_num`(`= sum(cat=="数值" and conf=="低")`),故**不 gating**;喂 `_fact_audit_repair` 的 POWER_VERIFY+POINT_REPAIR(advisory/修复)。

### 共享骨架(consolidation 依据)
两引擎都是:**per-key 追 running-max;新值 parse 出后若低于阈值(序数:严格<;数值:<95%)即标回退;best 更新为 max**。差异全在 **key / parse / 阈值** → 可插拔比较器。

## 架构

### 模块与数据模型
`src/hiki/char_ledger.py` 追加(与 RevivalLedger 并存,纯/零 LLM/IO):
```python
@dataclass(frozen=True)
class PowerRegression:
    who: str
    ch: int
    raw_value: str        # 触发回退的原始值串
    best_raw: str         # 当时 running-best 的原始串(供修复钉回)
    mode: str             # "ordinal" | "numeric"

class PowerLedger:
    def __init__(self, comparator): ...
    def record(self, who: str, raw_value: str, ch: int) -> bool  # 返回 True 当且仅当此值相对当前 best 回退
    def regressions(self) -> list[PowerRegression]     # 累积的回退列表(确定性,记录顺序)
    def current_best(self, who: str, raw_value: str = "") -> str | None  # 该 key 的当前最高原始串
```
`record` 返回 bool 解决修复 adapter 的交错需求:`fix_power_monotonic` 逐值 `record`,**若返回 True 即就地把场景值钉回 `current_best`**(回退时 best 不变,因 new<best→max 保持 best,故 record 后 current_best 即运行最高);检测 adapter(`check_power_monotonic`)可用返回值或 `regressions()` 产 issue。`current_best` 仅修复(序数,key=who)用;数值无修复,不调它。

### 可插拔比较器(C2 核心)
比较器三元接口(纯函数式,可用小类或 namedtuple-of-callables):
```
key(who: str, raw: str) -> Hashable          # 分桶键
parse(raw: str) -> float | None              # 可比量; None=解析不出→record 跳过(不报不更新)
is_regression(new: float, best: float) -> bool
```
两实现:
- `OrdinalComparator(order)`:`key=who`;`parse=lambda raw: _power_rank(raw, order) (返回 -1 时视作 None 跳过)`;`is_regression = new < best`。
- `NumericComparator()`:`key=(who, _NUM.sub("#", raw))`;`parse=_num_of`;`is_regression = new < best * 0.95`。

`PowerLedger.record` 通用骨架:
```
k = cmp.key(who, raw); v = cmp.parse(raw)
if v is None: return
best = self._best.get(k)         # (value, raw)
if best is not None and cmp.is_regression(v, best.value):
    self._regressions.append(PowerRegression(who, ch, raw, best.raw, self._mode))
if best is None or v > best.value:
    self._best[k] = Best(v, raw)
```
`current_best(who, raw)` = `self._best.get(cmp.key(who, raw)).raw`。

### Adapter(2 引擎 + 修复变薄,输出逐位等价)
- **`check_power_monotonic`** → `PowerLedger(OrdinalComparator(order))`;逐 `power_after` 值 `record`;由 `regressions()` 产出 `"场景{i}: 「{who}」修为回退到{pw}(战力崩坏)"` 串(用 alias 映射保持)。
- **`fix_power_monotonic`** → 同 ledger 检测;adapter **自己**遍历 scenes,遇 ledger 标记的回退值时把 `sc["power_after"]` 钉回 `current_best`,产 `"场景{i}:{who} {p}→{cs}"`。**scenes 改写、alias、`_str_pair` 提取留在 adapter,ledger 不碰 scenes。**
- **`cross_check` power 段** → `PowerLedger(NumericComparator())`;产 `{cat:"数值",conf:"中",...}` finding 逐位不变(why 串、ch_a/ch_b 用现状格式)。
- `produce.py`、门、LLM 步、`_fact_audit_repair` 流程**不动**。

## 验证与特征化

两引擎已有部分测试(`test_audit` / `test_prose_facts` `test_cross_check_power_regression_conf_medium` / `test_cross_check_corpus` power 用例)。迁移前:
1. `tests/test_power_ledger.py`:PowerLedger + 两比较器纯函数语料(序数退/数值5%边界/unit 分桶/parse-None 跳过/current_best)。
2. 确认/补 `check_power_monotonic` + `fix_power_monotonic` 的 characterization(尤其 **fix 的 scene-mutation** 前后逐位一致、rank 判不出跳过、equal-rank 不报、alias 映射)。fix 当前若无专测则**迁移前先补**(同 C1 P1/P3"无网先补网")。
3. 等价闸:上述 + `cross_check_corpus` power + 全量 `pytest` 绿;`produce.py` 默认管线行为等价。
4. SDD 纪律:逐任务 TDD + 两段复核 + opus 终审;项间网守。

## 非目标(本 spec 明确不做)
- C1(已 PR #8)/ C3 身份 / C5 name 谓词 / A3 schema。
- principled 改判(用比较器改阈值/判据修当前误判)——留 follow-up。
- 门阈值、LLM 步、`power_order_from_bible` 解析逻辑改动。

## 风险
- **比较器 None 语义**:序数 `_power_rank` 返回 `-1` 表示判不出 → 比较器 parse 必须映射为 `None`(record 跳过),复现现状"rank<0 continue"。错映射会误报/漏报。
- **fix_power_monotonic 的 scene-mutation 必须逐位一致**:钉回的串、跳过非回退的 `cur` 更新、`new` 列表重建顺序——characterization 必须覆盖,这是最易漂移处。
- numeric 的 `(who, unit)` 复合键:unit 派生自值串(`_NUM.sub("#",raw)`),比较器 `key` 依赖 raw,record 调用处须传原始串。
