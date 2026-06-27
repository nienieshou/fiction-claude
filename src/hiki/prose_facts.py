"""Tier3 全书事实对账环: 21万字单pass入栈(V4 1M),抓 prose 层跨章硬矛盾。

设计依据(docs/design/tier3_fact_loop_and_seq_draft.md): 第7跑实证承重失效全在 prose 事实层
(死人复活/时间轴互斥/体系混用/数值倒退),分窗审计与 plan 级账本均盲——窗口看不见跨窗矛盾,
plan 干净不等于 prose 正确。引文逐条确定性 grep 验证(预评轮纪律: LLM 缺陷方向可信,具体指控必须可验)。
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from pathlib import Path
from . import prompts, textnum
from .gate import _safe_json
from .client import Client

_CH_SPLIT = textnum.MD_CH_RE
_CATS = {"生死", "体系", "时间轴", "身份", "数值"}
# 语义可变量(随情节合法变化,跨章不同≠矛盾):钱包余额/不同合同/股价等。
# 刻意排除 彩礼/年龄/婚龄/年限/走失年数 等应单值的设定不变量(不在此表)。
# 局限:表面词denylist枚举不全(synonym漏/子串误伤),正解是 LLM 抽取时标 mutable 语义——见 §fact_spine ⑥ 残留。
_MUTABLE = re.compile(r"余额|存款|现金|流水|身价|资产|合同|报价|成交|转账|欠款|借款|售价|股价|车程|路程")
_PUNCT = re.compile(r"[\s,。！？!?、：:;；“”‘’…—\"'《》()（）]")


def split_chapters(final_md: str) -> list[str]:
    """final.md → 章文本列表(无标题行)。parts[0]=书名/前言,丢弃。"""
    parts = _CH_SPLIT.split(final_md)
    chs = [p.strip() for p in parts[1:]]
    return chs if chs else [final_md]


def _norm(s: str) -> str:
    return _PUNCT.sub("", s or "")


def verify_finding(f: dict, ch_texts: list[str]) -> bool:
    """确定性验证: 两条引文都逐字(去标点空白)出现在所指章 ±1 章内。"""
    def hit(q: str, ch) -> bool:
        if not q or not isinstance(ch, int) or not (1 <= ch <= len(ch_texts)):
            return False
        nq = _norm(q)[:24]
        if len(nq) < 6:
            return False
        lo, hi = max(0, ch - 2), min(len(ch_texts), ch + 1)
        return any(nq in _norm(ch_texts[i]) for i in range(lo, hi))
    return hit(f.get("quote_a"), f.get("ch_a")) and hit(f.get("quote_b"), f.get("ch_b"))


async def fact_audit(cli: Client, ch_texts: list[str]) -> dict:
    """单pass全书对账 → {findings:[...含verified标记], n_verified}。retry-on-empty×3(核心flaky类)。"""
    labeled = "\n\n".join(f"# 第{i + 1}章\n{t}" for i, t in enumerate(ch_texts))
    sys_p, usr_t = prompts.FACT_AUDIT
    findings: list[dict] = []
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


# ============ R8 A2': 事实表对账(LLM逐章抽取→代码跨章确定性对比) ============
# 1M单pass"通读找矛盾"召回仅18%(深处不查)已证伪;局部抽取是模型强项,全局推理挪进代码。

# 数字解析单源 → textnum(C4); 别名保持接口兼容供内部调用及 tests/test_prose_facts.py
_NUM = textnum.NUM
_CN_DIGIT = textnum.CN_DIGIT
_CN_UNIT = textnum.CN_UNIT
_UNIT_MUL = textnum.UNIT_MUL
_cn_to_num = textnum.cn_to_num
_num_of = textnum.num_of


async def extract_facts(cli: Client, ch_texts: list[str]) -> list[dict]:
    """逐章并发抽事实表(flash走量)。返回与章对齐的 list[dict]。retry-on-empty。"""
    sys_p, usr_t = prompts.FACT_EXTRACT

    async def _one(t: str) -> dict:
        for k in range(3):
            raw = await cli.complete("chunk_extract", sys_p, usr_t.format(text=t[:6000]),
                                     json_mode=True, max_tokens=1500, temperature=0.1 + 0.1 * k)
            r = _safe_json(raw) or {}
            if isinstance(r, dict) and ("present" in r or "deaths" in r):
                return r
        return {}
    return list(await asyncio.gather(*[_one(t) for t in ch_texts]))


def cross_check(facts: list[dict]) -> list[dict]:
    """代码跨章对比: 生死(高置信)/数值倒退(中)/身份多值(advisory)。保守宁缺毋滥。"""
    findings: list[dict] = []
    deaths: dict[str, tuple[int, str]] = {}
    for i, f in enumerate(facts, 1):
        for d in f.get("deaths") or []:
            who = (d.get("who") if isinstance(d, dict) else str(d) or "").strip()
            if who and 2 <= len(who) <= 6 and who not in deaths:
                clue = (d.get("clue") or "") if isinstance(d, dict) else ""
                deaths[who] = (i, clue)
    for who, (dch, clue) in deaths.items():
        after = [i for i, f in enumerate(facts, 1)
                 if i > dch and who in [str(p).strip() for p in (f.get("present") or [])]]
        if after:
            findings.append({"cat": "生死", "who": who, "ch_a": dch, "ch_b": after[0],
                             "why": f"{who}第{dch}章死亡({clue}),第{after[0]}章仍在场行动",
                             "conf": "高"})
    powers: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for i, f in enumerate(facts, 1):
        for pair in f.get("power") or []:
            if not (isinstance(pair, (list, tuple)) and len(pair) >= 2):
                continue
            who, val = str(pair[0]).strip(), str(pair[1])
            v = _num_of(val)
            if who and v is not None:
                unit = _NUM.sub("#", val).strip()    # 同量纲才比(气血#卡 vs 气血#卡)
                powers.setdefault((who, unit), []).append((i, v))
    for (who, unit), seq in powers.items():
        seq.sort()
        hi: float | None = None
        hich = 0
        for ch, v in seq:
            if hi is not None and v < hi * 0.95:
                findings.append({"cat": "数值", "who": who, "ch_a": hich, "ch_b": ch,
                                 "why": f"{who}「{unit.replace('#', 'X')}」第{hich}章{hi}→第{ch}章{v}倒退",
                                 "conf": "中"})
                break
            if hi is None or v > hi:
                hi, hich = v, ch
    # identity 与 numbers 分开按来源类别走,不靠 _num_of 猜(中文数字会在'天一武堂'类名字里误触)
    id_findings: list[dict] = []
    for key, cat in (("identity", "身份"), ("numbers", "数值")):
        table: dict[str, dict[str, int]] = {}
        for i, f in enumerate(facts, 1):
            for pair in f.get(key) or []:
                if not (isinstance(pair, (list, tuple)) and len(pair) >= 2):
                    continue
                k, v = str(pair[0]).strip(), str(pair[1]).strip()
                if k and v:
                    table.setdefault(k, {}).setdefault(v, i)
        for k, vals in table.items():
            vs = list(vals.items())
            for a_i, (va, ca) in enumerate(vs):
                for vb, cb in vs[a_i + 1:]:
                    if va in vb or vb in va:         # 互为子串=同义写法,不报
                        continue
                    if cat == "数值":
                        if _MUTABLE.search(k):
                            continue                  # 语义可变量(余额/合同额) → 不报
                        na, nb = _num_of(va), _num_of(vb)
                        if na is None or nb is None or na == nb:
                            continue                  # 数字相同/解析不出 → 不报
                    id_findings.append({"cat": cat, "who": k, "ch_a": ca, "ch_b": cb,
                                        "va": va, "vb": vb,    # 结构化值(供身份真矛盾LLM裁决)
                                        "why": f"{k}: 第{ca}章「{va}」vs 第{cb}章「{vb}」",
                                        "conf": "低"})
    # 身份类放宽到4条/实体(让 LLM 真矛盾门去伪,不在此处用盲cap误杀真矛盾);数值类仍封2条
    # cap 计数键含 cat: 否则同名实体的身份findings会吃光共享计数,误删其数值findings(独立cap本意)
    cap = {"身份": 4, "数值": 2}
    per_entity: dict[tuple[str, str], int] = {}
    for f in id_findings:
        key = (f["cat"], f["who"])
        c = per_entity.get(key, 0)
        if c < cap.get(f["cat"], 2):
            findings.append(f)
            per_entity[key] = c + 1
    return findings


def _ctx(ch_texts: list[str], ch, who: str, span: int = 45) -> str:
    """取所指章内实体名首次出现处 ±span 字的上下文(供身份真矛盾裁决)。"""
    if not (isinstance(ch, int) and 1 <= ch <= len(ch_texts)):
        return ""
    t = ch_texts[ch - 1]
    i = t.find(who)
    i = i if i >= 0 else 0
    return t[max(0, i - span):i + span].replace("\n", " ")


async def verify_identity(cli: Client, findings: list[dict], ch_texts: list[str]) -> list[dict]:
    """M1.5 ①: 对身份类 findings 逐条 LLM 判真矛盾(并发),annotate f['real']。
    身份语义代码判不了(M1 命门),交 LLM 去伪——只有同维互斥的真矛盾留 real=True。
    非身份类(生死/数值)不动,real 默认 True(生死高置信、数值已确定性去噪)。"""
    sys_p, usr_t = prompts.IDENTITY_VERIFY

    async def _judge(f: dict) -> None:
        va, vb = f.get("va", ""), f.get("vb", "")
        if not (va and vb):
            f["real"] = True
            return
        usr = usr_t.format(who=f["who"], ca=f["ch_a"], va=va, cb=f["ch_b"], vb=vb,
                           ctx_a=_ctx(ch_texts, f["ch_a"], f["who"]),
                           ctx_b=_ctx(ch_texts, f["ch_b"], f["who"]))
        real = False                                  # 默认 false(存疑不报)
        for k in range(2):
            raw = await cli.complete("chunk_extract", sys_p, usr,
                                     json_mode=True, max_tokens=200, temperature=0.0 + 0.1 * k)
            r = _safe_json(raw)
            if isinstance(r, dict) and "real" in r:
                real = bool(r["real"])
                f["reason"] = str(r.get("reason", ""))[:30]
                break
        f["real"] = real

    await asyncio.gather(*[_judge(f) for f in findings if f.get("cat") == "身份"])
    for f in findings:
        f.setdefault("real", True)                    # 非身份类默认真
    return findings


async def fact_table_audit(cli: Client, ch_texts: list[str]) -> dict:
    """A2' 入口: 抽取→对比。返回 {findings, n_high(生死类数), n_unaudited}。
    A1: n_unaudited=抽取失败(空)的章数——区分"审计过=干净"与"没审到"(后者非0时 findings 不可当可信干净)。"""
    facts = await extract_facts(cli, ch_texts)
    findings = cross_check(facts)
    return {"findings": findings,
            "n_high": sum(1 for f in findings if f.get("conf") == "高"),
            "n_unaudited": sum(1 for f in facts if not f)}    # 空 dict = 该章抽取重试后仍失败


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
        print(f"[{f['cat']}]{v} {f.get('who', '')}: ch{f.get('ch_a')}「{str(f.get('quote_a', ''))[:20]}」"
              f"vs ch{f.get('ch_b')}「{str(f.get('quote_b', ''))[:20]}」 {f.get('why', '')}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(_main(sys.argv[1]))
