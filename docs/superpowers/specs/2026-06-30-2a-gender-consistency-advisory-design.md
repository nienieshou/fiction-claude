# 2a 全角色性别一致性检测器(advisory v1)设计

> 2026-06-30 · Stage-0 #2 之 2a(三检测器中第一个)。Stage-0 边缘书 符术师 配角"落羽"结尾 男→"她"漏检(`continuity_check` 只读前 8000 字 + 只问主角)。**范围 = advisory v1**(检出+浮现,**不**硬拦门 —— codex 警示 gender 硬拦会误拦 女扮男装/变身/兽世 等合法大类;用户拍板 advisory)。基于 `master`。codex 设计级压测已过(结论:canon 对照需证据验证 + 例外抑制 + 叙述/对话分离 + 归一)。

## 目标 / 范围(advisory v1)
检出"正文性别 ≠ bible canon 性别"的角色×章,作 **advisory**(进 `fact_adv` + 报告 + fact_table.json),供人/陪审复核。**不**进门(无 `spine_gender_contra` 门信号)、**不**进冻结 `build_signal_vector`、**不**改 `cross_check` 签名/逻辑、**不**改 gate/gold/装配网。FP 由 advisory 容忍(人决),但仍做 codex 要求的归一 + 例外抑制 + 叙述优先以保信号有用。

## 背景(已核实)
- `prose_facts.extract_facts`(逐章并发 LLM 抽取)字段:deaths/present/power/identity/numbers/items/milestones —— **无性别**。`fact_table_audit(cli, ch_texts) -> {findings,n_high,n_unaudited}`(extract_facts→cross_check)。`cross_check(facts)` 只 生死/数值/身份。
- bible 为**全角色**钉 canon 性别:`protagonist.gender` + `characters[].gender`;实测值含 `男/女/雄/雌/未知/无(器灵)`(codex 实证;`落羽=男` 在 stage0_edge)。
- `_fact_audit_repair` 现:`fact_adv = [f["why"] for f in ft["findings"] if f.get("conf") in ("高","中")]` → **conf 高/中 的 finding 自动进 advisory 列表**(无需新管线)。`point_repair._verified_revivals` 也调 `fact_table_audit(cli, chs)`。
- gate 信号(spine_num_contra/spine_id_contra)按 `cat=="数值"/"身份"` 过滤 → `性别` cat 不被门计数;`signal_counts_from_fact_table`/装配网走冻结 fact_table(无 gender)→ 不受影响。

## 架构(3 处 + 抽取)

### 1) `prompts.FACT_EXTRACT` — 加性别证据记录(无新 LLM 调用)
输出 schema 加:
```
"gender_mentions":[{"who":"本名","pronoun":"他|她|它","quote":"含该人名与代词的原文片段(≤40字)","source":"narration|dialogue"}]
```
(LLM 做"代词↔角色"关联 + 给可验证引文 + 标叙述/对话。只抽**叙述/对话明确指代某本名角色**的代词,模糊跳过。)

### 2) `prose_facts.gender_findings(facts, bible) -> list[dict]` — 新纯函数(canon 对照 + 例外 + 归一)
```python
_CANON_PRONOUN = {"男": "他", "雄": "他", "女": "她", "雌": "她", "母": "她"}  # codex: repo 含"母"
# 其余(未知/无/双性/器灵/不明/隐藏/它/非人/空) → skip(不比对, 无 finding)
_DISGUISE_MARK = ("女扮男装", "男装", "易容", "伪装", "变身", "换身", "化形",
                  "恢复女儿身", "公子", "神秘人", "看不清", "蒙面", "替身")
```
- 取 bible canon: `{name: gender}`(protagonist + characters[])。
- 逐 `gender_mentions`(优先 `source=="narration"`):canon 性别经 `_CANON_PRONOUN` 归一为应有代词;skip canon∈未知/无/双性/器灵 的角色。
- **例外抑制**:若该 mention 的 `quote` 或该角色 canon 上下文含 `_DISGUISE_MARK` 词 → 跳过(不报)。
- 正文代词 ≠ canon 应有代词 → finding `{cat:"性别", who, ch_b(章), pronoun, canon_pronoun, quote, source, why:"{who}第{ch}章正文'{pronoun}'与设定性别'{canon}'不符", conf}`。conf:narration=高、dialogue=中。
- **缺 canon 角色**:退跨章翻转检测(同角色不同章 narration 代词冲突)→ conf 中(advisory)。
- **去重**:同 (who, 章) 只一条。

### 3) `fact_table_audit` 加 `bible` 参 + 合并 gender_findings
```python
async def fact_table_audit(cli, ch_texts, bible=None) -> dict:
    facts = await extract_facts(cli, ch_texts)
    findings = cross_check(facts)
    if bible:
        findings = findings + gender_findings(facts, bible)
    return {"findings": findings, "n_high": ..., "n_unaudited": ...}
```
`bible` 默认 None → `point_repair._verified_revivals` 的 `fact_table_audit(cli, chs)` 调用**零变化**(无 gender)。

### 4) `produce._fact_audit_repair` 穿 `bible`(保 life_arcs)+ advisory 浮现
**codex 修**:现签名是 `_fact_audit_repair(cli, ch_texts, out_dir, life_arcs=None)`,run() 现以**位置参**传 `life_arcs`(`bible.get("life_arcs")` 一类)。**新增 `bible` 必须排在 `life_arcs` 之后且不动 life_arcs**:`_fact_audit_repair(cli, ch_texts, out_dir, life_arcs=None, bible=None)`;run() 调用改**关键字** `bible=bible`(life_arcs 仍按原样传,绝不被 bible 顶替 —— 否则破复活 beat 和解)。内部 `ft = await prose_facts.fact_table_audit(cli, ch_texts, bible=bible)`。`性别` findings(conf 高/中)经现有 `fact_adv = [f["why"] for f if conf in ("高","中")]` **自动进 advisory**;另加 report/stderr 计数 `性别不符 N 处(advisory)`。**不**进 sig/门/spine_net。

## 验证
- **`gender_findings` 纯单测**(新 `tests/test_gender_findings.py`):
  - canon 男 + 正文 narration "她" → finding(conf 高);canon 男 + "他" → 无。
  - 归一:canon 雄→他、雌→她;canon 未知/无/器灵/双性 → skip(无 finding 即便代词不符)。
  - 例外:quote 含 女扮男装/男装/公子/神秘人 → 抑制(无 finding)。
  - 叙述 vs 对话:narration 不符→conf 高;dialogue 不符→conf 中。
  - 缺 canon 角色:跨章 narration 代词翻转 → finding(conf 中);单章一致 → 无。
  - 去重:同 who 同章多 mention → 一条。
  - 落羽案:canon 男 + 正文 narration "她" → finding。
- **`fact_table_audit` 合并测**:bible 给定 → findings 含 `性别` 类;`bible=None`(point_repair 路)→ 无 `性别`、其余不变(逐字)。
- **缺字段容错测**:facts 无 `gender_mentions`(老抽取/抽取省略)→ `gender_findings` 返 `[]`,不崩(镜 A3 教训)。
- **`_fact_audit_repair` 测桩更新(codex)**:`tests/test_stages.py` 现 monkeypatch `prose_facts.fact_table_audit` 的桩须接受 `bible`(用 `*a,**k` 或加 `bible=None`);确认 `life_arcs` 路径(复活 beat 和解)不被 bible 顶替——加一断言 life_arcs 仍生效。
- **回归网绿**:`tests/test_gold_regression.py`/`test_assembly_regression.py`/`test_prose_facts.py` —— cross_check 签名/逻辑未动 + 冻结 fact_table 无 gender + signal_counts 不计 性别 → 平凡绿。`point_repair` 测(bible 默认 None)不变。
- 全量 `pytest -m 'not api'` 绿。SDD:逐任务 TDD + 两段复核 + opus 终审。

## 非目标
- **不**硬拦门 / 不加 `spine_gender_contra` 门信号 / 不进 `build_signal_vector` 冻结向量(都留待 gate 版,需例外抑制在真数据验稳)。
- **不**改 `cross_check`(签名+逻辑)/ gate / gold 夹具 / 信号 schema。
- **不**碰 2b 共指 / 2c 语义重复 / power(#1 已修)。
- **不**自动改写性别(advisory 只报,不动正文)。

## 风险
- **FP(advisory 容忍)**:LLM 代词关联噪声 / canon 与正文歧义 → 进 advisory 非门 → 人/陪审决,不拒书。归一 + 例外抑制 + 叙述优先降噪。
- **例外覆盖不全**:`_DISGUISE_MARK` 可能漏某些变身/伪装措辞 → 漏抑制 → 多报(advisory 容忍);后续按真数据扩词表。
- **bible canon 错/缺**:canon 本身错 → 误报正确正文(advisory 容忍);canon 缺该角色 → 退跨章翻转(低置信)。
- **抽取 schema 扩**:FACT_EXTRACT 加 gender_mentions → happy-path 其余字段不变(镜 A3 教训:加字段非改既有);gold fact_table 冻结不重跑 → 不受影响。
- **bible 参穿透**:`fact_table_audit`/`_fact_audit_repair` 加 `bible=None` 默认 → point_repair 等既有调用零变化(向后兼容)。

<!-- codex-peer-reviewed: 2026-06-30T06:52:28Z rounds=2 verdict=approved -->
