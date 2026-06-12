# Tier3 A+B 验证轮 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 prose 事实层闭环(交付门升级+全书对账环)与顺序整本起草 M0 对照实验,产出三份硬数据(门回放表/对账召回表/顺序-并行差分表)。

**Architecture:** 设计见 `docs/design/tier3_fact_loop_and_seq_draft.md`。A1 先回放后改门;A2 新模块 `prose_facts.py` 文本自洽审计(不依赖 bible),用第7跑两本的已知缺陷当真值测召回;B 给 `_draft_candidates` 加模板注入点 + `DRAFT_SEQ`(history-first,吃前缀缓存),一次规划两种起草,差分**修复前**的矛盾数。

**Tech Stack:** Python 3 / asyncio / DeepSeek v4(`hiki.client.Client`)。注意:本项目**不是 git 仓库**,无 commit 步;每任务以验证运行收尾。Windows 控制台 GBK → 所有脚本顶部 `sys.stdout.reconfigure(encoding="utf-8")`,文件读写显式 `encoding="utf-8"`。

**真钱预算:** A2 召回测试 ~¥2(2本×单pass×重试余量);B 实验 ~¥8-15(规划1次+两臂起草,n=3 无金标)。A1/A3 零成本。

---

### Task 1 (A3): HFL 追加第7跑 Fable 记录

**Files:** Modify: `assets/hfl.jsonl`(追加2行,UTF-8——不要用 PowerShell Add-Content,会写 GBK)

- [ ] **Step 1: 用 python 追加两条记录**(schema 对齐现有行:date/scorer/round/title/source/dims{拉力,笔力,人,承重}/total/comments/auto_signals/version;scorer="fable" 与人工隔离)

```python
# 一次性: python scripts/append_hfl_r7.py (或 python -c 内联)
import json
recs = [
  {"date": "2026-06-11", "scorer": "fable", "round": 7, "title": "前妻归来：温医生她不将就",
   "source": "ZYGXY01847冷战三年，离婚当日纪总哭红了眼",
   "dims": {"拉力": 74, "笔力": 73, "人": 65, "承重": 40}, "total": 64.7,
   "comments": "拉力:单章钩子在线但章末钩子赖账(31章律师函无下文)爽点靠堆尸体;笔力:高光章近人写/低谷章纲要体方差大;人:女主单场主动但人设四次换皮(医师→实习→网红→合伙人);承重:纪老夫人二次死亡/女儿先于受孕/婚龄四版本/缅北线悬空",
   "auto_signals": {"final_consistent": True, "维14死人复活": 1, "章缝_检出": 23, "章缝_修复": 17, "暗黑比": 0.02},
   "version": "round7-fact-eval"},
  {"date": "2026-06-11", "scorer": "fable", "round": 7, "title": "全球屠神后，我开启星辰征途",
   "source": "CPBGX00192灵气复苏：开局无限合成",
   "dims": {"拉力": 72, "笔力": 68, "人": 60, "承重": 47}, "total": 63.0,
   "comments": "拉力:章章有钩但傀儡战钩子蒸发/一拳之威×3/十秒团灭;笔力:中后期震惊体+断头残句(ch31/32);人:主角自驱但零内面成长全员功能件;承重:6套等级体系混用/数值倒退互斥/冉剑锋龙御须佐同章死活/青阳天一武堂双名",
   "auto_signals": {"final_consistent": False, "维14死人复活": 0, "章缝_检出": 29, "章缝_修复": 20, "暗黑比": 0.02},
   "version": "round7-fact-eval"},
]
with open("assets/hfl.jsonl", "a", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
```

- [ ] **Step 2: 验证** `python -c "import json;[json.loads(l) for l in open('assets/hfl.jsonl',encoding='utf-8')]"` 全行可解析,行数=8。

---

### Task 2 (A1a): 交付门回放脚本

**Files:** Create: `scripts/replay_gate.py`

- [ ] **Step 1: 写回放脚本。** 信号取自 report.json;**final_consistent 判据只对带 `章缝_检出` 字段的新报告生效**(旧报告该位被篇幅 bug 污染,round6 修的);旧报告残缝判据跳过(无字段)。

```python
"""回放新交付门判据于盘上全部 report.json,对照已知人工/Fable 分。
通过标准: 分数≤65 全拦 / ≥68 全放。误拦好书 → 调残缝阈值(初拍8)。"""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
OUT = Path("output")
KNOWN = {  # 源目录名片段 → (分, 评分人)
    "暴君偷听": (37, "总编辑"), "全球陆沉": (62, "总编辑"), "荒年超市": (64.25, "总编辑"),
    "逃荒路上": (68.75, "总编辑"), "大佬她美飒": (73, "总编辑"),
    "团宠小师妹靠摆烂带飞全宗门_full_round6": (75.25, "总编辑"),
    "冷战三年": (64.7, "fable"), "灵气复苏": (63.0, "fable"),
}
SEAM_TH = int(sys.argv[1]) if len(sys.argv) > 1 else 8

def new_gate(rep: dict) -> list[str]:
    issues = []
    hard = rep.get("audit_承重_确定性硬检") or {}
    rev = hard.get("维14死人复活") or []
    if isinstance(rev, list) and rev and rev != ["无"]:
        issues.append(f"死人复活{len(rev)}处")
    if "章缝_检出" in rep:                      # 新报告才有,亦是 final_consistent 已修的时代标记
        fixed = rep.get("章缝_修复") or []
        n_fixed = 0 if fixed == ["无"] else len(fixed)
        residual = (rep.get("章缝_检出") or 0) - n_fixed
        if residual > SEAM_TH:
            issues.append(f"残缝{residual}处")
        if rep.get("final_consistent") is False:
            issues.append("final_consistent=false")
    return issues

rows = []
for rp in sorted(OUT.glob("*_full*/report.json")):
    rep = json.loads(rp.read_text(encoding="utf-8"))
    if rep.get("rejected"):
        continue
    tag = rp.parent.name
    score = next((v for k, v in KNOWN.items() if k in tag), None)
    old_blocked = rep.get("deliverable") is False
    new_iss = new_gate(rep)
    rows.append((tag[:34], score, old_blocked, bool(new_iss) or old_blocked, "；".join(new_iss) or "—"))
print(f"{'书':<36}{'分':>8}  旧门拦  新门拦  新增判据命中")
ok = True
for tag, score, ob, nb, why in rows:
    s = f"{score[0]}({score[1][:2]})" if score else "无分"
    print(f"{tag:<36}{s:>10}  {'拦' if ob else '放':^5}  {'拦' if nb else '放':^5}  {why}")
    if score:
        if score[0] <= 65 and not nb: ok = False; print("   ^^ 漏放烂书!")
        if score[0] >= 68 and nb:     ok = False; print("   ^^ 误拦好书!")
print("\n回放结论:", "通过(≤65全拦/≥68全放)" if ok else "未通过,需调阈值或弃用某判据")
```

- [ ] **Step 2: 运行** `python scripts/replay_gate.py`(项目根)。预期:冷战(维14=1)/灵气(final_consistent=false)被新门拦;摆烂75.25/星际73/单亲68.75 不被误拦。
- [ ] **Step 3: 若误拦好书** → 先试调阈值 `python scripts/replay_gate.py 12`;final_consistent 判据若误拦 ≥68 的书则降级为只配合维14/残缝使用(记录决策进设计文档)。回放表全文留存到 `docs/plans/replay_result.md`。

---

### Task 3 (A1b): 交付门落地(回放通过后才做)

**Files:** Modify: `src/hiki/produce.py:494-507`(ship_issues 块)

- [ ] **Step 1: 改门。** 把 final_consistent 计算从 report dict(~551行)上移到门前,新增三判据(阈值用回放定稿值):

```python
    # 5.5) 交付门(6本人工回放校准 + Tier3 回放扩展: 维14/残缝/final_consistent 进门——
    #     第7跑实证: 维14命中+final_consistent=false 的两本人工63-65,旧门照常放行)
    too_short = [d for d in det if d.startswith("过短")]
    final_consistent = not advisory and not [d for d in det if "长" not in d and "短" not in d]
    seam_residual = seam_found - len(seam_fixed)
    ship_issues = []
    if audit_struct.get("维2阵营串线"):
        ship_issues.append(f"阵营串线{len(audit_struct['维2阵营串线'])}条(canon级硬伤)")
    if len(too_short) >= 3:
        ship_issues.append(f"{len(too_short)}章过短<70%(二次扩写后仍稀薄)")
    if values_reject:
        ship_issues.append(f"暗黑饱和(暗黑比{dark_rep['dark_ratio']}>0.25)")
    if climax_skipped:
        ship_issues.append(f"预告事件被跳过未演({climax_skipped})")
    if audit_struct.get("维14死人复活"):
        ship_issues.append(f"死人复活{len(audit_struct['维14死人复活'])}处(prose事实硬伤)")
    if seam_residual > 8:                          # 阈值=回放定稿值
        ship_issues.append(f"残缝{seam_residual}处(章缝修复采用不足)")
    if not final_consistent:
        ship_issues.append("final_consistent=false(连续性残留)")
    deliverable = not ship_issues
```

- [ ] **Step 2: report dict 里原 `"final_consistent": not advisory and ...` 改为引用变量** `"final_consistent": final_consistent,`(删除重复表达式)。
- [ ] **Step 3: 语法验证** `python -c "import ast;ast.parse(open('src/hiki/produce.py',encoding='utf-8').read())"`。**不跑真书**(门生效与否下轮批量验证;判据本身已被回放证明)。

---

### Task 4 (A2a): 全书对账环模块

**Files:** Create: `src/hiki/prose_facts.py` ｜ Modify: `src/hiki/prompts.py`(尾部追加 FACT_AUDIT)、`config/models.yaml`(routing 加 `fact_audit: v4-pro`)

- [ ] **Step 1: prompts.py 追加**(沿用 (sys, usr_tmpl) 元组惯例):

```python
# Tier3: 全书事实对账(1M 单pass,只报跨章硬矛盾,引文逐字可grep验证)
FACT_AUDIT = (
    "你是网文出版社的事实审校。通读整本书,只找**跨章节的事实硬矛盾**,五类:"
    "①生死(人物明确死亡后又实质在场行动,被回忆/提及不算)"
    "②修为体系(等级阶梯前后不兼容/同一人修为无理由倒退)"
    "③时间轴(跨章事件顺序互斥/时间倒流,如先有孩子后怀孕)"
    "④身份(同一人物职业/身份/姓名前后矛盾,如同一机构两个名字)"
    "⑤数值(年龄/婚龄/战力等具体数字跨章互斥)。"
    "铁律: 只报确凿矛盾,不报风格/节奏/猜测;每条引文必须**逐字摘抄正文**≤30字;"
    "宁缺毋滥,无矛盾的类别不输出。输出JSON:"
    '{"findings":[{"cat":"生死|体系|时间轴|身份|数值","who":"涉及实体","ch_a":1,"quote_a":"…",'
    '"ch_b":47,"quote_b":"…","why":"≤40字说明矛盾"}]}',
    "【全书正文(含章标记)】\n{text}\n\n通读后输出五类跨章硬矛盾清单(JSON)。")
```

- [ ] **Step 2: 写 `src/hiki/prose_facts.py`:**

```python
"""Tier3 全书事实对账环: 21万字单pass入栈(V4 1M),抓 prose 层跨章硬矛盾。
设计依据: 第7跑实证承重失效全在 prose 事实层(死人复活/时间轴互斥/体系混用/数值倒退),
分窗审计与 plan 级账本均盲。引文逐条确定性 grep 验证(预评轮纪律: LLM 方向可信,指控必须可验)。"""
from __future__ import annotations
import asyncio, json, re, sys
from pathlib import Path
from . import prompts
from .gate import _safe_json
from .client import Client

_CH_SPLIT = re.compile(r"^# 第\d+章.*$", re.M)
_CATS = {"生死", "体系", "时间轴", "身份", "数值"}


def split_chapters(final_md: str) -> list[str]:
    """final.md → 章文本列表(无标题行)。"""
    parts = _CH_SPLIT.split(final_md)
    chs = [p.strip() for p in parts[1:]]          # parts[0]=书名/前言,丢弃
    return chs if chs else [final_md]


def _norm(s: str) -> str:
    return re.sub(r"[\s,。!?、:;""''…—\"']", "", s)


def verify_finding(f: dict, ch_texts: list[str]) -> bool:
    """确定性验证: 两条引文都逐字(去标点空白)出现在所指章 ±1 章内。"""
    def hit(q: str, ch: int) -> bool:
        if not q or not isinstance(ch, int) or not (1 <= ch <= len(ch_texts)):
            return False
        nq = _norm(q)[:24]
        if len(nq) < 6:
            return False
        lo, hi = max(0, ch - 2), min(len(ch_texts), ch + 1)
        return any(nq in _norm(ch_texts[i]) for i in range(lo, hi))
    return hit(f.get("quote_a"), f.get("ch_a")) and hit(f.get("quote_b"), f.get("ch_b"))


async def fact_audit(cli: Client, ch_texts: list[str]) -> dict:
    """单pass全书对账 → {findings:[...含verified标记], n_verified}。retry-on-empty×3。"""
    labeled = "\n\n".join(f"# 第{i + 1}章\n{t}" for i, t in enumerate(ch_texts))
    sys_p, usr_t = prompts.FACT_AUDIT
    findings = []
    for t in range(3):
        raw = await cli.complete("fact_audit", sys_p, usr_t.format(text=labeled),
                                 json_mode=True, max_tokens=8000, temperature=0.2 + 0.1 * t)
        r = _safe_json(raw) or {}
        items = r.get("findings")
        if isinstance(items, list):
            findings = [f for f in items if isinstance(f, dict) and f.get("cat") in _CATS]
            break
    for f in findings:
        f["verified"] = verify_finding(f, ch_texts)
    return {"findings": findings, "n_verified": sum(1 for f in findings if f["verified"])}


async def _main(out_dir: str) -> None:
    final = (Path(out_dir) / "final.md").read_text(encoding="utf-8")
    chs = split_chapters(final)
    cli = Client()
    rep = await fact_audit(cli, chs)
    (Path(out_dir) / "fact_audit.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"章数={len(chs)} 矛盾={len(rep['findings'])} 其中grep验真={rep['n_verified']} "
          f"¥{cli.cost_cny:.2f}")
    for f in rep["findings"]:
        v = "✓" if f["verified"] else "✗未验"
        print(f"[{f['cat']}]{v} {f.get('who','')}: ch{f.get('ch_a')}「{f.get('quote_a','')[:20]}」"
              f"vs ch{f.get('ch_b')}「{f.get('quote_b','')[:20]}」 {f.get('why','')}")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(_main(sys.argv[1]))
```

- [ ] **Step 3: models.yaml routing 末尾加** `  fact_audit: v4-pro    # Tier3 全书对账,1M单pass`
- [ ] **Step 4: 纯函数自测(不花钱):**

```python
# python -c 运行: split_chapters + verify_finding
from hiki.prose_facts import split_chapters, verify_finding
chs = split_chapters("# 《书》\n\n# 第1章 x\n纪老夫人喝了参汤。\n\n# 第2章 y\n纪老夫人已经下葬三年。")
assert len(chs) == 2
f = {"cat": "生死", "ch_a": 1, "quote_a": "纪老夫人喝了参汤", "ch_b": 2, "quote_b": "已经下葬三年"}
assert verify_finding(f, chs)
f2 = dict(f, quote_b="没出现过的引文内容啊")
assert not verify_finding(f2, chs)
print("ok")
```

预期输出 `ok`(运行加 `$env:PYTHONPATH='src'`)。

---

### Task 5 (A2b): 召回测试(真API,~¥2)

**Files:** Create: `scripts/m0_fact_recall.py`

- [ ] **Step 1: 写召回脚本。** 真值=第7跑 Fable 评审坐实清单(引文已 grep 验过):

```python
"""对账环 M0: 在冷战/灵气两本已知病例上测召回。判据: 召回≥70%接产线,<50%降级advisory。
匹配规则: 类别同 + 实体名同(或包含) + 章号差≤3 → 命中。"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, "src"); sys.stdout.reconfigure(encoding="utf-8")
from hiki.prose_facts import fact_audit, split_chapters
from hiki.client import Client

TRUTH = {
  "output/ZYGXY01847冷战三年，离婚当日纪总哭红了眼_full": [
    {"cat": "生死",  "who": "纪老夫人", "ch": 47},   # 15章死亡火化,47章复活,后又二次死亡
    {"cat": "时间轴", "who": "奚曼",    "ch": 45},   # 女儿先于受孕: 24章B超 vs 45章妊娠八周
    {"cat": "数值",  "who": "婚龄",    "ch": 60},   # 四年/五年/三年/两年前四版本
    {"cat": "身份",  "who": "白清霜",  "ch": 59},   # 生母轮廓→下毒保姆
    {"cat": "身份",  "who": "温苒",    "ch": 31},   # 医师→实习→网红→合伙人四次换皮
  ],
  "output/CPBGX00192灵气复苏：开局无限合成_full": [
    {"cat": "体系",  "who": "等级",    "ch": 32},   # ≥6套等级阶梯混用
    {"cat": "数值",  "who": "司天宇",  "ch": 3},    # 十一卡→气血7.2
    {"cat": "数值",  "who": "陆景",    "ch": 4},    # 16.12卡→档案14.32/入学检测2.1
    {"cat": "生死",  "who": "冉剑锋",  "ch": 59},   # 同章化血雾又被擒着奄奄一息
    {"cat": "生死",  "who": "龙御",    "ch": 60},   # 59章化光点消散,60章在陆景身边
    {"cat": "身份",  "who": "武堂",    "ch": 4},    # 青阳武堂vs天一武堂双名
  ],
}

def match(t: dict, f: dict) -> bool:
    if t["cat"] != f.get("cat"):
        return False
    who_f = str(f.get("who", ""))
    name_ok = t["who"] in who_f or who_f in t["who"] or t["who"] in str(f.get("why", ""))
    ch_ok = any(isinstance(f.get(k), int) and abs(f[k] - t["ch"]) <= 3 for k in ("ch_a", "ch_b"))
    return name_ok and ch_ok

async def main():
    cli = Client()
    tot_t = tot_hit = tot_f = tot_v = 0
    for d, truths in TRUTH.items():
        chs = split_chapters((Path(d) / "final.md").read_text(encoding="utf-8"))
        rep = await fact_audit(cli, chs)
        fs = rep["findings"]
        hits = [t for t in truths if any(match(t, f) for f in fs)]
        miss = [t for t in truths if t not in hits]
        tot_t += len(truths); tot_hit += len(hits); tot_f += len(fs); tot_v += rep["n_verified"]
        print(f"\n== {d.split('/')[-1][:24]} 召回 {len(hits)}/{len(truths)} "
              f"报告{len(fs)}条(验真{rep['n_verified']}) 漏检:{[m['who'] for m in miss]}")
        for f in fs:
            print(f"  [{f['cat']}]{'✓' if f['verified'] else '✗'} {f.get('who','')}: {f.get('why','')[:40]}")
        (Path(d) / "fact_audit.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    rec = tot_hit / tot_t
    prec_proxy = tot_v / max(1, tot_f)
    print(f"\n总召回 {tot_hit}/{tot_t}={rec:.0%} | 引文验真率 {tot_v}/{tot_f}={prec_proxy:.0%} | ¥{cli.cost_cny:.2f}")
    print("判定:", "≥70% 接产线" if rec >= 0.7 else ("50-70% 灰区,加一轮重试/换prompt再测" if rec >= 0.5 else "<50% 降级advisory,路线B风险上调"))

asyncio.run(main())
```

- [ ] **Step 2: 运行** `python scripts/m0_fact_recall.py`(需 .env 的 DEEPSEEK_API_KEY;~2-5min)。
- [ ] **Step 3: 记录结果**到 `docs/plans/recall_result.md`(召回/验真率/漏检类别/成本)。**召回≥70% 时**(且仅此时)在 produce.py 4h 之后追加 4i 对账步(单独小改动:`fact_rep = await prose_facts.fact_audit(cli, ch_texts)`,verified 命中数进 ship_issues 阈值≥2、全量进 report)——这步留到下一任务批,本轮只出数据。

---

### Task 6 (B-a): 顺序起草支撑件(零API成本)

**Files:** Modify: `src/hiki/slice_validate.py:47-71`(tmpl 注入点)、`src/hiki/prompts.py`(DRAFT_SEQ)、`src/hiki/produce.py`(规划产物落盘3行)

- [ ] **Step 1: `_draft_candidates` 与 `_process_scene` 加 `tmpl=None` 透传:**

```python
async def _draft_candidates(cli: Client, sc: dict, bible: dict, voice: str,
                            target: int, n: int, gold: str = "", context: str = "",
                            tmpl: tuple[str, str] | None = None) -> list[str]:
    sys_p, usr_t = tmpl or prompts.DRAFT
```

`_process_scene` 签名加 `tmpl: tuple[str, str] | None = None`,调用处 `_draft_candidates(..., context=context, tmpl=tmpl)`。默认行为不变(并行产线零影响)。

- [ ] **Step 2: prompts.py 追加 DRAFT_SEQ**(system 复用 DRAFT[0];usr=history-first,append-only 前缀吃缓存):

```python
# Tier3 M0: 顺序整本起草模板。{history}在最前=append-only前缀(DeepSeek缓存命中),
# 起草者直接看见前文实际正文(非状态摘要)→章缝/复活/重复初遇类生成时不犯。
DRAFT_SEQ = (DRAFT[0], "【已成章前文(实际正文,与之绝不矛盾,禁重写已发生事件)】\n{history}\n\n" + DRAFT[1])
```

(注: DRAFT[1] 里的 `{context}` 占位仍在,顺序模式传 `context="(前文见最上方已成章正文)"`。)

- [ ] **Step 3: produce.run 规划后落盘产物**(在 `det_struct = ...`(~357行) 之前插入;批量/复评/B实验都用得上):

```python
    for nm, obj in (("bible", bible), ("macro", macro), ("plan", plan)):
        (out_dir / f"{nm}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: 验证** `python -c "import ast;ast.parse(...)"` 两文件 + `$env:PYTHONPATH='src'; python -c "from hiki import prompts; assert len(prompts.DRAFT_SEQ)==2; assert '{history}' in prompts.DRAFT_SEQ[1]; print('ok')"`。

---

### Task 7 (B-b): 顺序 vs 并行对照实验(真API ~¥8-15,后台跑)

**Files:** Create: `scripts/m0_seq_draft.py`

- [ ] **Step 1: 写实验脚本。** 锚源=团宠;**一次规划,两臂起草**;两臂同设置(n=3/无金标/无peak);**跳过全部修复 pass**(修复会掩盖架构差异),只 fit+truncate+组装;差分=对账环矛盾数 + 首尾10章套话密度/控字。

```python
"""B路线 M0: 同一plan下 顺序整本上下文起草 vs 并行分章起草 对照差分。
切换判据(三条同时成立才换起草层): 顺序矛盾数≤并行50% / 尾部章质量不塌 / 成本≤2×。"""
import asyncio, json, sys, time
from pathlib import Path
sys.path.insert(0, "src"); sys.stdout.reconfigure(encoding="utf-8")
from hiki import mining, audit, ledger, prompts
from hiki.client import Client
from hiki.ingest import ingest
from hiki.produce import _plan_macro, _plan_one_chapter, _handoff
from hiki.slice_validate import _process_scene, _fit_chapter, _truncate, _assemble
from hiki.prose_facts import fact_audit

SRC = Path("fictions_source/ZYGGY03733团宠小师妹靠摆烂带飞全宗门.txt")
OUT = Path("output/_m0_seq"); OUT.mkdir(parents=True, exist_ok=True)
N_CH, N_CAND = 60, 3

async def plan_once(cli):
    pf = OUT / "plan_artifacts.json"
    if pf.exists():                                   # 断点续跑: 规划只做一次
        a = json.loads(pf.read_text(encoding="utf-8"))
        return a["bible"], a["plan"], a["scenes"]
    meta = ingest(SRC, OUT / "source")
    clean = (OUT / "source" / "clean.txt").read_text(encoding="utf-8")
    mined = await mining.mine_book(cli, clean, 13, int(N_CH * 1.4))
    bible, scenes = mined["bible"], mined["scenes"]
    macro = await _plan_macro(cli, bible, scenes, N_CH)
    beats = macro.get("chapters", [])[:N_CH]
    p = bible.get("protagonist", {})
    bb = json.dumps({"protagonist": {k: p.get(k) for k in ("name", "gender", "goal", "arc")},
                     "characters": [{"name": c.get("name"), "goal": c.get("goal")}
                                    for c in bible.get("characters", [])[:8]],
                     "setting": bible.get("setting")}, ensure_ascii=False)[:3000]
    def _bb(b): return (b.get("beat") or "")[:60] or "（无）"
    chs = await asyncio.gather(*[_plan_one_chapter(cli, b, scenes, bb,
                                 prev_beat=_bb(beats[j-1]) if j else "（本章是开篇）",
                                 next_beat=_bb(beats[j+1]) if j < len(beats)-1 else "（本章是全书结局）")
                                 for j, b in enumerate(beats)])
    plan = {"chapters": [c for c in chs if c.get("scenes")]}
    ordered = [sc for ch in plan["chapters"] for sc in ch["scenes"]]
    ledger.dedup_first_meetings(ordered)
    audit.fix_entourage(bible, ordered); audit.fix_power_monotonic(bible, ordered)
    pf.write_text(json.dumps({"bible": bible, "plan": plan, "scenes": scenes},
                             ensure_ascii=False), encoding="utf-8")
    return bible, plan, scenes

async def arm_parallel(cli, bible, plan):
    voice = bible.get("voice", "网文白话")
    ordered = [sc for ch in plan["chapters"] for sc in ch["scenes"]]
    spc = max(1.0, len(ordered) / max(1, len(plan["chapters"])))
    target = int(3500 / spc * 0.92)
    jobs = [(ci, si, sc) for ci, ch in enumerate(plan["chapters"]) for si, sc in enumerate(ch["scenes"])]
    res = await asyncio.gather(*[
        _process_scene(cli, sc, bible, voice, target, N_CAND,
                       context=ledger.format_context(ledger.state_before(ordered, i)) + _handoff(jobs, plan, i))
        for i, (_, _, sc) in enumerate(jobs)])
    out: dict[int, list[str]] = {}
    for (ci, _, _), r in zip(jobs, res):
        out.setdefault(ci, []).append(r["winner"])
    return ["\n\n".join(out.get(ci, [])) for ci in range(len(plan["chapters"]))]

async def arm_sequential(cli, bible, plan):
    voice = bible.get("voice", "网文白话")
    n_sc = sum(len(c["scenes"]) for c in plan["chapters"])
    target = int(3500 / max(1.0, n_sc / max(1, len(plan["chapters"]))) * 0.92)
    prev: list[str] = []
    for ch in plan["chapters"]:
        parts: list[str] = []
        for sc in ch["scenes"]:
            hist = "\n\n".join(f"# 第{i+1}章\n{t}" for i, t in enumerate(prev)) or "（本书尚未开始）"
            if parts:
                hist += "\n\n# 本章已写部分\n" + "\n\n".join(parts)
            tmpl = (prompts.DRAFT_SEQ[0], prompts.DRAFT_SEQ[1].replace("{history}", hist.replace("{", "{{").replace("}", "}}")))
            r = await _process_scene(cli, sc, bible, voice, target, N_CAND,
                                     context="(前文见最上方已成章正文)", tmpl=tmpl)
            parts.append(r["winner"])
        prev.append("\n\n".join(parts))
    return prev

async def finish(cli, chs):
    chs = await asyncio.gather(*[_fit_chapter(cli, t, 3500) for t in chs])
    return [_truncate(t, int(3500 * 1.15)) for t in chs]

def tail_quality(chs):
    def block(idx):
        txt = "\n".join(chs[i] for i in idx)
        cl = sum(sum(v.values()) if isinstance(v, dict) else len(v) for v in audit.cliche_hits(txt).values()) if audit.cliche_hits(txt) else 0
        return {"套话": cl, "均字": sum(len(chs[i]) for i in idx) // len(idx),
                "过短章": sum(1 for i in idx if len(chs[i]) < 3500 * 0.7)}
    return {"前10章": block(range(10)), "后10章": block(range(len(chs) - 10, len(chs)))}

async def main():
    cli = Client()
    bible, plan, _ = await plan_once(cli)
    print(f"规划就绪 {len(plan['chapters'])}章 ¥{cli.cost_cny:.2f}")
    rep = {}
    for name, arm in (("parallel", arm_parallel), ("sequential", arm_sequential)):
        c2 = Client(); t0 = time.time()
        chs = await finish(c2, await arm(c2, bible, plan))
        (OUT / f"final_{name}.md").write_text(_assemble(plan, chs), encoding="utf-8")
        fa = await fact_audit(c2, chs)
        rep[name] = {"矛盾总数": len(fa["findings"]), "矛盾验真": fa["n_verified"],
                     "by_cat": {c: sum(1 for f in fa["findings"] if f["cat"] == c and f["verified"])
                                for c in ("生死", "体系", "时间轴", "身份", "数值")},
                     "尾部质量": tail_quality(chs), "墙钟s": round(time.time() - t0, 1),
                     "成本¥": round(c2.cost_cny, 2)}
        print(name, json.dumps(rep[name], ensure_ascii=False))
    (OUT / "m0_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    p, s = rep["parallel"], rep["sequential"]
    ok1 = s["矛盾验真"] <= p["矛盾验真"] * 0.5
    ok2 = s["尾部质量"]["后10章"]["过短章"] <= 1 and s["尾部质量"]["后10章"]["套话"] <= p["尾部质量"]["后10章"]["套话"] * 1.3
    ok3 = s["成本¥"] <= p["成本¥"] * 2
    print(f"\n切换判据: 矛盾减半{ok1} 尾部不塌{ok2} 成本≤2×{ok3} → {'换起草层' if ok1 and ok2 and ok3 else '留路线A'}")

asyncio.run(main())
```

- [ ] **Step 2: 干跑校验**(不花钱):`python -c "import ast;ast.parse(open('scripts/m0_seq_draft.py',encoding='utf-8').read())"`;确认 `fictions_source/ZYGGY03733*.txt` 存在。
- [ ] **Step 3: 后台运行**(顺序臂60章串行,预计60-120min): `python scripts/m0_seq_draft.py`,run_in_background。
- [ ] **Step 4: 跑完读 `output/_m0_seq/m0_report.json`**,差分表+判据结论写入 `docs/plans/m0_seq_result.md`。

---

### Task 8: 汇总与决策记录

- [ ] **Step 1:** 三份结果(回放/召回/差分)汇总成一节追加到 `docs/design/tier3_fact_loop_and_seq_draft.md` 末尾(「## M0 实测结果」),给出:门定稿判据、对账环接线与否、起草层换否。
- [ ] **Step 2:** 项目记忆 `hiki-rewrite-redesign.md` 追加一段 Tier3 结果(沿用账本风格:数据+铁结论+下一步)。

---

## Self-Review 记录

- 覆盖:设计文档 A1(Task2/3)/A2(Task4/5)/A3(Task1)/B(Task6/7)/产出汇总(Task8) ✓
- 占位符:无 TBD;Task5 的"接产线 4i 步"显式标注**留到下一任务批**,本轮只出数据 ✓
- 类型一致:`fact_audit(cli, ch_texts)->dict` 在 Task4 定义、Task5/7 同签名调用;`tmpl` 参数 Task6 定义、Task7 使用 ✓
- 风险标注:DRAFT_SEQ 用 `.replace("{history}", ...)` 而非 format(history 含正文花括号会炸 format)——Task7 代码已按 replace+花括号转义写 ✓
