# C6 子项目② — config 门控 craft_audit 白烧 设计

> 2026-06-28 · 技术债 C6(检测器 sprawl:advisory 算了就扔白烧 token)第二片。接 C6①(DIMENSIONS 可信单源)。
> 基于:`master`(独立)。配套:`docs/design/tech-debt.md` C6 行。

## 背景(已核实,master)

三个"白烧 advisory"扫描器(LLM 调用但结果不进交付门)中,**默认配置下真正白烧的只有 craft_audit**:

| 扫描器 | 位置 | 成本 | 调用条件(现状) | 默认是否烧 | 可否裸关 |
|---|---|---|---|---|---|
| `craft_audit` | `audit.py:438`(1调用~2500tk),调用点 `produce.py:1242`(`_stage_finalize` 内,**门后**) | ~2500tk | **无条件** | **是** | ✅ 安全(纯报告) |
| `early_repeat_audit` | `audit.py:466`(1调用~600tk),调用点 `produce.py:1423`(**门前**) | ~600tk | 无条件 | 是 | ❌ **gating-leak**:`early_rep["count"]`→`早段重复`信号→把开篇代入感封顶30(<40硬门),关掉改出货判定 |
| `event_state_audit` | `event_audit.py:113`(~20-30调用),调用点 `produce.py:1410` | ~10k+tk | `HIKI_SPINE==1` | **默认否** | — |

**HIKI_SPINE 是 Fact Spine 特性主开关**(produce.py:509/839/982/1119/1410 五处用,1119 把 spine 薄网真矛盾喂进门=C6① gating 维6/12),由 CLI `--spine` 设置(1518)。默认关 → event_state 默认不跑不烧。**故本波只动 craft_audit。**

`config.load("pipeline")` 返 dict;`produce.run` 读 `_cfg.get("production")` 等(`produce.py:1265`)。`_stage_finalize`(`produce.py:1223`)**不接收 `_cfg`**(craft 调用在其内部)。

## 目标

给唯一的默认白烧 `craft_audit` 加 config 开关,量产精简跑可省 ~2500tk/本。**默认开 → 行为逐位保持**,省 token 是 opt-in。

**风险姿态:默认行为保持**(默认开,craft 照跑、报告同);关时跳过 craft + 报告占位。

## 架构

### ① 单源开关助手(`config.py`)
```python
def advisory_on(cfg: dict, name: str, default: bool = True) -> bool:
    """C6②: advisory 扫描器是否启用(config.advisories.<name>, 缺省 default)。
    advisory 开关单一来源, 不影响 gating。"""
    return (cfg.get("advisories") or {}).get(name, default)
```

### ② config 加 `advisories` 块(`config/pipeline.yaml`)
```yaml
advisories:                 # C6②: 白烧 advisory 开关(不影响 gating)
  craft_audit: true         # 门后 craft 人/故事性评审(~2500tk/本, 纯报告); 量产精简可关
```
canonical 默认在 `advisory_on` 的 `default` 参(调用点传 craft_audit 用 True);yaml 仅为可发现性。`config.py` 的 `_DEFAULTS` 回退(无 PyYAML 时)无需加——`_cfg.get("advisories")` 缺→`advisory_on` 走 `default=True`,语义同。

### ③ `_stage_finalize` 加尾参 + 门控 craft(`produce.py:1223 签名 / 1241-1244 craft 块`)
签名加尾 kwarg `craft_advisory: bool = True`(默认 True → 任何调用方/测试不破)。craft try-块改:
```python
    if craft_advisory:
        try:                                      # craft 仅 advisory，绝不为它丢成品/报告
            audit_craft = await audit.craft_audit(cli, final[:9000])
        except Exception as e:
            audit_craft = [f"(craft审计跳过:{type(e).__name__})"]
    else:
        audit_craft = ["(craft advisory 已关:config.advisories.craft_audit)"]
```
下游 `report.update({..., "audit_人+故事性_craft(advisory)": audit_craft or ["无"], ...})` 逐字不变。

### ④ run() 传入(`produce.py:1488`)
```python
    return await _stage_finalize(cli, src, out_dir, bible, final, deliverable, ship_issues, report,
                                 open_premise, immersion,
                                 craft_advisory=config.advisory_on(_cfg, "craft_audit"))
```
(`_cfg` 已在 run() `produce.py:1265` 加载;`produce` 已 import `config`。)

## 验证

- `config.advisory_on` 单测:缺 `advisories` 块→默认、块在但缺键→默认、显式 `true`/`false`→该值。
- 焦点测:`_stage_finalize`(mock cli + tmp out_dir + monkeypatch `audit.craft_audit`):
  - `craft_advisory=False` → `audit.craft_audit` **不**被 await(monkeypatch 成调用即抛/计数器)+ `report["audit_人+故事性_craft(advisory)"]` == 占位串。
  - `craft_advisory=True`(默认)→ craft 被调,结果入报告。
  - (mock cli 满足 `gen_title` 的 complete;传 `immersion={}` 避免重算 opening_immersion;`deliverable=False`;`out_dir=tmp_path`。)
- 既有 `test_produce_units`/`test_stages` 绿(默认 True → 行为逐位不变)。
- 金标/装配回归网绿(craft 是 advisory、不在冻结信号向量 → 天然不受影响)。
- SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- **early_repeat 不动**:gating-leak(封顶代入感→能触发硬门),关掉改出货判定,本波不碰(若要可控需另设计保 gating 等价)。
- **event_state / HIKI_SPINE 不动**:Spine 特性主开关(5 处用),默认关不烧,非 craft 式游离白烧。
- 不加其他 advisory 旋钮、不加 lean-mode 主开关(YAGNI)。不改阈值/信号/门/任何 gating 路径。
- 不改 craft_audit 自身逻辑、不改报告键名。

## 风险
- **默认为何 ON**:质量 > token;craft 产的人/故事性 advisory 喂人工三维复核(测量边界备忘),默认关会静默丢人工要看的信号 → 默认开,省 token 由量产跑显式置 `false`。
- **`_stage_finalize` 加参**:尾 kwarg 默认 True,run() 与任何直调/测试零破。
- **行为保持(默认)**:默认 True → craft 照跑、report 字段逐字同;金标/装配网天然绿(craft 非信号向量成员)。
- **关时影响**:仅报告 craft 段变占位串 + 省 ~2500tk;不触 gating/信号/成品。
