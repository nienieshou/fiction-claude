"""A 接线(步骤1-3): 逐 bible 罗斯特实体抽「状态/重大遭遇时间线」→ 确定性候选 → LLM verify 真矛盾 → 进交付门。

治 fact_table(实体事实:名/数值/身份/生死点)覆盖不到的 **事件双版本 / 死后在场 / 互斥重大遭遇**——
补 docs/design/load_bearing_measurement.md §2 实测的「交付门对该类失明」漏洞。

M0(scripts/event_spine_m0.py)证: **定向逐实体**抽取 2/2 枚举出真矛盾(车祸↔绑架 / 生前↔活着),
泛抽 0/2(配角被丢)。故此处必须按罗斯特定向，非泛抽。behind HIKI_SPINE(承重质量环)。
"""
from __future__ import annotations

import asyncio
import re

from .client import Client
from .gate import _safe_json

_DEATH = re.compile(r"死|去世|已故|身亡|生前|遇害|过世|丧生|亡故|罹难")
_INCIDENT = re.compile(r"车祸|绑架|被囚|重伤|坠[楼崖]|失踪|中毒|被擒|昏迷|瘫痪")

_SYS = "你是信息抽取器，忠实抽取文本显式写出的人物状态/重大遭遇，不推断、不评判、不补全。"


def roster(bible: dict) -> list[str]:
    """bible 罗斯特(主角+配角名)，去重截顶。定向抽取靠它，避免泛抽丢配角。"""
    names: list[str] = []
    p = bible.get("protagonist") or {}
    if p.get("name"):
        names.append(str(p["name"]))
    for c in (bible.get("characters") or []):
        nm = c.get("name") if isinstance(c, dict) else c
        if nm:
            names.append(str(nm))
    seen, out = set(), []
    for n in names:
        n = n.strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out[:40]


def _ch(e: dict) -> int:
    v = e.get("章") or e.get("ch") or 0
    return v if isinstance(v, int) else 0


def _st(e: dict) -> str:
    return str(e.get("状态") or e.get("state") or "")


def scan_contradictions(timelines: dict) -> list[dict]:
    """确定性候选:①死后在场(死/已故 章 之后仍非死状态在场) ②互斥重大遭遇(同人多种重大遭遇)。
    纯函数(0 LLM,可测)。候选需 _verify 去伪(假死/倒叙/合理先后)。"""
    out: list[dict] = []
    for ent, tl in (timelines or {}).items():
        rows = [e for e in (tl or []) if isinstance(e, dict)]
        rows.sort(key=_ch)
        deaths = [e for e in rows if _DEATH.search(_st(e))]
        if deaths:
            dch = min(_ch(e) for e in deaths)
            after = [e for e in rows if _ch(e) > dch and not _DEATH.search(_st(e))]
            if after:
                out.append({"entity": ent, "type": "死后在场", "conf": "高",
                            "detail": f"已故(第{dch}章)→第{_ch(after[0])}章仍「{_st(after[0])}」"})
        inc = [_st(e) for e in rows if _INCIDENT.search(_st(e))]
        if len(set(inc)) >= 2:
            out.append({"entity": ent, "type": "互斥重大遭遇", "conf": "中",
                        "detail": " | ".join(list(dict.fromkeys(inc))[:4])})
    return out


async def _chunk_events(cli: Client, chunk: str, lo: int) -> list[dict]:
    """单块穷举抽取:任何人物的 生死/重大遭遇(按 incident 维穷举,非"重要人物"过滤——M0 教训:
    40实体一次抽会稀释丢配角;按事件维分块穷举才不漏。"""
    usr = ("穷举列出本节中**任何人物**（含配角/次要人物，别漏）的 生死状态 或 重大遭遇"
           "（死亡/已故/生前/遇害/丧生/车祸/绑架/重伤/被囚/坠楼/失踪/中毒/昏迷）。无则空数组。\n"
           '输出JSON：{"events":[{"人物":"","章":数字,"状态":"","引文":"≤20字"}]}\n\n' + chunk[:20000])
    for k in range(2):
        raw = await cli.complete("chunk_extract", _SYS, usr, json_mode=True, max_tokens=2000, temperature=0.2 + 0.1 * k)
        r = _safe_json(raw) or {}
        if isinstance(r.get("events"), list):
            return r["events"]
    return []


async def _timelines(cli: Client, ch_texts: list[str]) -> dict:
    """分块(每6章)穷举抽 incident，按人物聚合成时间线。flash 走量,~10块。"""
    chunks = [(i + 1, "\n".join(f"【第{i + j + 1}章】{t}" for j, t in enumerate(ch_texts[i:i + 6])))
              for i in range(0, len(ch_texts), 6)]
    res = await asyncio.gather(*[_chunk_events(cli, c, lo) for lo, c in chunks])
    tl: dict = {}
    for evs in res:
        for e in evs:
            if isinstance(e, dict) and e.get("人物"):
                tl.setdefault(str(e["人物"]), []).append(e)
    return tl


async def _verify(cli: Client, c: dict) -> bool:
    usr = ("判断这是否网文「承重真矛盾」（假死/诈死/倒叙/回忆/双胞胎/合理时间先后 都不算矛盾）。\n"
           f"人物:{c['entity']} 类型:{c['type']} 线索:{c['detail']}\n"
           '输出JSON：{"real":true或false,"reason":"≤20字"}')
    for k in range(2):
        raw = await cli.complete("chunk_extract", "你是严格的承重矛盾判定器，存疑一律判 false。",
                                 usr, json_mode=True, max_tokens=150, temperature=0.0 + 0.1 * k)
        r = _safe_json(raw)
        if isinstance(r, dict) and "real" in r:
            c["reason"] = str(r.get("reason", ""))[:30]
            return bool(r["real"])
    return False


async def event_state_audit(cli: Client, ch_texts: list[str], bible: dict) -> dict:
    """定向抽取 → 候选 → verify。返回 {contradictions(已确认), n_real, checked, all_candidates, timelines}。"""
    tls = await _timelines(cli, ch_texts)        # 分块穷举(incident维),不靠罗斯特名单避免稀释
    cands = scan_contradictions(tls)
    if cands:
        reals = await asyncio.gather(*[_verify(cli, c) for c in cands])
        for c, r in zip(cands, reals):
            c["real"] = r
    confirmed = [c for c in cands if c.get("real")]
    return {"contradictions": confirmed, "n_real": len(confirmed), "checked": len(tls),
            "all_candidates": cands, "timelines": tls}
