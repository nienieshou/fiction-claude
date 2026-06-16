"""37 维审计套件（inkos 37 维适配到"压缩单源→60章"）。

按 rubric 四轴(承重/笔力/人/故事性)归类；每维标检测类型:
  det  = 确定性结构检（LLM 裁判的盲区，最高价值，可信）
  mech = 机械正则检（可信，不可刷分）
  llm  = LLM 判断（craft 维度，人工校准证明不可靠→只 advisory，低权）
状态: ✓已实现 / ~部分 / advisory(仅标记) / metric(走结构指标)
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from . import ledger, prompts


@dataclass
class Dim:
    id: int
    name: str
    axis: str          # 承重/笔力/人/故事性
    kind: str          # det/mech/llm
    status: str


DIMENSIONS: list[Dim] = [
    # —— 承重轴（结构连续/世界观）：确定性为主，LLM 盲区，最高价值 ——
    Dim(1, "人名/别名一致", "承重", "det", "✓"),
    Dim(2, "阵营归属/随从匹配", "承重", "det", "✓"),      # ← 张岩/格森门
    Dim(3, "时间线顺序", "承重", "det", "✓"),
    Dim(4, "场景/事件唯一(无重复)", "承重", "det", "✓"),   # ← 许安两次初遇
    Dim(5, "战力/修为单调(战力崩坏)", "承重", "det", "✓"),
    Dim(6, "数值/资源账一致", "承重", "det", "~"),
    Dim(7, "伏笔plant→payoff序+回收", "承重", "det", "✓"),
    Dim(8, "支线立场无无过渡翻转", "承重", "det", "✓"),    # ← 天机阁
    Dim(9, "支线停滞检测", "承重", "det", "~"),
    Dim(10, "位置一致(不同时两地)", "承重", "det", "~"),
    Dim(11, "信息边界/越界(知识)", "承重", "llm", "advisory"),
    Dim(12, "称谓/身份一致", "承重", "det", "✓"),          # ← 圣子/圣帝
    Dim(13, "世界规则遵守/设定冲突", "承重", "llm", "advisory"),
    Dim(14, "生死/伤势状态", "承重", "det", "~"),
    Dim(15, "记忆点/差异化", "承重", "llm", "advisory"),
    # —— 笔力轴（语言/对话/画面）：机械为主 ——
    Dim(16, "去AI腔/套话密度", "笔力", "mech", "✓"),
    Dim(17, "词汇疲劳(高频词)", "笔力", "mech", "✓"),
    Dim(18, "段落等长", "笔力", "mech", "✓"),
    Dim(19, "整齐排比/列表式结构", "笔力", "mech", "✓"),
    Dim(20, "比喻/感官套话密度", "笔力", "mech", "✓"),
    Dim(21, "对话蹦字/机枪句", "笔力", "mech", "~"),
    Dim(22, "英文泄漏/乱码", "笔力", "mech", "✓"),
    Dim(23, "公式化转折", "笔力", "llm", "advisory"),
    Dim(24, "流水账/梗概感", "笔力", "llm", "advisory"),
    Dim(25, "台词失真", "笔力", "llm", "advisory"),
    Dim(26, "视角(POV)一致", "笔力", "llm", "advisory"),
    # —— 人轴（魅力/代入/主动性/成长）：LLM 判断（rubric 最大洼地）——
    Dim(27, "角色还原度/OOC", "人", "llm", "advisory"),
    Dim(28, "配角降智", "人", "llm", "advisory"),
    Dim(29, "配角工具人化", "人", "llm", "advisory"),
    Dim(30, "主角主动性(防被动洼地)", "人", "llm", "advisory"),
    Dim(31, "成长弧/弧线平坦", "人", "llm", "advisory"),
    Dim(32, "关系动态", "人", "llm", "advisory"),
    Dim(33, "代入/魅力", "人", "llm", "advisory"),
    # —— 故事性轴（钩子/爽点/节奏）：结构指标 + LLM ——
    Dim(34, "爽点密度/最大憋屈跨度", "故事性", "metric", "✓"),
    Dim(35, "钩子密度", "故事性", "metric", "✓"),
    Dim(36, "节奏单调/爽点间隔", "故事性", "metric", "✓"),
    Dim(37, "读者期待管理", "故事性", "llm", "advisory"),
]


# ============ 承重轴·确定性结构检（核心，LLM 盲区）============

def _alias_map(bible: dict) -> dict:
    """别名→本名（全角色，治 张将军↔张岩）。"""
    m = {}
    for ch in [bible.get("protagonist", {})] + bible.get("characters", []):
        canon = (ch.get("name") or "").strip()
        if not canon:
            continue
        for a in ch.get("aliases") or []:
            if a.strip() and a.strip() != canon:
                m[a.strip()] = canon
    return m


def _faction_of(bible: dict) -> dict:
    """本名→阵营。"""
    f = {}
    for ch in [bible.get("protagonist", {})] + bible.get("characters", []):
        nm = (ch.get("name") or "").strip()
        if nm:
            f[nm] = (ch.get("faction") or "").strip()
    return f


def _str_pair(pair):
    """安全取 [str,str]；LLM 偶吐嵌套/非串/非2元 → 返回 None 跳过，绝不崩确定性审计。"""
    if isinstance(pair, (list, tuple)) and len(pair) == 2 \
            and isinstance(pair[0], str) and isinstance(pair[1], str):
        return pair[0].strip(), pair[1].strip()
    return None


def _known_factions(bible: dict) -> set:
    """全书已登记的 canon 阵营名集合（防 entourage 自由文本'队友/己方'被误判串线）。"""
    s = set()
    for f in bible.get("factions") or []:
        nm = (f.get("name") or "").strip() if isinstance(f, dict) else ""
        if nm:
            s.add(nm)
    for ch in [bible.get("protagonist", {})] + bible.get("characters", []):
        fc = (ch.get("faction") or "").strip()
        if fc and fc != "无":
            s.add(fc)
    return s


def fix_entourage(bible: dict, scenes: list[dict]) -> int:
    """维2 shift-left 确定性修复：随从阵营钉回主子的 canon 阵营，起草前执行。
    第1轮迭代实证：串线是 plan 的 run 间随机噪声（同源 round6=0条/round7=3条），好源也会中——
    可确定性修就不该拿去交付门拦书。修后 check_factions 残留=真正的未知主子类。"""
    fac = _faction_of(bible)
    alias = _alias_map(bible)
    fixed = 0
    for sc in scenes:
        new = []
        for pair in sc.get("entourage") or []:
            sp = _str_pair(pair)
            if sp:
                master, ent_fac = sp
                mf = fac.get(alias.get(master, master), "")
                if mf and mf != "无" and ent_fac != mf:
                    new.append([master, mf]); fixed += 1
                    continue
            new.append(pair)
        sc["entourage"] = new
    return fixed


def check_factions(bible: dict, scenes: list[dict]) -> list[str]:
    """维2：随从阵营须与主子阵营一致（治 张岩/格森门串线）。
    只在随从阵营是**已登记 canon 阵营**且与主子不符时才判串线；自由文本(队友/己方/手下)跳过，防误报。"""
    fac = _faction_of(bible)
    alias = _alias_map(bible)
    known = _known_factions(bible)
    issues = []
    for i, sc in enumerate(scenes):
        for pair in sc.get("entourage") or []:
            sp = _str_pair(pair)
            if not sp:
                continue
            master, ent_fac = sp
            mf = fac.get(alias.get(master, master), "")
            # 仅 canon 阵营冲突才算硬伤；主子阵营='无'时没有冲突依据(第5跑实证:温灵属'无'被误拦)
            if mf and mf != "无" and ent_fac in known and mf != ent_fac:
                issues.append(f"场景{i}: 「{master}」属{mf}，随从却写成{ent_fac}阵营(串线)")
    return issues


_POWER_ORDER = ["凡人", "炼气", "筑基", "结丹", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫"]


def _power_rank(p: str, order: list[str] | None = None) -> int:
    """R13c修(锚-5.9主因,52处钉反实锤): 旧版按梯子序找子串,'练气大圆满（渡劫中）'被括号状语
    命中'渡劫'判rank=10(最高),后续筑基/金丹全被当'回退'钉回低值。改:
    ①取**字符串中最早出现**的境界词(主境界在串首,状语注释在后); ②炼/练归一('练气'旧版rank=-1)。"""
    s = (p or "").replace("炼气", "练气")
    best, pos = -1, 1 << 30
    for j, k in enumerate(order or _POWER_ORDER):
        i = s.find(k.replace("炼气", "练气"))
        if 0 <= i < pos:
            best, pos = j, i
    return best


def power_order_from_bible(bible: dict) -> list[str] | None:
    """从 bible.escalation_ladder 解析本书境界梯('练气→筑基→金丹…，赌注从…'→取→链头段)。
    解析不出≥3级返回 None(调用方退默认梯);宁缺勿错。"""
    raw = str((bible or {}).get("escalation_ladder") or "")
    head = re.split(r"[，。,;；\s]", raw)[0]
    stages = [t.strip() for t in re.split(r"[→>＞]+", head) if 1 < len(t.strip()) <= 6]
    return stages if len(stages) >= 3 else None


def fix_power_monotonic(bible: dict, scenes: list[dict]) -> list[str]:
    """维5 shift-left：plan 里回退的 power_after 钉回当前最高境界，起草前执行。
    Fable三本实证翻案: 维5标记不是噪声——plan层修为回退会被起草忠实写进正文
    (化神→金丹→筑基三连倒退,正文跟着乱),人类编辑只读开头看不见,全读就是killer。
    '隐藏实力/虚弱'是prose层的演法,canon真实境界只升不降。
    R13c: 优先用 bible 专属梯子;rank判不出(任一侧-1)绝不钉——宁漏勿错钉(钉反=主动造伤)。"""
    order = power_order_from_bible(bible)
    alias = _alias_map(bible)
    cur: dict[str, tuple[int, str]] = {}
    fixed = []
    for i, sc in enumerate(scenes):
        new = []
        for pair in sc.get("power_after") or []:
            sp = _str_pair(pair)
            if sp:
                who, p = alias.get(sp[0], sp[0]), sp[1]
                r = _power_rank(p, order)
                if r >= 0:
                    cr, cs = cur.get(who, (-1, ""))
                    if r < cr:                       # 回退 → 钉回当前最高
                        new.append([sp[0], cs])
                        fixed.append(f"场景{i}:{who} {p}→{cs}")
                        continue
                    cur[who] = (r, p)
            new.append(pair)
        sc["power_after"] = new
    return fixed


def check_power_monotonic(bible: dict, scenes: list[dict]) -> list[str]:
    """维5：修为不可回退(战力崩坏)。用境界序粗判(R13c: 同步bible专属梯)。"""
    order = power_order_from_bible(bible)
    alias = _alias_map(bible)
    cur: dict[str, int] = {}
    issues = []
    for i, sc in enumerate(scenes):
        for pair in sc.get("power_after") or []:
            sp = _str_pair(pair)
            if not sp:
                continue
            who, pw = alias.get(sp[0], sp[0]), sp[1]
            r = _power_rank(pw, order)
            if r < 0:
                continue
            if who in cur and r < cur[who]:
                issues.append(f"场景{i}: 「{who}」修为回退到{pw}(战力崩坏)")
            cur[who] = max(cur.get(who, -1), r)
    return issues


def _polarity(s: str) -> str:
    """立场极性：友好/敌对/中性。只有友↔敌的反转才算硬伤(自然加深不算)。"""
    s = s or ""
    if any(k in s for k in ("敌对", "威胁", "觊觎", "提防", "警惕", "图谋", "暗算", "夺", "搬走")):
        return "敌"
    if any(k in s for k in ("合作", "敬畏", "忠诚", "归顺", "供奉", "示好", "结盟", "巴结")):
        return "友"
    return "中"


def check_thread_stance(bible: dict, scenes: list[dict]) -> list[str]:
    """维8：势力立场"友↔敌"反转须有过渡(治天机阁 合作→威胁 无过渡)；放过同极性加深。"""
    last: dict[str, tuple[int, str]] = {}
    issues = []
    for i, sc in enumerate(scenes):
        for pair in sc.get("faction_stance") or []:
            sp = _str_pair(pair)
            if not sp:
                continue
            fac, st = sp
            if fac in last:
                pi, ps = last[fac]
                if {_polarity(ps), _polarity(st)} == {"友", "敌"} and i - pi <= 1:
                    issues.append(f"场景{i}: 「{fac}」立场{ps}→{st}(友↔敌)无过渡场景")
            last[fac] = (i, st)
    return issues


def check_revival(scenes: list[dict]) -> list[str]:
    """维14：死人复活（治 疯骡子 ch30死 ch31活）。某场景死亡/退场的人物，此后不得再出场。"""
    dead: dict[str, int] = {}
    issues = []
    for i, sc in enumerate(scenes):
        present = set()
        for c in sc.get("first_appearances") or []:
            if isinstance(c, str):
                present.add(c.strip())
        for pair in (sc.get("power_after") or []) + (sc.get("entourage") or []):
            sp = _str_pair(pair)
            if sp:
                present.add(sp[0])
        for a, b in ledger._rel_pairs(sc.get("relationships_formed")):
            present.add(a); present.add(b)
        for who in present:
            if who in dead:
                issues.append(f"场景{i}: 「{who}」已在场景{dead[who]}死亡/退场，却再次出场(死人复活)")
        for c in (sc.get("deaths") or []):
            if isinstance(c, str) and c.strip():
                dead[c.strip()] = i
    return issues


def deterministic_audit(bible: dict, scenes: list[dict]) -> dict:
    """承重轴确定性套件（只放高可信、低误报项；伏笔序见 foreshadow_advisory 不混入）。"""
    return {k: v for k, v in {
        "维4事件/初遇唯一(硬)": ledger.validate_timeline(scenes),
        "维2阵营串线": check_factions(bible, scenes),
        "维5战力崩坏": check_power_monotonic(bible, scenes),
        "维8立场翻转(友↔敌)": check_thread_stance(bible, scenes),
        "维14死人复活": check_revival(scenes),
    }.items() if v}


def foreshadow_advisory(scenes: list[dict]) -> list[str]:
    """维7 伏笔序：模糊 advisory，不触发 re-plan、不计入硬一致性。"""
    return ledger.check_foreshadow(scenes)


# ============ 笔力轴·机械正则检 ============

_CLICHE = re.compile(r"(不由得|不由自主|嘴角(微微)?(勾起|上扬)|眼中闪过一丝|心中一[紧凛]|"
                     r"仿佛|宛如|犹如|好像|like a|之色|不禁|莫名地)")

# Tier2 套话门：全书反复复读的模板句/小动作(编辑实测点名 + 高频网文套话)。按"类别"计数:
# 同义变体(嘴角勾起/上扬/弧度)归一类,才反映读者的累积疲劳。
_TICS = [("全场死寂", r"全场死寂|死一般的?[寂静沉默]|鸦雀无声"), ("瞳孔骤缩", r"瞳孔[一骤微]?缩"),
         ("脸色铁青", r"脸色(铁青|煞白|惨白|阴沉)"), ("倒吸凉气", r"倒吸(一|了)?.{0,2}口凉气"),
         ("嘴角勾起/弧度", r"嘴角.{0,5}(勾|上扬|弧度|抽搐)"), ("眼中闪过", r"眼(中|里|底)(闪过|划过|掠过)"),
         ("心中一紧", r"心(中|里|头)一[紧凛沉]"), ("冷哼一声", r"冷哼(一声|一下)?"),
         ("眼神一凛", r"(眼神|目光)一(凛|冷)"), ("后背发凉", r"后背(发凉|一凉|發涼)"),
         ("鸡皮疙瘩", r"鸡皮疙瘩"), ("如遭雷击", r"如遭雷击|如坠冰窟"), ("深吸一口气", r"深吸(一|了)?.{0,2}口气")]


def cliche_hits(text: str) -> dict:
    """按类别统计套话命中(同义变体归一类)。用于 Tier2 去套话门。"""
    return {label: len(re.findall(pat, text)) for label, pat in _TICS if re.search(pat, text)}
_PARALLEL = re.compile(r"[，,][^，。！？\n]{2,8}[，,][^，。！？\n]{2,8}[，,][^，。！？\n]{2,8}[，,]")
_ENGLISH = re.compile(r"[A-Za-z]{3,}")


def mechanical_audit(text: str) -> dict:
    issues = {}
    n = max(1, len(text) // 1000)
    cliche = len(_CLICHE.findall(text))
    if cliche / n > 8:
        issues["维16/20套话比喻密度"] = [f"{cliche}/千字 (>8 偏高)"]
    # 维17 词汇疲劳：高频实词
    words = re.findall(r"[一-龥]{2,4}", text)
    from collections import Counter
    top = [(w, c) for w, c in Counter(words).most_common(8) if c > n * 6 and w not in ("自己", "一个", "这个", "什么")]
    if top:
        issues["维17词汇疲劳"] = [f"{w}×{c}" for w, c in top[:3]]
    # 维18 段落等长：方差过小
    paras = [len(p) for p in text.split("\n") if p.strip()]
    if len(paras) > 8:
        mean = sum(paras) / len(paras)
        var = sum((x - mean) ** 2 for x in paras) / len(paras)
        if var ** 0.5 < mean * 0.4:
            issues["维18段落等长"] = [f"段长变异系数{var**0.5/mean:.2f} (<0.4 太齐)"]
    if _PARALLEL.search(text) and len(_PARALLEL.findall(text)) > n:
        issues["维19整齐排比"] = [f"{len(_PARALLEL.findall(text))}处"]
    eng = _ENGLISH.findall(text)
    if eng:
        issues["维22英文泄漏"] = eng[:3]
    return issues


# ============ 人轴+故事性·LLM craft 审计（advisory 低权）============

async def craft_audit(cli, text: str) -> list[str]:
    from .gate import _safe_json
    sys_p, usr_t = prompts.CRAFT_AUDIT
    raw = await cli.complete("pk_final", sys_p, usr_t.format(text=text[:9000]),
                             json_mode=True, max_tokens=2500, temperature=0.3)
    r = _safe_json(raw)
    return (r or {}).get("issues", []) if isinstance(r, dict) else []


async def opening_immersion_audit(cli, opening_text: str, premise: str = "") -> dict:
    """C: 开篇代入感/premise连贯审计——补 human-eval-5 机器盲点(和谈笔力高却代入崩:Opus69 vs 人54)。
    专盯前1-2章读者第一眼:①代入锚(代入对了主角?有无原主/旁观视角开篇)②premise清晰(穿越/重生设定无矛盾;
    金手指主角自己发现非NPC点破)③代入感分。LLM-judge,advisory(不进交付门——重蹈A的覆辙之鉴:craft类机器判不可靠)。"""
    from .gate import _safe_json
    sys_p, usr_t = prompts.OPENING_IMMERSION
    try:
        raw = await cli.complete("pk_final", sys_p,
                                 usr_t.format(text=opening_text[:8000], premise=premise or "非穿越/重生"),
                                 json_mode=True, max_tokens=900, temperature=0.2)
    except Exception as e:
        return {"代入感分": None, "代入锚": None, "premise清晰": None, "issues": [f"(开篇代入审计跳过:{type(e).__name__})"]}
    r = _safe_json(raw)
    if not isinstance(r, dict):
        return {"代入感分": None, "代入锚": None, "premise清晰": None, "issues": []}
    return {"代入感分": r.get("代入感分"), "代入锚": r.get("代入锚"),
            "premise清晰": r.get("premise清晰"), "issues": r.get("issues") or []}


_CJK_SLASH = re.compile(r"[一-鿿]/[一-鿿]")


def broken_prose(ch_texts: list[str]) -> list[str]:
    """R8 残句/文本损伤确定性检测(advisory): ①长段落结尾停在逗号/顿号(断头句;冒号合法=引出下文,不报)
    ②CJK字符间裸斜杠(灵气ch31'狼首异/咔嚓!'类拼接损伤;【】系统面板内'炼器/炼丹'是合法UI,先剥掉)。
    保守规则,宁缺毋滥(灵气实测校准:冒号尾×6/面板斜杠×2全是误报)。"""
    out = []
    for i, t in enumerate(ch_texts):
        for ln in t.split("\n"):
            s = ln.strip()
            if len(s) >= 20 and s[-1] in "，、,":      # 含半角逗号(半角标点收尾本身即损伤)
                out.append(f"第{i + 1}章段尾残句:…{s[-15:]}")
            elif (2 <= len(s) <= 12 and s and "一" <= s[-1] <= "鿿"
                  and not any(c in "。！？…—，、：；,!?\"”’』」)" for c in s)):
                # 灵气ch31实形态: 孤行'狼首异'=名词中间截断,整行无任何标点
                out.append(f"第{i + 1}章孤行截断:「{s}」")
        plain = re.sub(r"【[^】]*】", "", t)            # 剥系统面板再查斜杠
        m = _CJK_SLASH.search(plain)
        if m:
            out.append(f"第{i + 1}章斜杠拼接:{plain[max(0, m.start() - 8):m.end() + 8]}")
    return out[:20]


_ERA_RE = re.compile(r"[五六七八九]零年代|19[5-8]\d|[五六七八九]十年代|公社|粮票|供销社")
_MODERN_RE = re.compile(r"智能手机|微信|聊天群|朋友圈|扫码|二维码|APP|直播间|网购|视频通话|点赞|WiFi|wifi|短视频|网约车|手机")


def era_anachronism(ch_texts: list[str], era_hint: str = "") -> list[str]:
    """R9 时代锚错位det(advisory): 年代文(语域/设定/开头含年代标记)出现现代物件。
    重生八零实测: 1984年出现手机报警/学校聊天群(评审坐实,承重40的主因之一)。"""
    head = "\n".join(ch_texts[:3])[:9000]
    if not (_ERA_RE.search(era_hint or "") or _ERA_RE.search(head)):
        return []
    out = []
    for i, t in enumerate(ch_texts):
        hits = sorted(set(_MODERN_RE.findall(t)))
        if hits:
            out.append(f"第{i + 1}章时代锚:{'/'.join(hits)}")
    return out[:20]


_BIG_EVENTS = ("渡劫", "天劫", "飞升", "大婚", "成亲", "登基", "颁奖", "决赛", "认亲", "册封")


def fix_event_unique(plan: dict) -> list[str]:
    """R10 大事件唯一 shift-left(团宠实证: macro把渡劫排进ch58又ch60,正文写4遍,铁律⑪prompt压不住):
    大事件关键词首次出现的章拥有该事件;**后续章**的场景brief前注禁演铁律(确定性,零LLM)。
    同章多场景同词不动(合法的两段式高潮)。"""
    owner: dict[str, int] = {}
    fixed = []
    for ci, ch in enumerate(plan.get("chapters", [])):
        scs = ch.get("scenes") or []
        text = str(ch.get("title", "")) + " ".join(
            str(sc.get("brief", "")) + str(sc.get("event_id", "")) for sc in scs if isinstance(sc, dict))
        for kw in _BIG_EVENTS:
            if kw not in text:
                continue
            if kw in owner and owner[kw] < ci:
                for sc in scs:
                    if isinstance(sc, dict) and kw in str(sc.get("brief", "")):
                        sc["brief"] = (f"(铁律:「{kw}」已在第{owner[kw] + 1}章演完,本场景绝不再写{kw}过程本身,"
                                       f"只写其后续/余波/启程) ") + (sc.get("brief") or "")
                        fixed.append(f"第{ci + 1}章「{kw}」→禁演(归属第{owner[kw] + 1}章)")
            else:
                owner.setdefault(kw, ci)
    return fixed
