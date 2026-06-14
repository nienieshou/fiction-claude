"""Tier1 全书产线：全书深挖 → 两层规划(macro→分章) → 复用切片后端起草/选优/审计。

与 slice_validate 的区别：前端换成 mining.mine_book(全书map-reduce厚bible+全局场景池+源分级)
和两层规划(PLAN_MACRO 60章骨架 → PLAN_CHAPTER 并发分章)；后端(BoN/refine/gold/控字/归一/37维)
直接复用 slice_validate 的函数。目标=回收源里本就存在的人/承重/爽点深度。
用法：python -m hiki.produce <源.txt> [--chapters 60] [--chunks 12] [-n 3]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from . import prompts, gate, ledger, audit, mining, prose_continuity, prose_facts
from .client import Client
from .ingest import ingest
from .slice_validate import (_process_scene, _fit_chapter, _truncate, _assemble,
                             _load_gold, _json, _strip_markers)


import re as _re
import collections


_DLG = _re.compile(r"[「『“\"'][^」』”\"'\n]*[」』”\"']")  # 对话引号(粗)

# R15 高潮事件关键词。强高潮词(查 title+key_events): 明确不可拆。境界词(仅查 title):
# 只有"本章标题就是该境界突破"才算高潮章——避免"配角突破金丹"等key_events噪声误伤普通章("突破"太泛已删)。
_CLIMAX_STRONG = ("飞升", "渡劫", "破虚", "九九", "天劫", "认主", "夺舍", "决战", "陨落", "合体", "大乘")
_CLIMAX_REALM = ("化神", "元婴", "结丹", "凝丹", "金丹", "筑基")


def _is_climax_ch(ch: dict) -> bool:
    title = str(ch.get("title", ""))
    blob = title + "".join(str(e) for e in (ch.get("key_events") or []))
    return any(k in blob for k in _CLIMAX_STRONG) or any(k in title for k in _CLIMAX_REALM)


def _first_person_ratio(text: str) -> float:
    """引号外叙述里第一人称占比（对话内'我'不计）。判 POV 离群章用。"""
    narr = _DLG.sub("", text)
    fp = len(_re.findall(r"我", narr))
    tp = len(_re.findall(r"[他她]", narr))
    return fp / max(1, fp + tp)


def _pov_outliers(ch_texts: list[str]):
    """返回 (全书主人称person, 需修的离群章索引)。主三人称→修一人称离群章；主一人称→不动(尊重源)。"""
    ratios = [_first_person_ratio(t) for t in ch_texts]
    first_chs = sum(1 for r in ratios if r > 0.5)
    if first_chs > len(ratios) / 2:          # 全书本就第一人称 → 不强转
        return 1, []
    outliers = [i for i, r in enumerate(ratios) if r > 0.5]   # 三人称书里的一人称离群章
    return 3, outliers


def _normalize_near_names(ch_texts: list[str], canon: set):
    """编辑距离近似名归一(治 白小雅→白小兰):用每个 canon 名的"逐位单字替换"正则找近似名。
    保守:仅当 canon 名出现≥3次、近似名更少见、近似名本身非 canon 时归一,避免误伤。"""
    full = "\n".join(ch_texts)
    fixes = {}
    for c in sorted(canon):
        if not (2 <= len(c) <= 4):
            continue
        cc = full.count(c)
        if cc < 3:                                  # 只向真实高频 canon 名归一
            continue
        for pos in range(len(c)):                   # 逐位放一个通配，找差1字的近似名
            pat = _re.escape(c[:pos]) + "[一-龥]" + _re.escape(c[pos + 1:])
            for m in set(_re.findall(pat, full)):
                if m != c and m not in canon and m not in fixes:
                    mc = full.count(m)
                    if 0 < mc < cc:                 # 近似名比 canon 名罕见 → 判笔误
                        fixes[m] = c
    if not fixes:
        return ch_texts, {}
    out = []
    for t in ch_texts:
        for w, c in fixes.items():
            t = t.replace(w, c)
        out.append(t)
    return out, fixes


def _safe_filename(name: str, fallback: str = "成品") -> str:
    """清掉 Windows 非法字符(\\ / : * ? \" < > |)+控制符，给成品起干净文件名。"""
    name = _re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name or "").strip().strip(".")
    name = _re.sub(r"\s+", " ", name)
    return name[:40] or fallback


async def _decliche_chapters(cli: Client, ch_texts: list[str], cap: int = 22):
    """Tier2 套话硬重写门：按**全书累积疲劳**定位过度复读的套话类别,重写它们聚集的章(治读者累积腻)。"""
    full = "\n".join(ch_texts)
    over_book = {lab for lab, c in audit.cliche_hits(full).items() if c >= 8}   # 全书≥8次=疲劳类
    if not over_book:
        return ch_texts, []
    scored = []
    for i, t in enumerate(ch_texts):
        h = audit.cliche_hits(t)
        inst = sum(c for lab, c in h.items() if lab in over_book)
        present = [lab for lab in h if lab in over_book]
        if inst >= 2:                               # 本章含≥2个疲劳套话实例 → 候选
            scored.append((inst, i, present))
    scored.sort(reverse=True)
    jobs = [(i, present) for _, i, present in scored[:cap]]   # 取最密的 cap 章
    if not jobs:
        return ch_texts, []
    sys_p, usr_t = prompts.DECLICHE
    res = await asyncio.gather(*[
        cli.complete("draft", sys_p, usr_t.format(cliches="、".join(present), text=ch_texts[i][:12000]),
                     max_tokens=8000, temperature=0.5) for i, present in jobs])
    done = []
    for (i, _), t in zip(jobs, res):
        t = _strip_markers(t)
        if (t and len(t) > len(ch_texts[i]) * 0.7
                and sum(audit.cliche_hits(t).values()) < sum(audit.cliche_hits(ch_texts[i]).values())):
            ch_texts[i] = t
            done.append(i)
    return ch_texts, done


def _split_head(t: str, n: int = 1200) -> tuple[str, str]:
    """在 ~n 字附近的段落边界切出"章开头"，供章缝定向重写（只动开头，其余原样拼回）。"""
    cut = t.find("\n\n", int(n * 0.6))
    if cut == -1 or cut > n * 2:
        cut = min(len(t), n * 2)
    return t[:cut], t[cut:]


async def _seam_pass(cli: Client, ch_texts: list[str], cap: int = 60):
    """章缝衔接检修（治人工头号缺陷：相邻章时空/动作倒退）。
    detect(59对尾→头并发) → 定向重写断裂章的开头段(其余原样) → 采用守卫。
    返回 (修后章文, 修复清单, 检出数)。"""
    if len(ch_texts) < 2:
        return ch_texts, [], 0
    sys_c, usr_c = prompts.SEAM_CHECK

    async def _check(i: int) -> dict:
        for t in range(3):                       # retry-on-empty(flash偶发空响应,核心flaky类)
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-700:], head=ch_texts[i][:900]),
                                     json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if "ok" in r:
                return r
        return {}                                # 3次都空 → 认衔接正常(保守不误修)
    idxs = list(range(1, len(ch_texts)))
    checks = await asyncio.gather(*[_check(i) for i in idxs])
    bad = []
    for i, r in zip(idxs, checks):
        if r.get("ok") is False:
            bad.append((i, (r.get("issue") or "").strip() or "时空/动作衔接断裂"))
    found = len(bad)
    if not bad:
        return ch_texts, [], 0
    bad = bad[:cap]
    sys_f, usr_f = prompts.SEAM_FIX
    splits = {i: _split_head(ch_texts[i]) for i, _ in bad}
    res = await asyncio.gather(*[
        cli.complete("draft", sys_f,
                     usr_f.format(prev=ch_texts[i - 1][-700:], issue=iss, head=splits[i][0]),
                     max_tokens=4000, temperature=0.4) for i, iss in bad])
    fixed = []
    for (i, iss), t in zip(bad, res):
        head, rest = splits[i]
        t = _strip_markers((t or "").strip())
        if t and len(head) * 0.5 <= len(t) <= len(head) * 2.0:   # 守卫:开头没崩才采用
            ch_texts[i] = t + rest
            fixed.append(f"第{i + 1}章:{iss[:18]}")
    return ch_texts, fixed, found


def _trim_tail(t: str, look: int = 400) -> str:
    """章尾句界强制：章末不收在句号/叹号/问号/引号上→回退到最近句界裁掉残句。
    (团宠ch56实证: _truncate的逗号兜底在章尾位置='断在逗号上'肉眼可见,章尾必须整句。)"""
    t = t.rstrip()
    if not t or t[-1] in "。！？”…":
        return t
    for i in range(len(t) - 1, max(0, len(t) - look) - 1, -1):
        if t[i] in "。！？”":
            return t[:i + 1]
    return t


_FLASHBACK_RE = _re.compile(r"(三天前|三日前|几天前|数日前|一个时辰前|时间回到|回到.{0,4}(天|日|年)前|半(天|日)前)")


async def _adj_dup_pass(cli: Client, ch_texts: list[str], cap: int = 12):
    """R11 邻章头部重演检修: 后章开头把前章已演事件重演成互斥版本(冥夙双救场/茶壶两版类)。
    M0(scripts/m0_adjdup_recall.py): 头部类召回1/1,净书误报7%且抽查多为真伤;修复=重写后章开头
    承接前章(同 seam-fix 模式,采用守卫),深处互斥不在此环(归点修)。返回 (修后, 修复清单, 检出数)。"""
    if len(ch_texts) < 2:
        return ch_texts, [], 0
    sys_c, usr_c = prompts.ADJ_DUP_CHECK

    async def _check(i: int) -> dict:
        for t in range(3):
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=ch_texts[i - 1][-1800:], head=ch_texts[i][:2200]),
                                     json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if isinstance(r, dict) and "dup" in r:
                return r
        return {}
    idxs = list(range(1, len(ch_texts)))
    checks = await asyncio.gather(*[_check(i) for i in idxs])
    bad = [(i, (r.get("issue") or "互斥重演").strip()) for i, r in zip(idxs, checks)
           if r.get("dup") is True][:cap]
    if not bad:
        return ch_texts, [], 0
    sys_f, usr_f = prompts.ADJ_DUP_FIX
    fixed = []
    rewrites = await asyncio.gather(*[
        cli.complete("draft", sys_f, usr_f.format(issue=iss, prev=ch_texts[i - 1][-1500:],
                                                  text=ch_texts[i][:14000]),
                     max_tokens=8000, temperature=0.3) for i, iss in bad])
    for (i, iss), t in zip(bad, rewrites):
        t = _strip_markers((t or "").strip())
        if t and len(t) >= len(ch_texts[i]) * 0.7:   # 采用守卫
            ch_texts[i] = t
            fixed.append(f"第{i + 1}章:{iss[:20]}")
    return ch_texts, fixed, len(bad)


def _wave_bounds(beats: list[dict], n_ch: int) -> list[tuple[int, int]]:
    """R13 波次界: act 对齐 + 确定性护栏(泛性来自护栏不来自对齐)。
    切点=act转换处;单波>12强制加切;<4并入邻波;act畸形(波数<3或>8)退化固定切口8/20/33/46。
    返回 [(start,end)) 0-based。"""
    cuts = []
    prev_act = None
    for i, b in enumerate(beats[:n_ch]):
        act = b.get("act") if isinstance(b, dict) else None
        if prev_act is not None and act and act != prev_act:
            cuts.append(i)
        if act:
            prev_act = act
    def _to_waves(cs: list[int]) -> list[tuple[int, int]]:
        pts = [0] + sorted(set(c for c in cs if 0 < c < n_ch)) + [n_ch]
        return list(zip(pts, pts[1:]))
    waves = _to_waves(cuts)
    if not (3 <= len(waves) <= 8):                   # act 畸形 → 固定切口
        waves = _to_waves([8, 20, 33, 46])
    merged: list[tuple[int, int]] = []               # 护栏①: <4 先并入邻波
    for w in waves:
        if merged and (w[1] - w[0] < 4 or merged[-1][1] - merged[-1][0] < 4):
            merged[-1] = (merged[-1][0], w[1])
        else:
            merged.append(w)
    out: list[tuple[int, int]] = []                  # 护栏②: >12 均匀分割(14→7+7,绝不产生<4的尾巴)
    for a, b in merged:
        n = b - a
        k = -(-n // 12)                              # ceil
        base, rem = n // k, n % k
        s = a
        for i in range(k):
            e = s + base + (1 if i < rem else 0)
            out.append((s, e))
            s = e
    return out


_ITEM_TERMINAL = ("碎", "毁", "耗尽", "丢失", "灰飞", "湮灭", "送出", "易主", "炸")


_MILESTONE_KW = [
    ("分娩", ("分娩", "生下", "产下", "生子", "生女", "临盆", "早产", "剖腹", "诞下", "生产", "出生")),
    ("成婚", ("完婚", "结婚", "大婚", "领证", "成婚", "婚礼", "嫁给", "迎娶", "出嫁")),
    ("离婚", ("离婚", "和离")),
    ("认亲", ("认亲", "认祖", "归宗", "相认", "身世揭", "验亲", "滴血", "亲子鉴定", "DNA")),
]


def _milestone_type(ev: str) -> str:
    """里程碑归类(同类只记首次):分娩/成婚/离婚/认亲;不匹配则用前4字。"""
    for t, kws in _MILESTONE_KW:
        if any(k in ev for k in kws):
            return t
    return ev[:4]


def _settle_facts(settled: dict, facts: list[dict], start_ch: int) -> None:
    """波间结算: extract_facts 的逐章事实并入滚动状态(只进不退,死亡/最高修为/事件)。
    R14: 物品终态账——碎/毁/耗尽类只记首次,后续波次铁律禁其完好复出(雷灵珠ch50碎→ch52复用实证)。"""
    for off, f in enumerate(facts):
        ch = start_ch + off + 1                      # 1-based
        for d in f.get("deaths") or []:
            who = (d.get("who") if isinstance(d, dict) else str(d) or "").strip()
            if who and 2 <= len(who) <= 6:
                settled["deaths"].setdefault(who, ch)
        for pair in f.get("power") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                settled["power"][str(pair[0]).strip()] = (str(pair[1])[:20], ch)
        for pair in f.get("items") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                name, state = str(pair[0]).strip(), str(pair[1]).strip()
                if name and 2 <= len(name) <= 8 and any(k in state for k in _ITEM_TERMINAL):
                    settled.setdefault("items", {}).setdefault(name, (state[:12], ch))
        for pair in f.get("milestones") or []:       # M1.5: 不可逆人生里程碑账(治孕产/婚育时间线退步)
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                who, ev = str(pair[0]).strip(), str(pair[1]).strip()
                if who and 2 <= len(who) <= 6 and ev:
                    t = _milestone_type(ev)          # 按类型去重(措辞每章不同,'分娩'类只记首次)
                    settled.setdefault("milestones", {}).setdefault(who, {}).setdefault(t, (ev[:24], ch))


def _spine_map(bible: dict) -> dict:
    """Fact Spine(M1): 从 bible 全量配角+主角编成冻结角色表 {本名:{role,aliases,rel}}。
    M0 实证: 现有 id_map 只钉身份不钉名,且长尾配角漏列→同角色多名漂移(生父4名/顾明骁↔景)。
    Spine 把全量角色的规范名+禁用别名+血缘关系编成硬约束注入起草。"""
    sm: dict = {}
    for c in (bible.get("characters") or []):
        n = (c.get("name") or "").strip()
        if not n:
            continue
        sm[n] = {"role": (c.get("role") or "").strip()[:24],
                 "aliases": [a.strip() for a in (c.get("aliases") or []) if isinstance(a, str) and a.strip() and a.strip() != n][:5],
                 "rel": (c.get("key_relation") or c.get("relation_arc") or "").strip()[:30]}
    p = bible.get("protagonist") or {}
    if (p.get("name") or "").strip():
        sm[p["name"].strip()] = {"role": str(p.get("identity") or "")[:24],
                                 "aliases": [a for a in (p.get("aliases") or []) if a][:5], "rel": "主角"}
    return sm


def _spine_block(cur: dict, spine_map: dict) -> str:
    """本章登场角色的冻结角色表(只列本章点到名/别名的角色),硬约束: 禁改名/禁新造名/身份钉死。"""
    if not spine_map:
        return ""
    ch_txt = json.dumps(cur, ensure_ascii=False)
    rows = []
    for name, info in spine_map.items():
        hit = name in ch_txt or any(a in ch_txt for a in info["aliases"])
        if not hit:
            continue
        seg = f"{name}"
        if info["rel"]:
            seg += f"〔{info['rel']}〕"
        if info["role"]:
            seg += f"={info['role']}"
        if info["aliases"]:
            seg += f"(全书只称「{name}」,禁用异名:{'/'.join(info['aliases'])})"
        rows.append(seg)
        if len(rows) >= 10:
            break
    if not rows:
        return ""
    return ("\n角色名钉死(Fact Spine·冻结,违者即承重硬伤): " + "；".join(rows)
            + "\n  铁律: 本章涉及的角色一律只用上列**本名**,**禁止为任何角色新造名字或改用别名/改写身份血缘**"
              "(治同一角色多名/同名多身份漂移);上表没有的新角色才可命名。")


def _spine_facts(bible: dict) -> str:
    """Fact Spine(M1.5 ②): 把 bible.facts(归并后的单值设定数值)编成「数值钉死」硬约束。
    M1 实证: 只钉名+身份不够,彩礼30/60/15万、年龄22/21/24 照漂——因为数值无单一真相、
    起草各编各的。此块把冻结单值注入每章起草,优先级 > brief 现编。条目少(~10),全章注入。"""
    rows = []
    for f in (bible.get("facts") or []):
        if not isinstance(f, dict):
            continue
        item, val = str(f.get("item") or "").strip(), str(f.get("value") or "").strip()
        if not (item and val):
            continue
        rule = str(f.get("rule") or "").strip()
        rows.append(f"{item}={val}" + (f"〔{rule}〕" if rule else ""))
        if len(rows) >= 16:
            break
    if not rows:
        return ""
    return ("\n数值钉死(Fact Spine·冻结单值,违者即承重数值矛盾): " + "；".join(rows)
            + "\n  铁律: 涉及上列设定数值时**只能用冻结值**(单调标记者只可按序递增,绝不写低/回退);"
              "brief 或情节需要而上表未列的数值才可自定,且全书须自洽。")


def _spine_roster(spine_map: dict) -> str:
    """M1.5③ 身份维钉死: 全书角色身份的 always-on 冻结总表(治身份漂移)。
    名钉死(_spine_block)只防「同角色多名」;身份漂移是另一类——draft 给已知角色另派身份/职务/辈分
    (顾明骁大少↔二少、秦江洲表弟↔表叔),或复用人名作新职务(周柏森 律师↔人力总监,M1.5③精读头号残留致命)。
    这些名钉死管不到,需身份维硬约束 + 「新功能角色必须另起新名」规则。"""
    rows = []
    for name, info in spine_map.items():
        tag = (info.get("role") or "").strip() or (info.get("rel") or "").strip()
        if tag:
            rows.append(f"{name}={tag}")
        if len(rows) >= 18:
            break
    if not rows:
        return ""
    return ("\n角色身份钉死(Fact Spine·全书冻结,违者即承重硬伤): " + "；".join(rows)
            + "\n  铁律: ①上列角色的身份/职业/头衔/辈分/亲属称谓一经设定全书不得变更"
              "(禁:顾家大少写成二少、表弟写成表叔、律师写成总监、哥哥写成父亲);"
              "②同一人名绝不承担两种互斥身份/职务;③需要新职务的功能性角色(某公司总监/某律师等)"
              "**必须另起新名,严禁复用上表或前文已出现过的人名**。")


def _spine_world(bible: dict) -> str:
    """M2 失效类: 世界观体系登记表(地点/势力/战力体系钉死)。
    M2 实证两持平本死于地名横跳(云城↔武边↔凤城、霖洲↔槐居↔百川致命)+战力体系乱序(金丹↔数字段)。
    名/数值钉死不覆盖非人实体——补地点/势力规范名 + 单一体系定义,治世界观漂移。"""
    out = ""
    places = [p.get("name", "").strip() for p in (bible.get("places") or [])
              if isinstance(p, dict) and p.get("name")][:12]
    facs = [f.get("name", "").strip() for f in (bible.get("factions") or [])
            if isinstance(f, dict) and f.get("name")][:8]
    sysdef = (bible.get("power_system") or "").strip()
    if places:
        out += "\n地点钉死(全书规范地名/城名,禁中途改名换城): " + "、".join(places)
    if facs:
        out += "\n势力/机构钉死(规范名,禁异名): " + "、".join(facs)
    if sysdef and sysdef not in ("无", "None"):
        out += "\n战力/体系钉死(全书唯一阶梯,禁混用别套或等级乱序/回退): " + sysdef[:220]
    if out:
        out += "\n  铁律: 涉及上列地点/势力/体系一律用规范称谓与单一体系,禁中途改地名、换公司名、混用别套战力或等级倒退。"
    return out


def _control_plane(ci: int, si: int, plan: dict, settled: dict, prev_exit: str,
                   id_map: dict | None = None, spine_map: dict | None = None,
                   spine_facts: str = "", spine_roster: str = "", spine_world: str = "") -> str:
    """R13 章级控制面(inkos控制面+WriteHERE inclusion/exclusion+autonovel病例的反面):
    事实由代码编译进起草输入,不靠模型回忆;铁律优先级>brief。
    B1-bug修(R13锚-8.8根因): inclusion(本章必演)是**章级**清单,原先每场景都注入→
    章内后场景被铁律命令重演首场景已完成的事件(团宠ch49近逐字复刻实锤)。
    改: 必演/开场前提只进首场景(si==0);后场景(si>0)把这批事件改标"已演完,绝不重演,只顺势推进"。
    R14 账本扩面(团宠三臂实证:有对账守得住/错账更糟/无账放任漂移):
    +身份账(canon,bible来源,治傅礼三版身份) +物品账(prose终态,治雷灵珠碎后复用)。"""
    chs = plan["chapters"]
    cur = chs[ci]
    inc = [str(k) for k in (cur.get("key_events") or []) if str(k).strip()][:3]
    excl: list[str] = []
    for j in range(max(0, ci - 3), ci):              # 近3章已演事件(邻章互斥重灾区)
        for k in (chs[j].get("key_events") or []):
            if str(k).strip():
                excl.append(f"第{j + 1}章已演:{str(k)[:40]}")
    dead = [f"{w}(第{c}章亡,绝不再出场)" for w, c in sorted(settled["deaths"].items(), key=lambda x: x[1])][-8:]
    pw = [f"{w}={v}(截至第{c}章)" for w, (v, c) in list(settled["power"].items())[-6:]]
    # R14 身份账: 本章场景文本里点到名的 canon 角色,身份钉死(确定性匹配,cap5防膨胀)
    ids: list[str] = []
    if id_map:
        ch_txt = json.dumps(cur, ensure_ascii=False)
        ids = [f"{n}={r}" for n, r in id_map.items() if n and n in ch_txt][:5]
    # R14 物品账: 已终结物品,禁完好复出
    items = [f"{n}(第{c}章{s},绝不再完好出现/使用)" for n, (s, c) in
             list(settled.get("items", {}).items())[-6:]]
    lines = ["【控制面·铁律(优先级高于场景brief的叙述)】"]
    if prev_exit and si == 0:                        # 开场前提=章首场景的事,后场景接的是本章前序场景
        lines.append(f"开场前提: 上一章结束于——{prev_exit[:80]};本章从此处接续。")
    if dead:
        lines.append("生死账(已结算,违者即硬伤): " + "；".join(dead))
    if pw:
        lines.append("修为/数值账(只升不降): " + "；".join(pw))
    if ids:
        lines.append("身份账(canon,全书不变,违者即硬伤): " + "；".join(ids))
    spine_on = os.environ.get("HIKI_SPINE") == "1"
    sb = _spine_block(cur, spine_map) if (spine_map and spine_on) else ""
    sb += (spine_roster + spine_facts + spine_world) if spine_on else ""
    if spine_on and settled.get("milestones"):       # M1.5: 里程碑账(不可逆,治孕产/婚育时间线退步)
        ms = []
        for w, types in list(settled["milestones"].items())[-8:]:
            ms.append(f"{w}: " + "、".join(f"{ev}(第{c}章)" for ev, c in types.values()))
        lines.append("里程碑账(已发生·不可逆,绝不退回此前状态/不重演该事件;如已分娩绝不再写未孕待产、已完婚绝不再写未婚): "
                     + "；".join(ms))
    if items:
        lines.append("物品账(已终结): " + "；".join(items))
    if inc:
        if si == 0:                                  # 章首场景才命令演出本章关键事件
            lines.append("本章必演(具体写出过程与结果): " + "；".join(inc))
        else:                                        # 后场景: 同批事件已在本章前序场景演完→禁重演
            lines.append("本章关键事件已在前序场景演出完毕(绝不重演/换角度重写,只顺势推进其后续): "
                         + "；".join(inc))
    if excl:
        lines.append("绝不重演(已在前章演出完毕,只可一句带过): " + "；".join(excl[-6:]))
    return "\n" + "\n".join(lines) + sb + "\n"


async def _plan_dedup_pass(cli: Client, plan: dict, cap: int = 16) -> list[str]:
    """R12 plan级邻章节拍查重: R11实证版本互斥重灾区=act边界(ch30-33/45-46/57-60,五本全中),
    大事件禁演只盖关键词类(渡劫/大婚),战斗/对峙/求娶类漏——相邻章场景计划判'同事件覆盖',
    后章brief注禁演(确定性标注,起草前,LLM只判不改)。"""
    chs = plan["chapters"]
    if len(chs) < 2:
        return []
    sys_p, usr_t = prompts.PLAN_DUP_CHECK

    def _digest(ch: dict) -> str:
        # R16: 喂 key_events(剧情进展信号)+brief——治邻章"同一剧情进展无推进"(ch23-24试探江清清),
        # 旧版只喂brief判不出(brief措辞不同但剧情原地踏步)。
        ke = "；".join(str(e)[:40] for e in (ch.get("key_events") or []))
        return (str(ch.get("title", "")) + " | 进展:" + ke + " | " + " ; ".join(
            str(sc.get("brief", ""))[:120] for sc in ch.get("scenes", []) if isinstance(sc, dict)))[:700]

    async def _check(j: int) -> dict:
        for t in range(3):
            raw = await cli.complete("chunk_extract", sys_p,
                                     usr_t.format(prev=_digest(chs[j - 1]), cur=_digest(chs[j])),
                                     json_mode=True, max_tokens=200, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if isinstance(r, dict) and "dup" in r:
                return r
        return {}
    idxs = list(range(1, len(chs)))
    checks = await asyncio.gather(*[_check(j) for j in idxs])
    fixed = []
    for j, r in zip(idxs, checks):
        if r.get("dup") is True and len(fixed) < cap:
            ev = (str(r.get("event") or "同一事件")).strip()[:20]
            for sc in chs[j].get("scenes", []):
                if isinstance(sc, dict):
                    sc["brief"] = (f"(铁律:「{ev}」已在上一章演出完毕,本章绝不重演/换角度重写它,"
                                   f"只写其后续推进) ") + (sc.get("brief") or "")
            fixed.append(f"第{j + 1}章:{ev}")
    return fixed


async def _verify_advisories(cli: Client, claims: list[str], bible: dict) -> list[str]:
    """R11 灰区判读: 只有'读者可感知的硬矛盾'才保留为advisory(进fc/门)。
    实证噪声类: 龙套未列(郑金花/刘长老/魔皇)、能力延伸(冰系∈水系)、goal剧情演进、口径差
    (圣经练气圆满vs正文措辞)。存疑保守: 判不出=保留。"""
    if not claims:
        return []
    sys_p, usr_t = prompts.ADVISORY_VERIFY
    bx = json.dumps({k: bible.get(k) for k in ("protagonist", "characters", "setting")},
                    ensure_ascii=False)[:2500]
    checks = await asyncio.gather(*[
        cli.complete("chunk_extract", sys_p,
                     usr_t.format(claim=str(c)[:200], bible_excerpt=bx),
                     json_mode=True, max_tokens=200, temperature=0.1) for c in claims[:12]])
    out = []
    for c, r in zip(claims, checks):
        v = gate._safe_json(r) or {}
        if v.get("real") is not False:               # 只滤明确判否的
            out.append(c)
    return out


def _flashback_advisory(ch_texts: list[str]) -> list[str]:
    """确定性倒叙标记扫描(advisory): 章首即倒叙='ch41三天前重演颁奖典礼'型重演的直接信号。
    注: 曾试过'章级场合摘要→LLM查重'检测重演,在已知病书上零检出(章级表征看不见章内重演),
    已删——不可靠的检测器不能进交付门,防重演靠规划层铁律⑪⑫+邻章节拍注入,本扫描只做哨兵。"""
    out = []
    for i, t in enumerate(ch_texts):
        m = _FLASHBACK_RE.search(t[:200])
        if m:
            out.append(f"第{i + 1}章开头即倒叙({m.group()})——疑似重演前章事件")
    return out


def _handoff(jobs: list, plan: dict, i: int) -> str:
    """给场景 i 注入"紧邻前文"握手（上一场景 brief；跨章再附上一章 exit_state），治章缝倒退。"""
    if i == 0:
        return ""
    ci = jobs[i][0]
    pci, _, psc = jobs[i - 1]
    parts = [psc.get("brief") or ""]
    if pci != ci:
        ex = (plan["chapters"][pci].get("exit_state") or "").strip()
        if ex:
            parts.append(f"上一章收束状态:{ex}")
    txt = "；".join(x for x in parts if x)
    return f"\n紧邻前文(本场景开场必须从此接续,时空/动作不得倒退): {txt}" if txt else ""


def _title_ok(t: str) -> bool:
    """书名合法性守卫：必须像书名不像简介片段（治 setting[:12] 残句类 bug）。"""
    t = (t or "").strip()
    if not (3 <= len(t) <= 16):
        return False
    if any(c in t for c in "。，、…；"):                # 描述句标点=简介(冒号放行:主副标题是合法网文命名)
        return False
    if t[0].isdigit():                                  # "1970年代饥荒背景，女" 类残句
        return False
    if any(w in t for w in ("背景", "设定", "题材", "语域", "世界观", "主角", "复写")):
        return False
    return True


async def gen_title(cli: Client, bible: dict, ending: str = "") -> dict:
    """给复写新书起商业书名+卖点（flash，便宜）。喂实际结尾→书名/卖点贴真实结局(治承诺落空)。
    带重试+合法性守卫(flash 偶发吐空/吐残句)；兜底用主角名,绝不用 setting 描述片段当书名。"""
    p = bible.get("protagonist", {})
    sys_p, usr_t = prompts.TITLE
    usr = usr_t.format(
        protagonist=f"{p.get('name','')}/{p.get('identity','')}/{p.get('goal','')}",
        conflict=bible.get("central_conflict", ""), setting=bible.get("setting", ""),
        voice=bible.get("voice", ""), ladder=bible.get("escalation_ladder", ""),
        ending=ending[-3000:] or "（无）")
    r: dict = {}
    for t in range(3):                                  # 空/残句书名 → 重试(与其余 flaky 类同处理)
        raw = await cli.complete("plan_chapter", sys_p, usr,
                                 json_mode=True, max_tokens=2000, temperature=0.8 + 0.05 * t)
        r = gate._safe_json(raw) or {}
        if _title_ok(r.get("title", "")):
            return r
    name = (p.get("name") or "").strip()                # 三次仍不合法 → 主角名兜底,绝不拿 setting 描述
    fb = f"{name}的逆袭" if name else "绝世逆袭"
    return {"title": _safe_filename(fb), "tagline": r.get("tagline", ""), "alts": r.get("alts", [])}


async def _plan_macro(cli: Client, bible: dict, scenes: list[dict], n_ch: int, tries: int = 3) -> dict:
    """60章节拍图。pro 思考模式偶发吐空/截断 → 重试（与 reduce 同病）。"""
    sys_p, usr_t = prompts.PLAN_MACRO
    listed = "\n".join(
        f"{i}. [{sc.get('scene_type','')}/{sc.get('importance','')}] {sc.get('summary','')[:70]}"
        for i, sc in enumerate(scenes))
    bible_txt = json.dumps({k: bible.get(k) for k in
                            ("central_conflict", "escalation_ladder", "setting",
                             "protagonist", "factions")}, ensure_ascii=False)[:8000]
    usr = usr_t.format(n_ch=n_ch, bible=bible_txt, scenes=listed)
    best = {"chapters": []}
    for t in range(tries):
        raw = await cli.complete("plan_macro", sys_p, usr,
                                 json_mode=True, max_tokens=32000, temperature=0.4 + 0.1 * t)
        m = gate._safe_json(raw) or {}
        chs = m.get("chapters") or []
        if len(chs) >= int(n_ch * 0.8):             # 出≥80%章节才算成功(精简字段后60章应能整出)
            return m
        if len(chs) > len(best["chapters"]):
            best = m
    return best


async def _plan_one_chapter(cli: Client, beat: dict, scenes: list[dict], bible_brief: str,
                            tries: int = 2, prev_beat: str = "（无）", next_beat: str = "（无）",
                            prev_exit: str = "") -> dict:
    idx0 = beat.get("i", beat.get("index", 0))
    refs = [r for r in (beat.get("refs") or beat.get("source_scene_refs") or [])
            if isinstance(r, int) and 0 <= r < len(scenes)]
    sc_txt = "\n".join(f"[{r}] {scenes[r].get('summary','')} | 留:{scenes[r].get('key_excerpt','')}"
                       for r in refs) or "（无指定源场景，按节拍自行演绎）"
    sys_p, usr_t = prompts.PLAN_CHAPTER
    ch = {}
    for t in range(tries):                          # 单章偶发flaky→重试,防整章丢失致书变短
        raw = await cli.complete("plan_chapter", sys_p,
                                 usr_t.format(beat=json.dumps(beat, ensure_ascii=False)[:1500],
                                              scenes=sc_txt, bible_brief=bible_brief, index=idx0,
                                              prev_beat=prev_beat, next_beat=next_beat,
                                              prev_exit=prev_exit or "（未知,以上一章节拍收束处为准）"),
                                 json_mode=True, max_tokens=6000, temperature=0.5 + 0.1 * t)
        ch = gate._safe_json(raw) or {}
        if ch.get("scenes"):
            break
    for sc in ch.get("scenes", []):                 # 回填 source_ref 供起草学事件
        idx = sc.get("source_scene_index")
        if isinstance(idx, int) and 0 <= idx < len(scenes):
            s = scenes[idx]
            sc["source_ref"] = f"{s.get('key_excerpt','')} {s.get('summary','')}"
    ch.setdefault("index", idx0)
    ch.setdefault("title", (beat.get("beat") or beat.get("main_thread_beat") or "")[:20])
    ch.setdefault("scenes", [])
    ch.setdefault("end_hook", "")
    ch.setdefault("exit_state", "")
    ch.setdefault("start_state", "")
    return ch


async def _handshake_pass(cli: Client, plan: dict, beats: list[dict], scenes: list[dict],
                          bible_brief: str, cap: int = 20):
    """R8 plan层章间握手(M0实证: 章缝主源在plan节拍跳跃,prose缝合只能抹平句面→下沉到plan治根)。
    并行分章使第j+1章规划时看不见第j章exit_state → 规划后逐对flash判接续,
    断裂章带着上一章**真实exit_state**定向重规划(流程确定性,判读flash,宁放过不误报)。
    返回 (plan, 检出数, 重规划成功数)。"""
    chs = plan["chapters"]
    if len(chs) < 2 or not beats:
        return plan, 0, 0
    sys_h, usr_h = prompts.HANDSHAKE_CHECK

    async def _check(j: int) -> dict:
        prev, cur = chs[j - 1], chs[j]
        sc0 = (cur.get("scenes") or [{}])[0]
        brief = ((sc0.get("brief") if isinstance(sc0, dict) else str(sc0)) or "")[:300]
        for t in range(3):                           # retry-on-empty
            raw = await cli.complete("chunk_extract", sys_h,
                                     usr_h.format(prev_exit=prev.get("exit_state") or "（未知）",
                                                  hook=prev.get("end_hook") or "（无）",
                                                  start=cur.get("start_state") or "（未填）",
                                                  brief=brief or "（无）"),
                                     json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if "ok" in r:
                return r
        return {}                                    # 3次空 → 认衔接正常(保守不误修)

    idxs = list(range(1, len(chs)))
    checks = await asyncio.gather(*[_check(j) for j in idxs])
    bad = [j for j, r in zip(idxs, checks) if r.get("ok") is False][:cap]
    if not bad:
        return plan, 0, 0

    def _bb(b: dict) -> str:
        return (b.get("beat") or "")[:60] or "（无）"

    def _beat_for(j: int) -> dict:                   # 章→macro节拍: 按index对齐,丢章时退位置
        want = chs[j].get("index")
        cand = [b for b in beats if isinstance(b, dict)]
        if not cand:
            return {}
        return next((b for b in cand if b.get("i", b.get("index")) == want),
                    cand[min(j, len(cand) - 1)])
    replans = await asyncio.gather(*[
        _plan_one_chapter(cli, _beat_for(j), scenes, bible_brief,
                          prev_beat=_bb(_beat_for(j - 1)),
                          next_beat=_bb(_beat_for(j + 1)) if j + 1 < len(chs) else "（本章是全书结局）",
                          prev_exit=chs[j - 1].get("exit_state") or "")
        for j in bad])
    fixed = 0
    for j, nc in zip(bad, replans):
        if nc.get("scenes"):                         # 重规划flaky → 保留原章,不丢章
            chs[j] = nc
            fixed += 1
    return plan, len(bad), fixed


async def run(src: Path, n_ch: int = 60, n_chunks: int = 12, n_cand: int = 3,
              refine_rounds: int = 5, min_grade: str | None = None,
              out_dir: Path | None = None) -> dict:
    t0 = time.time()
    out_dir = out_dir or (Path("output") / (src.stem + "_full"))   # M3: best-of-K 并行跑用独立目录
    meta = ingest(src, out_dir / "source")
    clean = (out_dir / "source" / "clean.txt").read_text(encoding="utf-8")
    print(f"源 {meta.approx_wan_zi}万字/{meta.chapter_count}章 → 全书深挖({n_chunks}窗)")

    cli = Client()
    # 1) 全书深挖：map-reduce 厚bible + 全局场景池(打分筛选) + REDUCE后源分级
    keep_scenes = int(n_ch * 1.4)                       # ~1.4 场景/章
    mined = await mining.mine_book(cli, clean, n_chunks, keep_scenes)
    bible, scenes, grade = mined["bible"], mined["scenes"], mined["grade"]
    p = bible.get("protagonist", {})
    # 厚 bible 无效 = 抽取/归并管道失败（flaky），绝不当成"源质量差"拒收 → 显式报错
    if not mining._bible_ok(bible):
        raise RuntimeError(f"REDUCE 失败：厚 bible 无效（主角/中心冲突缺失），非源质量问题。"
                           f"已重试仍空，请重跑。bible={json.dumps(bible, ensure_ascii=False)[:300]}")
    print(f"语域:{bible.get('voice','')} | 主角:{p.get('name')}({p.get('gender')}) "
          f"目标:{p.get('goal','')[:20]}")
    print(f"中心冲突:{bible.get('central_conflict','')[:40]}")
    print(f"全局场景 {mined['all_scene_count']}→筛{len(scenes)} | 源分级:{grade.get('grade')}"
          f"/{grade.get('mode')} 主角弧:{grade.get('protagonist_arc','?')} "
          f"暗黑预扫:{grade.get('source_dark_ratio', 0)} 风险:{grade.get('risk','')}")
    below_floor = (min_grade
                   and mining._GRADE_ORDER.index(grade.get("grade") or "B")
                   > mining._GRADE_ORDER.index(min_grade))
    if grade.get("grade") == "Q" or grade.get("mode") == "拒收" or below_floor:
        why = f"低于源门槛{min_grade}" if below_floor and grade.get("grade") != "Q" else "达不到85"
        report = {"source": src.name, "grade": grade, "rejected": True, "reject_why": why,
                  "cost_cny": round(cli.cost_cny, 2)}
        (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"⚠ 源分级={grade.get('grade')} → 拒收（{why}）。成本¥{cli.cost_cny:.2f}")
        return report

    # 把 agency 素材并进 arc，让起草的"主动"有真材料（决策:人维洼地）
    if p.get("agency_examples"):
        p["arc"] = (p.get("arc", "") + " | 主动事例:" + "；".join(p["agency_examples"][:3]))[:200]

    # 2) 两层规划：macro 60章节拍图 → 分章并发
    macro = await _plan_macro(cli, bible, scenes, n_ch)
    beats = macro.get("chapters", [])[:n_ch]
    if len(beats) < int(n_ch * 0.7):
        raise RuntimeError(f"PLAN_MACRO 失败：仅 {len(beats)}/{n_ch} 章节拍（flaky 截断），已重试仍不足，请重跑。")
    if len(beats) < n_ch:
        print(f"⚠ macro 仅 {len(beats)}/{n_ch} 章（截断残留），继续但成书略短")
    dropped = [str(d)[:20] for d in (macro.get("dropped_threads") or []) if d][:8]
    print(f"macro:{len(beats)}章 主线={macro.get('central_conflict','')[:30]}"
          f" | 砍线保肉:{dropped or '无'} → 分章并发...")
    bible_brief = json.dumps({"protagonist": {k: p.get(k) for k in ("name", "gender", "goal", "arc")},
                              "characters": [{"name": c.get("name"), "goal": c.get("goal")}
                                             for c in bible.get("characters", [])[:8]],
                              "setting": bible.get("setting")}, ensure_ascii=False)[:3000]
    if os.environ.get("HIKI_SPINE") == "1":             # Fact Spine: 规划也喂全量冻结角色名表(plan 用规范名)
        roster = "；".join(f"{n}={i['role']}" + (f"〔{i['rel']}〕" if i['rel'] else "")
                           for n, i in _spine_map(bible).items())[:2500]
        bible_brief += ("\n【冻结角色表(全书规范名,规划与命名只用这些本名,禁新造同义角色)】\n" + roster)
        facts_line = "；".join(f"{f.get('item')}={f.get('value')}" for f in (bible.get("facts") or [])
                              if isinstance(f, dict) and f.get("item") and f.get("value"))[:1500]
        if facts_line:
            bible_brief += ("\n【冻结设定数值(全书单值,节拍涉及时只用这些值)】\n" + facts_line)
    def _beat_brief(b: dict) -> str:
        return (b.get("beat") or "")[:60] or "（无）"
    plan_chs = await asyncio.gather(*[
        _plan_one_chapter(cli, b, scenes, bible_brief,
                          prev_beat=_beat_brief(beats[j - 1]) if j > 0 else "（本章是开篇）",
                          next_beat=_beat_brief(beats[j + 1]) if j < len(beats) - 1 else "（本章是全书结局）")
        for j, b in enumerate(beats)])
    plan = {"chapters": [c for c in plan_chs if isinstance(c, dict) and c.get("scenes")]}
    for c in plan["chapters"]:                       # 第13鲁棒类: flaky LLM把场景吐成str→.get崩整本
        c["scenes"] = [s for s in c["scenes"] if isinstance(s, dict)]
    plan["chapters"] = [c for c in plan["chapters"] if c["scenes"]]
    # R10消融: 握手两轮(R8/R9)零正效——每书检出/重规划全量20(cap撞顶=过敏),churn了1/3的plan
    # 而章缝检出未降、R9锚-4.2。默认关,留 HIKI_HANDSHAKE=1 单变量验证。
    hs_found = hs_fixed = 0
    if os.environ.get("HIKI_HANDSHAKE") == "1":
        plan, hs_found, hs_fixed = await _handshake_pass(cli, plan, beats, scenes, bible_brief)
        if hs_found:
            print(f"plan握手: {hs_found} 处开场不接续 → 带上章exit_state重规划 {hs_fixed} 章")
    ordered = [sc for ch in plan["chapters"] for sc in ch["scenes"]]
    n_scenes = len(ordered)
    if n_scenes == 0:
        raise RuntimeError("PLAN_CHAPTER 全失败：无任何可起草场景（flaky），请重跑。")
    dup_removed = ledger.dedup_first_meetings(ordered)   # 治重复初遇:清后续重复标记→前情账本准
    if dup_removed:
        print(f"确定性去重: 清掉 {dup_removed} 个重复初遇/重复登场标记")
    ev_fixed = audit.fix_event_unique(plan)              # R10 大事件唯一(团宠渡劫4遍=macro排重实证)
    if ev_fixed:
        print(f"确定性禁演: {len(ev_fixed)} 处大事件重演标记: {ev_fixed[:4]}")
    plan_dups = await _plan_dedup_pass(cli, plan)        # R12 邻章节拍查重(act边界版本互斥shift-left)
    if plan_dups:
        print(f"plan邻章查重: {len(plan_dups)} 处同事件覆盖→后章注禁演: {plan_dups[:5]}")
    ent_fixed = audit.fix_entourage(bible, ordered)      # 维2 shift-left:随从阵营钉回canon再起草
    if ent_fixed:
        print(f"确定性修复: {ent_fixed} 个随从阵营钉回canon(治串线,免交付门误拦)")
    pw_fixed = audit.fix_power_monotonic(bible, ordered)  # 维5 shift-left:修为只升不降钉进plan
    if pw_fixed:
        print(f"确定性修复: {len(pw_fixed)} 个修为回退钉回当前最高(治正文修为乱序): {pw_fixed[:4]}")
    for ch in plan["chapters"]:                          # 章尾钩纪律(治'每章结尾钩子弱')
        hk = (ch.get("end_hook") or "").strip()
        if hk and ch["scenes"]:
            last = ch["scenes"][-1]
            last["brief"] = (last.get("brief") or "") + f"；本章必须收在钩子上:{hk}(结尾留悬念/危机,不写圆满收场)"
    # R15 语义双版本治根(ch14讨债/ch59飞升各两版实证: plan把高潮拆2场景,两场景brief都覆盖高潮→
    # 起草各演一遍;R13c前置标注/R14检测拦截只止损不治本——根在场景2 brief仍含高潮指令)。
    # 高潮章: 场景2+的brief**整个替换**为纯收束(删掉原高潮指令,起草看不到"再演高潮")+强制SUMMARIZE压缩。
    # 非高潮章: 保留R13c前置标注(边际有效)。
    climax_chs = intra_dup = 0
    for ch in plan["chapters"]:
        scs = ch["scenes"]
        if len(scs) < 2:
            continue
        if _is_climax_ch(ch):                        # 高潮章: 首场景演透, 其余只写后续
            core = (scs[0].get("brief") or str(ch.get("title", "")))[:50]
            for k in range(1, len(scs)):
                scs[k]["mode"] = "SUMMARIZE"
                scs[k]["brief"] = (f"(铁律: 本章高潮「{core}」已在第一个场景完整演出。本场景**严禁**以任何措辞"
                                   f"重写/重演/换角度复述该高潮过程; 只写它**之后**的直接后果——他人反应/"
                                   f"主角状态/一两句收束或转场, 压缩带过, 绝不再展开高潮本身)")
            climax_chs += 1
        else:                                        # 非高潮章: R13c 前置标注
            for k in range(1, len(scs)):
                pb = (scs[k - 1].get("brief") or "").strip()[:60]
                if pb:
                    scs[k]["brief"] = (f"(铁律:上一场景已把「{pb}」完整演出——本场景从其结束状态顺势推进，"
                                       f"绝不从头重写/换机制重演/换角度复述该事件) ") + (scs[k].get("brief") or "")
                    intra_dup += 1
    if climax_chs:
        print(f"R15高潮章单场景化: {climax_chs} 章(高潮后续场景强制收束+SUMMARIZE)")
    if intra_dup:
        print(f"章内禁重演标注(非高潮): {intra_dup} 个次场景")

    # 规划产物落盘(Tier3): 复评/选优点修/B实验都要"同plan重起草",规划不再是一次性中间态
    for nm, obj in (("bible", bible), ("macro", macro), ("plan", plan)):
        (out_dir / f"{nm}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    # 2.5) 承重确定性审计（advisory，60章不做昂贵全局re-plan；靠注入前情账本+归一兜底）
    det_struct = {k: v for k, v in audit.deterministic_audit(bible, ordered).items() if v}
    print(f"规划:{len(plan['chapters'])}章/{n_scenes}场景 | 承重硬检残留={sum(len(v) for v in det_struct.values())} → 起草...")

    # 3) 并发起草所有场景（注入圣经+前情账本；造峰：开篇+富场景给大N+金标精修）
    spc = max(1.0, n_scenes / max(1, len(plan["chapters"])))
    target = int(3500 / spc * 0.92)
    jobs = [(ci, si, sc) for ci, ch in enumerate(plan["chapters"]) for si, sc in enumerate(ch["scenes"])]

    def _rich(sc: dict) -> int:
        idx = sc.get("source_scene_index")
        s = scenes[idx] if isinstance(idx, int) and 0 <= idx < len(scenes) else {}
        return len(s.get("payoffs", [])) + len(s.get("hooks", []))
    rich = [_rich(sc) for _, _, sc in jobs]
    n_peaks = max(2, n_scenes // 12)
    peaks = {0} | set(sorted(range(len(jobs)), key=lambda i: rich[i], reverse=True)[:n_peaks])
    gold = _load_gold(bible.get("voice", ""))
    n_peak = n_cand + 5
    n_per = [n_peak if i in peaks else n_cand for i in range(len(jobs))]
    print(f"造峰:{len(peaks)}场用N={n_peak}+金标{refine_rounds}轮,其余N={n_cand}|金标={'有' if gold else '无'}")
    # R9: 跨章并行、**章内顺序**——场景2+带本章已写实际正文起草(治R8头号类'章内多版本重演':
    # 白月光ch1双开场/星际坠机两遍/狂医同章矛盾,根因=章内场景并行起草互不知情。章均1.4场景,墙钟代价极小)
    starts: list[int] = []
    _acc = 0
    for ch in plan["chapters"]:
        starts.append(_acc)
        _acc += len(ch["scenes"])

    # R13: 分幕波次起草+事实结算——波内并行、波间结算(AI_NovelGenerator"定稿即结算"闸门思路);
    # 控制面(entry_facts/inclusion/exclusion)由代码编译进每章起草输入,铁律优先级>brief。
    settled: dict = {"deaths": {}, "power": {}, "items": {}}
    # R14 身份账源: canon 角色名→身份(角色role+阵营),主角也入账(治傅礼ch2太一宗代理宗主类硬伤)
    id_map: dict = {}
    for c in bible.get("characters", []):
        n, role, fac = (c.get("name") or "").strip(), (c.get("role") or "").strip(), (c.get("faction") or "").strip()
        if n and role:
            id_map[n] = (role + (f"({fac})" if fac and fac not in role else ""))[:24]
    if p.get("name") and p.get("identity"):
        id_map[p["name"].strip()] = str(p["identity"])[:24]
    spine_map = _spine_map(bible)                        # Fact Spine(M1,HIKI_SPINE=1): 冻结全量角色名表
    spine_facts = _spine_facts(bible)                    # M1.5 ②: 冻结单值设定数值(彩礼/年龄/婚龄...)
    spine_roster = _spine_roster(spine_map)              # M1.5 ③: 冻结角色身份总表(治身份维漂移)
    spine_world = _spine_world(bible)                     # M2 失效类: 地点/势力/战力体系登记表(治世界观漂移)
    if os.environ.get("HIKI_SPINE") == "1":
        print(f"Fact Spine: 冻结 {len(spine_map)} 角色规范名 + {len(bible.get('facts') or [])} 数值设定"
              f" + {len(bible.get('places') or [])} 地点 + 身份/体系钉死")

    async def _draft_chapter(ci: int) -> list[str]:
        parts: list[str] = []
        prev_exit = (plan["chapters"][ci - 1].get("exit_state") or "") if ci > 0 else ""
        for si, sc in enumerate(plan["chapters"][ci]["scenes"]):
            i = starts[ci] + si
            plane = _control_plane(ci, si, plan, settled, prev_exit, id_map, spine_map,
                                   spine_facts, spine_roster, spine_world)  # +Spine名/数值/身份/地点·体系钉死
            ctx = (ledger.format_context(ledger.state_before(ordered, i)) + _handoff(jobs, plan, i)
                   + plane)
            if parts:
                ctx += ("\n【本章已写前文(其中事件已发生,绝不重演/换角度重写,直接顺势接续)】\n"
                        + "\n\n".join(parts)[-4000:])
            res = await _process_scene(cli, sc, bible, bible.get("voice", "网文白话"), target,
                                       n_per[i], gold=gold, is_peak=(i in peaks),
                                       refine_rounds=refine_rounds, context=ctx)
            parts.append(res["winner"])
        return parts

    waves = _wave_bounds(beats, len(plan["chapters"]))
    print(f"波次: {len(waves)} 波 {[(a + 1, b) for a, b in waves]} (act对齐+护栏)")
    ch_texts = []
    for wi, (wa, wb) in enumerate(waves):
        wave_parts = await asyncio.gather(*[_draft_chapter(ci) for ci in range(wa, wb)])
        wave_texts = ["\n\n".join(p) for p in wave_parts]
        ch_texts += wave_texts
        if wb < len(plan["chapters"]):               # 末波不结算(无下游)
            wfacts = await prose_facts.extract_facts(cli, wave_texts)
            _settle_facts(settled, wfacts, wa)
            print(f"  波{wi + 1}({wa + 1}-{wb}章)结算: 生死账{len(settled['deaths'])} 修为账{len(settled['power'])} "
                  f"里程碑账{sum(len(v) for v in settled.get('milestones', {}).values())}")

    # 4) 后端：双向控字 + 硬截断 + POV统一 + 人名归一(双名守卫+近似名) + advisory连续性
    ch_texts = await asyncio.gather(*[_fit_chapter(cli, t, 3500) for t in ch_texts])
    short = [i for i, t in enumerate(ch_texts) if len(t) < 3500 * 0.7]   # 扩写flaky残留→再试一次
    if short:                                                            # (过短≥3章会被交付门拦)
        refit = await asyncio.gather(*[_fit_chapter(cli, ch_texts[i], 3500) for i in short])
        for i, t in zip(short, refit):
            ch_texts[i] = t
        print(f"控字: {len(short)} 章过短二次扩写")
    # 末章给1.6×上限(治断尾: 硬截断会把结局收束拍切掉,Fable预评坐实'最后一句是高潮中断')
    ch_texts = [_truncate(t, int(3500 * (1.6 if i == len(ch_texts) - 1 else 1.15)))
                for i, t in enumerate(ch_texts)]
    # 4a) POV：把误用人称的离群章统一回全书主人称(治整章第一人称误用)
    person, outliers = _pov_outliers(ch_texts)
    if outliers:
        print(f"POV: 第{person}人称书，{len(outliers)}个离群章定向重写: {outliers}")
        sys_pv, usr_pv = prompts.POV_FIX
        fixed = await asyncio.gather(*[
            cli.complete("draft", sys_pv, usr_pv.format(person=person, name=p.get("name", "他"),
                                                        text=ch_texts[i]),
                         max_tokens=8000, temperature=0.3) for i in outliers])
        for i, t in zip(outliers, fixed):
            t = _strip_markers(t)
            if t and _first_person_ratio(t) < 0.5:    # 修成功才采用
                ch_texts[i] = t
    # 4a2) Tier2 套话硬重写门
    ch_texts, decliche_done = await _decliche_chapters(cli, ch_texts)
    if decliche_done:
        print(f"去套话门: 重写 {len(decliche_done)} 章")
    valid_names = set()
    for nm in [p.get("name", "")] + (p.get("aliases") or []):
        for part in str(nm).replace("、", "/").split("/"):
            if part.strip():
                valid_names.add(part.strip())
    for c in bible.get("characters", []):
        if c.get("name"):
            valid_names.add(c["name"].strip())
        for a in c.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                valid_names.add(a.strip())
    # 4b) 人名一致：靠 REDUCE 别名合并 + 下面 continuity_check(LLM, 安全归一到canon)。
    #     确定性编辑距离归一在中文里误报灾难性(强大→强森) → 已弃用。
    final = _assemble(plan, ch_texts)
    cont = await gate.continuity_check(cli, final[:60000], bible)
    applied = []
    for f in (cont.get("name_fixes") or []):
        w, r = (f.get("wrong") or "").strip(), (f.get("right") or "").strip()
        # 只归一到**冻结 canon 名**：r 必须是合法名，否则 LLM 可能返回指令串/解释 → 污染正文
        if w and r and w != r and w not in valid_names and r in valid_names and len(r) <= 8:
            ch_texts = [t.replace(w, r) for t in ch_texts]
            applied.append(f"{w}→{r}")
    # 4c) PROSE 层连续性(治 plan 审计够不到的:同人异名漂移 + 死人复活)——作用在生成正文上
    ch_texts, prose_rep = await prose_continuity.audit_and_repair(cli, ch_texts, canon_names=valid_names,
                                                                  source_text=clean)
    print(f"prose连续性: 异名归一={prose_rep['prose_name_fixes']} | 复活修复={prose_rep['prose_revivals_fixed']}")
    # 4d) PROSE 内容过滤(治暗黑厌女:bible级content_flag失灵,读实际场景净化)
    ch_texts, dark_rep = await prose_continuity.content_filter(cli, ch_texts)
    values_reject = dark_rep["dark_ratio"] > 0.25      # 暗黑饱和(>25%章)→净化救不动,应拒收
    if dark_rep["dark_fixed"] != ["无"]:
        print(f"内容过滤: 净化 {len(dark_rep['dark_fixed'])} 章 (暗黑比{dark_rep['dark_ratio']}"
              f"{'→暗黑饱和,标记拒收' if values_reject else ''})")
    # 4e) 章缝衔接检修(人工头号缺陷:相邻章时空/动作倒退,如'前章已开车,后章才拿钥匙')
    ch_texts, seam_fixed, seam_found = await _seam_pass(cli, ch_texts)
    if seam_found:
        print(f"章缝: 检出 {seam_found} 处断裂, 修复 {len(seam_fixed)} 处: {seam_fixed}")
    # 4e2) R11 邻章事件版本互斥检修(缺陷类演化: 整章重演→同章双版本→邻章双版本;
    #      M0限界: 只管后章**头部**重演(检出→重写开头,采用守卫),深处互斥归点修通道)
    ch_texts, adj_fixed, adj_found = await _adj_dup_pass(cli, ch_texts)
    if adj_found:
        print(f"邻章版本: 检出 {adj_found} 对头部重演, 修复 {len(adj_fixed)} 对: {adj_fixed[:6]}")
    # 4f) 结尾收束守卫(治断尾: 末章高潮处戛然而止/无收束拍; 另判'预告事件被时间跳跃跳过')
    ending_fixed, climax_skipped = "", ""
    sys_ec, usr_ec = prompts.ENDING_CHECK
    prev_tail = ch_texts[-2][-800:] if len(ch_texts) >= 2 else "（无）"
    for t in range(3):                            # retry-on-empty
        raw = await cli.complete("chunk_extract", sys_ec,
                                 usr_ec.format(prev_tail=prev_tail, tail=ch_texts[-1][-2500:]),
                                 json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
        ec = gate._safe_json(raw) or {}
        if "ok" in ec:
            break
    else:
        ec = {}
    if ec.get("skipped") is True:                 # 兑现跳空没法补写一场大战 → 交付门拦
        climax_skipped = (ec.get("skipped_what") or "预告事件").strip()
        print(f"结尾守卫: 预告事件被跳过({climax_skipped}) → 计入交付门")
    if ec.get("ok") is False:
        prob = (ec.get("problem") or "结尾被截断").strip()
        sys_ef, usr_ef = prompts.ENDING_FIX
        # 第14鲁棒类(变量遮蔽): 这里曾复用变量名 cont,覆盖了4b的continuity dict →
        # 605行 cont.get 崩——白月光/末世×2 三次"补收束拍的书必崩"的根因
        tail_fix = await cli.complete("draft", sys_ef, usr_ef.format(problem=prob, tail=ch_texts[-1][-2500:]),
                                      max_tokens=2000, temperature=0.5)
        tail_fix = _strip_markers((tail_fix or "").strip())
        if 100 <= len(tail_fix) <= 1500:          # 守卫:收束拍合理长度才追加
            ch_texts[-1] = ch_texts[-1].rstrip() + "\n\n" + tail_fix
            ending_fixed = prob
            print(f"结尾守卫: 检出断尾({prob}) → 已补收束拍{len(tail_fix)}字")
    # 4g) 倒叙哨兵(确定性advisory): 章首即倒叙=重演前章事件的直接信号
    flashbacks = _flashback_advisory(ch_texts)
    if flashbacks:
        print(f"倒叙哨兵: {flashbacks}")
    # 4h) 章尾句界强制(残句裁掉,治'断在逗号上')
    ch_texts = [_trim_tail(t) for t in ch_texts]
    # 4i) R8 A2' 事实表对账(advisory,召回36%不进门;生死高置信+数值倒退=承重头号类的便宜哨兵,
    #     identity低置信只留 fact_table.json 供点修,不进摘要防称谓噪声淹没)
    ft_deaths_verified: list[dict] = []
    fact_table_ok = False
    spine_net_num, spine_net_id = 0, 0               # §3.6 Spine薄网: 起草违反冻结事实的残漏(对照后进交付门)
    try:
        ft = await prose_facts.fact_table_audit(cli, ch_texts)
        # R9: 生死候选过 PROSE_REVIVAL_VERIFY 才计入门——常规题材3/3真,但死遁/重生题材1/3
        # (白月光实测: 归墟亡魂/尸体在场被误判),verify滤假死/亡魂/提及,存疑判否
        cand = [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
                 "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
                for f in ft["findings"] if f.get("cat") == "生死"
                and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(ch_texts)]
        if cand:
            ft_deaths_verified = await prose_continuity.verify_revivals(cli, ch_texts, cand)
        if ft_deaths_verified:                        # R9b: 拦不如修——verify过的复活直喂已验证修复器,
            ch_texts = await prose_continuity.repair_revivals_smart(cli, ch_texts, ft_deaths_verified)
            residual = await prose_continuity.verify_revivals(cli, ch_texts, ft_deaths_verified)
            print(f"事实表生死: {len(ft_deaths_verified)} 处verify确认 → 定向修复 → 残留{len(residual)}")
            ft_deaths_verified = residual             # 只有修不掉的才进交付门
        ft["生死_verify后"] = [f"{r['who']}(第{r['revive_ch'] + 1}章)" for r in ft_deaths_verified]
        # R11 修为prose闭环: 数值回退候选→POWER_VERIFY(滤隐藏实力/量纲混)→定向修复(advisory不进门)
        pw_cand = [f for f in ft["findings"] if f.get("cat") == "数值" and f.get("conf") == "中"
                   and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(ch_texts)]
        pw_fixed_n = 0
        if pw_cand:
            sys_pv, usr_pv = prompts.POWER_VERIFY
            pchecks = await asyncio.gather(*[
                cli.complete("chunk_extract", sys_pv,
                             usr_pv.format(who=f.get("who", ""), why=f.get("why", ""),
                                           text=ch_texts[f["ch_b"] - 1][:6000]),
                             json_mode=True, max_tokens=300, temperature=0.1) for f in pw_cand])
            pw_real = [f for f, c in zip(pw_cand, pchecks)
                       if (gate._safe_json(c) or {}).get("real") is True]
            if pw_real:
                sys_pr, usr_pr = prompts.POINT_REPAIR
                prew = await asyncio.gather(*[
                    cli.complete("draft", sys_pr,
                                 usr_pr.format(issues=f"修为/数值写岔:{f['why']}——本章对「{f['who']}」的"
                                               f"该数值统一为此前已确立的较高值,禁止回退",
                                               text=ch_texts[f["ch_b"] - 1][:14000]),
                                 max_tokens=8000, temperature=0.3) for f in pw_real])
                for f, t in zip(pw_real, prew):
                    t = _strip_markers((t or "").strip())
                    if t and len(t) >= len(ch_texts[f["ch_b"] - 1]) * 0.7:
                        ch_texts[f["ch_b"] - 1] = t
                        pw_fixed_n += 1
                print(f"修为闭环: {len(pw_cand)}候选→verify真{len(pw_real)}→修复{pw_fixed_n}")
        if os.environ.get("HIKI_SPINE") == "1":       # §3.6 薄网: cross_check真矛盾(对照冻结Spine)进交付门
            if any(f.get("cat") == "身份" for f in ft["findings"]):
                await prose_facts.verify_identity(cli, ft["findings"], ch_texts)   # 真矛盾过滤(①)
            spine_net_num = sum(1 for f in ft["findings"] if f.get("cat") == "数值" and f.get("conf") == "低")
            spine_net_id = sum(1 for f in ft["findings"] if f.get("cat") == "身份" and f.get("real"))
            ft["spine_net"] = {"数值真矛盾": spine_net_num, "身份真矛盾": spine_net_id}
        fact_adv = [f["why"] for f in ft["findings"] if f.get("conf") in ("高", "中")]
        (out_dir / "fact_table.json").write_text(
            json.dumps(ft, ensure_ascii=False, indent=2), encoding="utf-8")
        fact_table_ok = True
    except Exception as e:                            # advisory 绝不为它丢成品
        fact_adv = [f"事实表对账失败:{e}"]
    if fact_adv:
        print(f"事实表对账(advisory): {len(fact_adv)} 条: {'；'.join(fact_adv[:3])}"
              f"{' | 生死verify后:' + str(len(ft_deaths_verified)) + '条进门' if ft_deaths_verified else ''}")
    # 4j) R13 检测换轨: 章 vs 控制面exclusion清单核对(文本对事实清单;两轮实证文本对文本召回不足)
    reenact_hits: list[str] = []
    try:
        sys_pc, usr_pc = prompts.PLANE_CHECK

        async def _pc(ci: int) -> list[str]:
            excl = []
            for j in range(max(0, ci - 3), ci):
                for k in (plan["chapters"][j].get("key_events") or []):
                    if str(k).strip():
                        excl.append(f"第{j + 1}章:{str(k)[:40]}")
            if not excl:
                return []
            raw = await cli.complete("chunk_extract", sys_pc,
                                     usr_pc.format(exclusion="\n".join(excl[-6:]),
                                                   text=ch_texts[ci][:6000]),
                                     json_mode=True, max_tokens=300, temperature=0.1)
            r = gate._safe_json(raw) or {}
            return [f"第{ci + 1}章重演[{str(x)[:40]}]" for x in (r.get("reenacted") or []) if str(x).strip()]
        pc_res = await asyncio.gather(*[_pc(ci) for ci in range(len(ch_texts))])
        reenact_hits = [x for lst in pc_res for x in lst]
        if reenact_hits:
            print(f"控制面核对: {len(reenact_hits)} 处重演: {reenact_hits[:4]}")
    except Exception as e:
        reenact_hits = []
        print(f"控制面核对跳过:{type(e).__name__}")
    final = _assemble(plan, ch_texts)

    # R14 章内自重复检测(确定性,0-LLM): 治整章双版本(ch59飞升写两遍/讨债两版类语义重演)。
    # 12-gram 章内两半重合>8%=同章把同一事件演两遍(读者可见killer);final_consistent兜底不可靠(ch59漏放)。
    def _intra_repeat(t: str, thr: float = 0.08) -> float:
        s = _re.sub(r"\s", "", t or "")
        if len(s) < 800:
            return 0.0
        h = len(s) // 2
        g1 = {s[i:i + 12] for i in range(0, h - 12, 3)}
        g2 = {s[i:i + 12] for i in range(h, len(s) - 12, 3)}
        return (len(g1 & g2) / max(1, min(len(g1), len(g2)))) if g1 and g2 else 0.0
    intra_rep = [(i, r) for i, t in enumerate(ch_texts) if (r := _intra_repeat(t)) > 0.08]
    if intra_rep:
        print(f"章内自重复(整章双版本): {[(f'第{i+1}章', f'{r:.0%}') for i, r in intra_rep]}")

    det = [i for t in ch_texts for i in gate.deterministic_checks(t, bible, 3500)]
    advisory_raw = [o for o in (cont.get("other_issues") or []) if o]
    advisory = await _verify_advisories(cli, advisory_raw, bible)   # R11 灰区判读后才进fc/门
    if len(advisory) < len(advisory_raw):
        print(f"灰区判读: advisory {len(advisory_raw)}→{len(advisory)} (滤掉龙套/延伸/口径差类)")

    # 5) 37维审计（先于交付门：闸门要用硬检结果）
    audit_struct = {k: v for k, v in audit.deterministic_audit(bible, ordered).items() if v}
    audit_fore = audit.foreshadow_advisory(ordered)
    audit_mech = audit.mechanical_audit(final)

    # 5.5) 交付门（人工6本校准:对人工分≤65的三本全拦/≥68的三本全放）。检测早就有效,缺的是这道门——
    #     37分书 final_consistent=false+阵营串线×3 照常交付过。信号选择:阵营串线(canon级硬伤,
    #     烂书有/好书无)+过短≥3章(内容稀薄,与人工分单调)+暗黑饱和;战力崩坏/伏笔序是噪声(75分书18条)不入门。
    #     Tier3 回放扩展(10本回放: ≤65五本全拦/≥68三本零误拦,docs/plans/replay_result.md):
    #     维14死人复活/残缝>8/final_consistent=false 进门——第7跑实证这三类命中的书人工63-65,旧门照常放行。
    too_short = [d for d in det if d.startswith("过短")]
    # 篇幅类(过短/超长)不污染一致性位——过短≥3章由门单独拦(原bug:"长"滤不掉"过短",75分好书也被标false)
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
    # R10b: 生死的权威仪器=prose事实表(detect→verify→repair→复验);plan维14是plan元数据信号,
    # 团宠R10/末世实证: prose全干净时维14仍报(陈旧元数据)→事实表正常跑过则维14只advisory,
    # 失败时才兜底进门(冷战纪老夫人案已被事实表生死通道覆盖,召回测试实证)。
    if audit_struct.get("维14死人复活") and not fact_table_ok:
        ship_issues.append(f"死人复活{len(audit_struct['维14死人复活'])}处(plan维14,事实表未跑兜底)")
    if ft_deaths_verified:                            # 修复后仍残留的才拦
        ship_issues.append(f"事实表死人复活{len(ft_deaths_verified)}处(verify确认,修复未净)")
    if seam_residual > 8:
        ship_issues.append(f"残缝{seam_residual}处(章缝修复采用不足)")
    if not final_consistent:
        ship_issues.append("final_consistent=false(连续性残留)")
    if len(reenact_hits) >= 1:                        # R13: 版本互斥换轨判据(每处=读者可见重演)
        ship_issues.append(f"事件重演{len(reenact_hits)}处(控制面核对)")
    if intra_rep:                                     # R14: 整章双版本(ch59飞升两遍实证,final_consistent漏放)
        ship_issues.append(f"章内双版本{[f'第{i+1}章{r:.0%}' for i, r in intra_rep]}(整章重演)")
    if spine_net_num + spine_net_id >= 2:             # §3.6 Spine薄网: 起草违反冻结事实的残漏(≥2防单条噪声误拦)
        ship_issues.append(f"Spine薄网真矛盾: 数值{spine_net_num}/身份{spine_net_id}条(起草违反冻结事实,详见fact_table.json)")
        # R13c: 阈值2→1——bug版实证1处重演(ch50复刻ch49)漏网误放57.9分书,单处即读者可见硬伤
    deliverable = not ship_issues

    # 成品命名：给复写新书起商业书名+卖点，输出《书名》.md（final.md 保留供下游）
    tmeta = await gen_title(cli, bible, ending=final)
    title, tagline = tmeta.get("title", ""), tmeta.get("tagline", "")
    safe = _safe_filename(title, fallback=_safe_filename(src.stem))
    book = f"# 《{title}》\n\n> {tagline}\n\n---\n\n{final}" if title else final
    (out_dir / "final.md").write_text(final, encoding="utf-8")
    out_name = f"《{safe}》.md" if deliverable else f"《{safe}》.不可交付.md"
    (out_dir / out_name).write_text(book, encoding="utf-8")
    if deliverable:
        print(f"成品命名：《{title}》 —— {tagline}")
    else:
        print(f"⛔ 交付门拦截：{'；'.join(ship_issues)} → {out_name}（重跑或拒收，绝不流向编辑）")
    try:                                          # craft 仅 advisory，绝不为它丢成品/报告
        audit_craft = await audit.craft_audit(cli, final[:9000])
    except Exception as e:
        audit_craft = [f"(craft审计跳过:{type(e).__name__})"]
    report = {
        "title": title, "tagline": tagline, "alt_titles": tmeta.get("alts", []),
        "output_file": out_name,
        "deliverable": deliverable, "交付门": ship_issues or ["通过"],
        "source": src.name, "wan_zi": meta.approx_wan_zi, "out_chapters": len(plan["chapters"]),
        "scenes": n_scenes, "all_scene_count": mined["all_scene_count"], "chunks": mined["chunks"],
        "grade": grade, "central_conflict": macro.get("central_conflict", ""),
        "砍掉支线": dropped or ["无"],
        "final_chars": len(final), "avg_chapter_chars": len(final) // max(1, len(plan["chapters"])),
        "spotlight_variety": _variety(beats),
        "mechanical": det or ["无"], "name_fixes_applied": applied or ["无"],
        "套话门_重写章数": len(decliche_done),
        "plan握手": f"检出{hs_found}/重规划{hs_fixed}",
        "大事件禁演": ev_fixed or ["无"],
        "plan邻章查重": plan_dups or ["无"],
        "波次": str([(a + 1, b) for a, b in waves]),
        "控制面重演核对": reenact_hits or ["无"],
        "邻章版本_检出": adj_found, "邻章版本_修复": adj_fixed or ["无"],
        "事实表对账(advisory)": fact_adv or ["无"],
        "事实表生死_verify后": [f"{r['who']}(第{r['revive_ch'] + 1}章)" for r in ft_deaths_verified] or ["无"],
        "残句(advisory)": audit.broken_prose(ch_texts) or ["无"],
        "时代锚(advisory)": audit.era_anachronism(
            ch_texts, str(bible.get("voice", "")) + str(bible.get("setting", ""))) or ["无"],
        "章缝_检出": seam_found, "章缝_修复": seam_fixed or ["无"],
        "结尾守卫_补收束": ending_fixed or "无需",
        "倒叙哨兵(advisory)": flashbacks or ["无"], "预告跳空": climax_skipped or "无",
        "修为钉回_plan": pw_fixed[:6] or ["无"],
        "prose_异名归一": prose_rep["prose_name_fixes"], "prose_死人复活修复": prose_rep["prose_revivals_fixed"],
        "内容过滤_暗黑净化": dark_rep["dark_fixed"], "暗黑比": dark_rep["dark_ratio"],
        "values_reject(暗黑饱和应拒)": values_reject,
        "audit_承重_确定性硬检": audit_struct or {"全过": "✓"},
        "audit_维7伏笔序(advisory)": audit_fore or ["无"],
        "audit_笔力_机械": audit_mech or {"全过": "✓"},
        "audit_人+故事性_craft(advisory)": audit_craft or ["无"],
        "advisory_issues": advisory or ["无"],
        "final_consistent": final_consistent,
        "calls": cli.calls, "cost_cny": round(cli.cost_cny, 2), "seconds": round(time.time() - t0, 1),
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _variety(beats: list[dict]) -> str:
    """爽点类型跨章变化度（治通胀的指标）：相邻重复率越低越好。"""
    types = [b.get("pt") or b.get("spotlight_payoff_type") for b in beats
             if b.get("pt") or b.get("spotlight_payoff_type")]
    if len(types) < 2:
        return "n/a"
    repeats = sum(1 for a, b in zip(types, types[1:]) if a == b)
    return f"相邻重复{repeats}/{len(types)-1} | 种类{len(set(types))}"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--chapters", type=int, default=60)
    ap.add_argument("--chunks", type=int, default=12)
    ap.add_argument("-n", "--candidates", type=int, default=3)
    ap.add_argument("--refine-rounds", type=int, default=5)
    ap.add_argument("--min-grade", default=None, choices=["S", "A", "B", "C", "D"],
                    help="源分级门槛:低于此档拒收(如 A=只产S/A好源)")
    a = ap.parse_args()
    rep = asyncio.run(run(Path(a.src), a.chapters, a.chunks, a.candidates, a.refine_rounds,
                          min_grade=a.min_grade))
    print("\n=== 全书报告 ===")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"\n成品 → output/{Path(a.src).stem}_full/final.md（请人工评判）")


if __name__ == "__main__":
    main()
