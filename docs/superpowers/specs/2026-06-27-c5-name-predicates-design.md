# C5 name 谓词单源 设计

> 2026-06-27 · 技术债 C5(检测器 sprawl)。范围:**仅人名/物品长度谓词集中化**(行为保持)。
> 基于分支:`master`(独立,不依赖 C1/C2)。配套:`docs/design/tech-debt.md`、`docs/design/techdebt-sweep-roadmap.md`。

## 目标

把散落 7 处的 `2 <= len(name) <= N` 人名/物品长度判定收口为单源谓词 `src/hiki/names.py`,**行为逐位保持**。各站点的界值(4/5/6/8)经参数显式可见 —— 把"人名界 2-6 vs 2-5 分叉(provenance 缺口)"这个 bug 变成"单处可改的旋钮"。

**风险姿态:行为保持**——纯债务消减,**零产品变化**。界统一(选 5 还是 6 修缺口)是 **principled 改判,留 follow-up**(需校准数据,不拍脑袋)。

## 现状(已核实,master 版)

| 站点(master) | 现状判定 | 实体 | 界 | 喂哪条路 |
|---|---|---|---|---|
| `produce.py:322` _settle_facts deaths | `who and 2 <= len(who) <= 6` | 人名 | 2-6 | 控制面账本 |
| `produce.py:335` _settle_facts milestones | `who and 2 <= len(who) <= 6 and ev` | 人名 | 2-6 | 控制面账本 |
| `produce.py:330` _settle_facts items | `name and 2 <= len(name) <= 8 and any(...)` | **物品名** | 2-8 | 控制面账本 |
| `prose_facts.py:~102` cross_check deaths | `who and 2 <= len(who) <= 6 and who not in deaths` | 人名 | 2-6 | 事实表对账 |
| `prose_continuity.py:40` extract_roster persons | `isinstance(nm, str) and 2 <= len(nm.strip()) <= 5` | 人名 | 2-5 | prose 连续性 roster |
| `prose_continuity.py:121` _variant_scan 锚 | `not (2 <= len(c) <= 4)` | 人名(锚) | 2-4 | 错字扫描锚(**有意更紧**) |
| `prose_continuity.py:146` cluster_names | `counts.get(p,0) >= 3 and 2 <= len(p) <= 5` | 人名 | 2-5 | prose 名聚类 |

**bug**:人名界 2-6(事实表/账本)vs 2-5(roster/cluster)不一致 → 5-6 字人名在事实表能追、在 prose-continuity 隐形(provenance 缺口)。危害窄(长中文人名罕见,事实表路仍追),故本期只集中化、不改界。

注:`prose_facts.py` 行号在 master 上是 cross_check 旧 inline 版(C1 未合);实现者读 master 实际代码定位。

## 架构

### 模块与谓词
新建 `src/hiki/names.py`(纯函数,零依赖):
```python
def is_person_name(nm: str, max_len: int) -> bool:
    """人名长度谓词单源。nm 须为已 str 化字符串(调用方保留各自 isinstance/strip)。
    下界 2(最短中文名);上界由调用方传——现状 4/5/6 分叉, 统一(修 provenance 缺口)留 follow-up。"""
    return 2 <= len(nm) <= max_len


def is_item_name(nm: str) -> bool:
    """物品/法器名谓词(可较长的复合名, 如 '天雷血玉珠')。"""
    return 2 <= len(nm) <= 8
```
**谓词只做长度**;各站点的 `isinstance` / `.strip()` / `who and` 真值前检、`and ev` / `and any(...)` 后置条件、`and who not in deaths` / `counts>=3` 等**原样保留在站点**——确保逐位等价。

### 迁移(7 站点,各传当前界)
| 站点 | 改为 |
|---|---|
| `produce.py:322` deaths | `who and is_person_name(who, 6)` |
| `produce.py:335` milestones | `who and is_person_name(who, 6) and ev` |
| `produce.py:330` items | `name and is_item_name(name) and any(...)` |
| `prose_facts.py:~102` deaths | `who and is_person_name(who, 6) and who not in deaths` |
| `prose_continuity.py:40` roster | `isinstance(nm, str) and is_person_name(nm.strip(), 5)` |
| `prose_continuity.py:121` 锚 | `cc < floor or not is_person_name(c, 4)` |
| `prose_continuity.py:146` cluster | `counts.get(p,0) >= 3 and is_person_name(p, 5)` |

各站点 `import` `from .names import is_person_name, is_item_name`。`max_len`(4/5/6)显式传参 = bug 的"单旋钮"。

## 验证

- `tests/test_names.py`:谓词纯函数语料——`is_person_name` 边界(len 1/2/max_len/max_len+1,各 max_len ∈ {4,5,6});`is_item_name` 边界(1/2/8/9)。
- 迁移站点靠**既有测试**(`test_prose_facts`/`test_audit`/`test_produce_units`/`test_mining`/`test_spine_renderers` 等覆盖 _settle_facts/extract_roster/cluster_names/cross_check)+ **全量绿**证等价(行为保持,无新断言)。
- 无直接覆盖的站点(如 `_variant_scan`)补轻量 characterization 钉死迁移前后等价。
- 行为保持:`produce.py` 门/LLM 步不受影响(谓词只换长度判定的写法)。

## 非目标(本 spec 明确不做)
- 界统一(选 5/6 修 provenance 缺口)—— principled,留 follow-up(需校准)。
- `safe_pairs` / pair 形状校验集中化(`isinstance(pair,(list,tuple)) and len>=2`,已部分由 `_str_pair` 覆盖)—— 独立小清理,留 follow-up。
- C3 身份 / A3 schema / 门阈值 / LLM 步。

## 风险
- **逐位等价的关键 = 前检/后置留站点**:若把 `isinstance`/`.strip()` 误并进谓词,会改变本无 isinstance 站点的行为(对非 str 输入)。谓词只做 `2<=len<=max_len`,其余留原位。
- `prose_continuity.py:121` 是 `not (2<=len<=4)`(反相);迁移须保持 `not is_person_name(c, 4)` 的反相语义。
- C5 与 C1/C2 文件重叠(prose_facts/prose_continuity)但改的是不同行;若 C1/C2 先合,C5 rebase 时这些 `len` 行大概率无冲突(C1/C2 未改界过滤行本身)。
