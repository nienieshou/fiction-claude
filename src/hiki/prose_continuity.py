"""Tier1.5b PROSE 层连续性审计（作用在生成的正文，不是 plan 元数据）。

教训：确定性 plan 审计能保证规划干净，但起草的 LLM 在正文里仍会漂（疯骡子复活、
高志强/高志坚同人异名）——这些 plan 审计是瞎的。本模块像编辑读稿：从正文抽实际
人物/死亡 → 全局聚类同人异名(语义,非编辑距离,避开中文误报灾难) → 确定性归一 +
死人复活检测 → 定向重写复活章。
"""
from __future__ import annotations
import asyncio
import re
from . import prompts
from .gate import _safe_json
from .client import Client

_CH = re.compile(r"^# 第", re.M)


async def _roster_window(cli: Client, text: str) -> dict:
    sys_p, usr_t = prompts.PROSE_ROSTER
    for t in range(3):                           # retry-on-empty: 空窗=该窗人物/死亡全静默丢失
        raw = await cli.complete("chunk_extract", sys_p, usr_t.format(text=text[:40000]),
                                 json_mode=True, max_tokens=4000, temperature=0.2 + 0.1 * t)
        r = _safe_json(raw) or {}
        if "persons" in r:                       # (白清霜漏网实证根因①: 单次空响应整窗丢)
            return r
    return {}


async def extract_roster(cli: Client, ch_texts: list[str], win: int = 8) -> dict:
    """分窗并发抽 正文里的 人物名 + 明确死亡(精确到章)。返回 {persons:set, deaths:[{who,clue,ch,win}]}。
    注: 给每章打 # 第i章 标记,死亡定位到章号→find_revivals按章比较(治同窗死而复生漏检,纪老夫人类)。"""
    labeled = [f"# 第{i + 1}章\n{t}" for i, t in enumerate(ch_texts)]
    windows = [labeled[i:i + win] for i in range(0, len(labeled), win)]
    results = await asyncio.gather(*[_roster_window(cli, "\n\n".join(w)) for w in windows])
    persons: set[str] = set()
    deaths: list[dict] = []
    for wi, r in enumerate(results):
        for nm in r.get("persons", []) or []:
            if isinstance(nm, str) and 2 <= len(nm.strip()) <= 5:
                persons.add(nm.strip())
        for d in r.get("deaths", []) or []:
            if isinstance(d, str):               # LLM 偶吐 deaths:["名字"] 扁平形 → 容忍(第12个健壮类)
                d = {"who": d}
            if not isinstance(d, dict):
                continue
            who = (d.get("who") or "").strip()
            if who:
                try:
                    ch = int(d.get("ch"))
                    ch = ch if 1 <= ch <= len(ch_texts) else None
                except (ValueError, TypeError):
                    ch = None
                deaths.append({"who": who, "clue": (d.get("clue") or "").strip(),
                               "ch": ch, "win": wi})
    return {"persons": persons, "deaths": deaths, "win": win, "n_win": len(windows)}


_SENT = re.compile(r"[^。！？\n]*[。！？]")


def _examples(name: str, full: str, k: int = 3) -> str:
    got = [s.strip()[:60] for s in _SENT.findall(full) if name in s][:k]
    return " / ".join(got) or name


def _dist_evidence(a: str, b: str, ch_texts: list[str]) -> str:
    """确定性分布证据(白清霜/白清梅实证): 判别器必须下沉到**句级**——真兄弟/亲属会同句互动
    ('高志坚的弟弟高志强'),写岔的名字不同句(章内中途写岔会造成同章共现,章级证据会误判)。"""
    full = "\n".join(ch_texts)
    ca = [i + 1 for i, t in enumerate(ch_texts) if a in t]
    cb = [i + 1 for i, t in enumerate(ch_texts) if b in t]
    co_sent = sum(1 for s in _SENT.findall(full) if a in s and b in s)
    fa = f"第{ca[0]}-{ca[-1]}章({len(ca)}章)" if ca else "无"
    fb = f"第{cb[0]}-{cb[-1]}章({len(cb)}章)" if cb else "无"
    return f"「{a}」出现于{fa}；「{b}」出现于{fb}；**同句共现{co_sent}次**"


async def _verify_pair(cli: Client, a: str, b: str, full: str,
                       ch_texts: list[str] | None = None) -> bool:
    """LLM 带例句+章分布证据核查 a/b 是否同一人写岔(排除兄弟/称号/昵称/粘连碎片)。"""
    sys_p, usr_t = prompts.PROSE_NAME_VERIFY
    dist = _dist_evidence(a, b, ch_texts) if ch_texts else "（无分布数据）"
    raw = await cli.complete("chunk_extract", sys_p,
                             usr_t.format(a=a, b=b, sa=_examples(a, full), sb=_examples(b, full),
                                          dist=dist),
                             json_mode=True, max_tokens=400, temperature=0.1)
    return (_safe_json(raw) or {}).get("same") is True


# 功能字停用表(第1轮实战教训): 变体差异字若是介词/动词/助词等,该"变体"几乎必是
# 粘连误切('看到苒苒'切出'到苒'/'和晏礼'/'家父'/'协会长'),replace会污染正文 → 确定性排除。
_FUNC_CHARS = set("的了在和与对到把被给让向从看说想见听着去来过就也都还又再才"
                  "是有等而或及其这那个家本您见请别只众位之者所如同跟连帮"
                  "我你他她它咱谁此每某双两几")


# 称谓后缀(第5跑实战教训): '姓+称谓'(马长老/刘总/纪少/好姐/冯哥)是合法称呼,不同姓的同称谓
# 是**不同的人**(马长老≠刘长老)——但它们从不同句共现,verify会被分布证据带偏误并 → 确定性排除。
_TITLE_SUFFIX = ("长老", "小姐", "少爷", "老师", "导师", "将军", "护法", "师兄", "师姐", "师妹",
                 "师弟", "掌门", "宗主", "城主", "公子", "大人", "先生", "夫人", "老祖", "前辈",
                 "姑娘", "殿下", "陛下", "会长", "队长", "老板",
                 "总", "少", "姐", "哥", "爷", "叔", "婶", "嫂", "兄", "妹", "师", "帝", "皇",
                 "王", "妃", "后", "神", "老")


def _is_appellation(name: str) -> bool:
    """是否'1-2字前缀+称谓后缀'形态(纪少/马长老/洪导师)——合法称呼,绝不参与归一替换。"""
    for suf in _TITLE_SUFFIX:
        if name.endswith(suf) and 1 <= len(name) - len(suf) <= 2:
            return True
    return False


def _variant_scan(counts: dict, full: str, floor: int = 10, cap_per: int = 6) -> set:
    """非对称变体扫描(治'嬴墨733次 vs 赢墨1次'漏网——roster/edit-1 只看次数≥3的名,罕见笔误漏掉)：
    对每个高频名,逐位单字通配在正文里找罕见近似串。只产候选,真假交 verify 把关;
    已知高频人物名(本就是别人)与功能字粘连碎片(确定性停用表)直接跳过。"""
    pairs = set()
    for c, cc in counts.items():
        if cc < floor or not (2 <= len(c) <= 4):
            continue
        cands: dict[str, int] = {}
        for pos in range(len(c)):
            pat = re.escape(c[:pos]) + "[一-龥]" + re.escape(c[pos + 1:])
            for m in re.findall(pat, full):
                if m != c:
                    diff = next(x for x, y in zip(m, c) if x != y)
                    if diff in _FUNC_CHARS:          # 功能字粘连 → 不是名字写岔
                        continue
                    cands[m] = cands.get(m, 0) + 1
        for m, mc in sorted(cands.items(), key=lambda kv: kv[1])[:cap_per]:   # 越罕见越像笔误
            if 0 < mc <= cc / 3 and counts.get(m, 0) < floor:   # 高频名是真人物,不当变体
                pairs.add((m, c))
    return pairs


async def cluster_names(cli: Client, persons: set[str], full: str, ch_texts: list[str],
                        extra_canon: set | None = None, source_text: str = "") -> dict:
    """同人异名归一(detect→verify→merge)：edit-1候选 ∪ LLM聚类候选 ∪ canon变体扫描
    → 源在场守卫 → 逐对LLM带例句核查 → 少数归多数。
    源在场守卫(团宠'灵器→成器'实战教训): 变体若在**源书原文**出现过=正常词汇/真实他人
    (灵器/雾海/青年/家父都来自源),不是生成漂移 → 确定性跳过;真漂移(白清梅/赢墨)源里没有。"""
    counts = {nm: full.count(nm) for nm in persons | set(extra_canon or ())}
    pairs: set = set()
    ps = [p for p in counts if counts.get(p, 0) >= 3 and 2 <= len(p) <= 5]
    for i in range(len(ps)):                                   # 确定性 edit-1 候选
        for j in range(i + 1, len(ps)):
            a, b = ps[i], ps[j]
            if len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1:
                pairs.add((a, b))
    for m, c in _variant_scan(counts, full):                   # 罕见笔误候选(verify把关)
        counts.setdefault(m, full.count(m))
        pairs.add((m, c))
    listed = "、".join(f"{nm}:{counts[nm]}" for nm in sorted(persons, key=lambda x: -counts[x]) if counts[nm] > 0)
    if listed:                                                # LLM 聚类候选(治2字漂移)
        sys_p, usr_t = prompts.PROSE_CLUSTER
        raw = await cli.complete("reduce", sys_p, usr_t.format(names=listed[:6000]),
                                 json_mode=True, max_tokens=3000, temperature=0.2)
        for cl in (_safe_json(raw) or {}).get("clusters", []) or []:
            if not isinstance(cl, dict):         # LLM 偶吐 clusters:["名"] 扁平形 → 跳过
                continue
            canon = (cl.get("canonical") or "").strip()
            for v in cl.get("variants", []) or []:
                v = (v or "").strip()
                if v and canon and v != canon and counts.get(v, 0) > 0 and counts.get(canon, 0) > 0:
                    pairs.add((v, canon))
    pairs = [(a, b) for a, b in pairs if a not in b and b not in a]              # 排互为子串
    pairs = [(a, b) for a, b in pairs if not (_is_appellation(a) or _is_appellation(b))]
    if source_text:                              # 源在场守卫: 罕见侧在源书原文里出现过→非漂移,跳过
        pairs = [(a, b) for a, b in pairs
                 if (a if counts.get(a, 0) <= counts.get(b, 0) else b) not in source_text]
    pairs = sorted(pairs, key=lambda ab: (-(counts.get(ab[0], 0) + counts.get(ab[1], 0)), ab))[:80]
    if not pairs:                                  # 按重要度(合计频次)排序封顶,要名先验,不再字典序误删
        return {}
    oks = await asyncio.gather(*[_verify_pair(cli, a, b, full, ch_texts=ch_texts) for a, b in pairs])
    fix_map = {}
    for (a, b), ok in zip(pairs, oks):
        if ok:
            lo, hi = (a, b) if counts[a] <= counts[b] else (b, a)
            if lo not in fix_map:
                fix_map[lo] = hi
    return fix_map


def find_revivals(roster: dict, ch_texts: list[str]) -> list[dict]:
    """确定性：某人死亡后，在更后的章节里实质再出场(count≥2) → 死人复活。
    死亡有章号→从死亡章的下一章查起(治同窗复活漏检: ch28死/ch32活同在一个8章窗,旧版窗后起查必漏);
    无章号→退回窗口粒度。"""
    win = roster["win"]
    out = []
    seen = set()
    for d in roster["deaths"]:
        who = d["who"]
        if who in seen:
            continue
        after = d["ch"] if d.get("ch") else (d["win"] + 1) * win   # ch是1-based→0-based下一章恰为ch
        for j in range(after, len(ch_texts)):
            if ch_texts[j].count(who) >= 2:
                out.append({"who": who, "clue": d["clue"], "death_win": d["win"], "revive_ch": j})
                seen.add(who)
                break
    return out


async def verify_revivals(cli: Client, ch_texts: list[str], revivals: list[dict]) -> list[dict]:
    """detect→verify→repair：逐个核查疑似复活是否为真(确定死亡+本章在场活人),滤掉假阳性(如未真死的角色)。"""
    sys_p, usr_t = prompts.PROSE_REVIVAL_VERIFY
    checks = await asyncio.gather(*[
        cli.complete("chunk_extract", sys_p,
                     usr_t.format(who=r["who"], clue=r["clue"] or "已死亡",
                                  text=ch_texts[r["revive_ch"]][:9000]),
                     json_mode=True, max_tokens=500, temperature=0.1) for r in revivals])
    out = []
    for r, c in zip(revivals, checks):
        v = _safe_json(c) or {}
        if v.get("is_revival") is True:
            out.append(r)
    return out


async def repair_revivals(cli: Client, ch_texts: list[str], revivals: list[dict], cap: int = 6) -> list[str]:
    """定向重写复活章(只改死人出场处,其余不动)。按章分组(同章多死人一次改),限 cap。"""
    sys_p, usr_t = prompts.PROSE_REVIVAL_FIX
    by_ch: dict[int, list[dict]] = {}
    for r in revivals[:cap]:
        by_ch.setdefault(r["revive_ch"], []).append(r)
    items = list(by_ch.items())
    fixed = await asyncio.gather(*[
        cli.complete("draft", sys_p, usr_t.format(
            who="、".join(r["who"] for r in rs),
            clue="；".join(r["clue"] or "已死亡" for r in rs),
            text=ch_texts[ci][:12000]), max_tokens=8000, temperature=0.3)
        for ci, rs in items])
    for (ci, rs), t in zip(items, fixed):
        t = (t or "").strip()
        orig = sum(ch_texts[ci].count(r["who"]) for r in rs)
        new = sum(t.count(r["who"]) for r in rs)
        if t and len(t) > len(ch_texts[ci]) * 0.5 and new < orig:   # 死人提及减少才算修成功
            ch_texts[ci] = t
    return ch_texts


_CHNUM = re.compile(r"#\s*第\s*([0-9]+)\s*章")


_DARK_KW = re.compile(r"羞辱|惨叫|品味|欣赏着|扒光|脱光|轮[奸流]|喂猪|当众.*脱|玩弄|凌辱|"
                      r"舔了舔嘴|咧嘴一笑.*惨|看.*好戏|当.*乐子|蛆|爽|快感|得意")


async def _scan_dark_window(cli: Client, text: str) -> list[dict]:
    """扫一窗暗黑。重试防 flaky 空返回——含暗黑关键词却扫到空 → 大概率是漏扫,重试。"""
    sys_p, usr_t = prompts.PROSE_DARK_SCAN
    has_kw = bool(_DARK_KW.search(text))
    for t in range(3):
        raw = await cli.complete("chunk_extract", sys_p, usr_t.format(text=text[:40000]),
                                 json_mode=True, max_tokens=4000, temperature=0.2 + 0.1 * t)
        flags = (_safe_json(raw) or {}).get("flags", []) or []
        if flags or not has_kw:        # 有结果 / 本窗无暗黑关键词(真干净) → 收
            return flags
    return []                          # 含关键词但3次都空 → 认其干净(避免空转)


async def content_filter(cli: Client, ch_texts: list[str], win: int = 8, cap: int = 16) -> tuple[list[str], dict]:
    """Tier2b PROSE内容过滤:分窗扫暗黑厌女当爽点的章 → 定向净化重写(保情节去爽点化暴力/厌女)。
    返回 (净化后章文, {fixed, dark_ratio})。dark_ratio 高 → 调用方可判该源应拒。
    注:此处 ch_texts 是无标题正文(step4d),故给每章打 # 第i章 标记供扫描按章号定位。"""
    labeled = [f"# 第{i + 1}章\n{t}" for i, t in enumerate(ch_texts)]   # 注入章号标记
    num2idx = {i + 1: i for i in range(len(ch_texts))}
    windows = [labeled[wi * win:(wi + 1) * win] for wi in range((len(ch_texts) + win - 1) // win)]
    flag_lists = await asyncio.gather(*[_scan_dark_window(cli, "\n\n".join(w)) for w in windows])
    flagged = {}
    for flags in flag_lists:
        for f in flags:
            if not isinstance(f, dict):          # LLM 偶吐扁平形 → 跳过
                continue
            try:
                idx = num2idx.get(int(f.get("ch")))
            except (ValueError, TypeError):
                idx = None
            if idx is not None and idx not in flagged:
                flagged[idx] = (f.get("issue") or "").strip()
    if not flagged:
        return ch_texts, {"dark_fixed": ["无"], "dark_ratio": 0.0}
    items = list(flagged.items())[:cap]
    sys_p, usr_t = prompts.PROSE_DARK_FIX
    res = await asyncio.gather(*[
        cli.complete("draft", sys_p, usr_t.format(issue=iss or "暴力/羞辱当爽点", text=ch_texts[idx][:12000]),
                     max_tokens=8000, temperature=0.4) for idx, iss in items])
    fixed = []
    for (idx, iss), t in zip(items, res):
        t = (t or "").strip()
        if t and len(t) > len(ch_texts[idx]) * 0.6:
            ch_texts[idx] = t
            fixed.append(f"第{idx + 1}章:{iss[:15]}")
    return ch_texts, {"dark_fixed": fixed or ["无"], "dark_ratio": round(len(flagged) / max(1, len(ch_texts)), 2)}


async def audit_and_repair(cli: Client, ch_texts: list[str],
                           canon_names: set | None = None,
                           source_text: str = "") -> tuple[list[str], dict]:
    """一条龙：抽roster → 同人异名归一(含canon变体扫描+源在场守卫) → 死人复活检测+定向修。"""
    full = "\n".join(ch_texts)
    roster = await extract_roster(cli, ch_texts)
    fix_map = await cluster_names(cli, roster["persons"], full, ch_texts,
                                  extra_canon=canon_names, source_text=source_text)
    name_fixes = []
    if fix_map:
        ch_texts = [t for t in ch_texts]
        for i in range(len(ch_texts)):
            for v, c in fix_map.items():
                if v in ch_texts[i]:
                    ch_texts[i] = ch_texts[i].replace(v, c)
        name_fixes = [f"{v}→{c}" for v, c in fix_map.items()]
    suspects = find_revivals(roster, ch_texts)
    revived = []
    if suspects:
        revivals = await verify_revivals(cli, ch_texts, suspects)   # detect→verify→repair,滤假阳性
        if revivals:
            ch_texts = await repair_revivals(cli, ch_texts, revivals)
            revived = [f"{r['who']}(第{r['revive_ch']+1}章)" for r in revivals]
    return ch_texts, {"prose_name_fixes": name_fixes or ["无"],
                      "prose_revivals_fixed": revived or ["无"],
                      "persons_found": len(roster["persons"]), "deaths_found": len(roster["deaths"])}


async def repair_revivals_smart(cli: Client, ch_texts: list[str], revivals: list[dict]) -> list[str]:
    """R10 修复位点选择: 死后≥3章仍在场→死亡描写多半是误笔,改写**死亡处**为重伤/未遂
    (骥川/傅礼/KEVIN实证: 逐章删人修不净且会毁书);孤立复现→照旧修复现处。
    revivals 项须带 death_ch(0-based,可缺省=退回旧路径)。"""
    site_death: dict[int, dict] = {}
    site_revive: list[dict] = []
    for r in revivals:
        dch = r.get("death_ch")
        who = r["who"]
        start = (dch + 1) if isinstance(dch, int) else r["revive_ch"]
        later = sum(1 for j in range(start, len(ch_texts)) if who in ch_texts[j])
        if later >= 3 and isinstance(dch, int) and 0 <= dch < len(ch_texts):
            site_death.setdefault(dch, r)
        else:
            site_revive.append(r)
    if site_revive:
        ch_texts = await repair_revivals(cli, ch_texts, site_revive, cap=10)
    if site_death:
        sys_p, usr_t = prompts.POINT_REPAIR

        async def _fix(dch: int, r: dict):
            issue = (f"本章把「{r['who']}」写死了({r.get('clue', '') or '死亡'}),但后文多章他仍正常在场——"
                     f"把死亡改为重伤垂死/被救走/未遂,保持本章冲突结果与其余情节一字不动,使其与后文在世一致")
            raw = await cli.complete("draft", sys_p,
                                     usr_t.format(issues=issue, text=ch_texts[dch][:14000]),
                                     max_tokens=8000, temperature=0.3)
            return dch, (raw or "").strip()
        res = await asyncio.gather(*[_fix(d, r) for d, r in site_death.items()])
        for c, t in res:
            if t and len(t) >= len(ch_texts[c]) * 0.7:
                ch_texts[c] = t
    return ch_texts
