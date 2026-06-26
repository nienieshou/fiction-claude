"""质量闸门（PRD §6 / A5）。替掉无用的 DeepSeek 自评。

三层：① 确定性机械检（0-LLM，不可刷分）② 对照圣经的连续性审计（LLM 查事实，非质量判断，不 Goodhart）
③ 结构指标（从规划计算）。④ 外部金标 PK 待 M-1 金标库就绪后接入。
"""
from __future__ import annotations
import json
import re
from . import prompts
from .client import Client

_MARKER_RE = re.compile(r"^\s*(.*场景[：:].*|---+|===+)\s*$")


def deterministic_checks(text: str, bible: dict, target_chars: int) -> list[str]:
    """0-LLM 机械检：漏标记 / 漏标题 / 篇幅。可靠、不可刷分。"""
    issues: list[str] = []
    for ln in text.split("\n"):
        s = ln.strip()
        if _MARKER_RE.match(ln):
            issues.append(f"漏场景标记: {s[:18]}")
        elif s.startswith("#") and not s.startswith("# 第"):
            issues.append(f"漏标题: {s[:18]}")
    ratio = len(text) / target_chars if target_chars else 1.0
    if ratio > 1.2:
        issues.append(f"超长 {ratio:.0%}（目标{target_chars}字）")
    elif ratio < 0.7:
        issues.append(f"过短 {ratio:.0%}")
    return issues


def _repair_json(s: str):
    """修复截断 JSON：从首个 { 起，平衡未闭合的字符串/括号，回收早出现的字段。
    （DeepSeek 思考模式偶发吐到一半截断，早字段如 protagonist/central_conflict 仍可救。）"""
    i = s.find("{")
    if i < 0:
        return None
    s = s[i:]
    stack, in_str, esc = [], False, False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    res = s
    if in_str:
        res += '"'
    res = re.sub(r"[:,]\s*$", "", res.rstrip())          # 去悬挂的 , 或 :
    res = re.sub(r',\s*"[^"]*"\s*$', "", res)            # 去结尾只剩 key 无值
    for ch in reversed(stack):
        res += "}" if ch == "{" else "]"
    # 逐步回退尾部直到能解析（救最大可解析前缀）
    for _ in range(40):
        try:
            return json.loads(res)
        except Exception:
            cut = max(res.rfind("}"), res.rfind("]"))
            if cut <= 0:
                return None
            inner = res[:cut + 1]
            depth = inner.count("{") - inner.count("}") + inner.count("[") - inner.count("]")
            res = inner + ("}" * max(0, inner.count("{") - inner.count("}"))) + \
                ("]" * max(0, inner.count("[") - inner.count("]")))
            if depth <= 0:
                try:
                    return json.loads(res)
                except Exception:
                    res = inner
    return None


def _safe_json(s: str):
    """健壮解析：去 fence、整体解析、首尾大括号、截断修复 四级兜底。
    只返回 dict/list——LLM 偶吐裸字符串/数字字面量(json.loads 成功返回 str)会让调用方
    .get() 崩(冷战两跑 AttributeError 'str' object 根因类)，一律视为解析失败。"""
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1].lstrip("json").strip()
    try:
        r = json.loads(s)
        if isinstance(r, (dict, list)):
            return r
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        try:
            r = json.loads(m.group())
            if isinstance(r, (dict, list)):
                return r
        except Exception:
            pass
    r = _repair_json(s)               # 截断救援（无闭合括号时）
    return r if isinstance(r, (dict, list)) else None


async def continuity_check(cli: Client, text: str, bible: dict) -> dict:
    """对照圣经查人名/性别/设定一致性（LLM 查事实，非评质量）。健壮 JSON + 重试。"""
    sys_p, usr_t = prompts.CONTINUITY
    usr = usr_t.format(bible=json.dumps(bible, ensure_ascii=False), text=text[:8000])
    for _ in range(2):
        raw = await cli.complete("pk_final", sys_p, usr, json_mode=True, max_tokens=4000, temperature=0.2)
        r = _safe_json(raw)
        if isinstance(r, dict) and "consistent" in r:
            return r
    return {"consistent": None, "issues": ["(审计解析失败)"]}


# 交付门阈值默认（人工 6+10 本校准;config/pipeline.yaml ship_gate 可覆盖,改动须回放验证)
# 阈值经 human-eval-5(2026-06-15, docs/evidence/human_eval5_calibration.md)重标。
# 真值表证伪了旧的承重微观硬门：5 本里机器信号与人类承重/可追**不单调可分**——
# 最可追本(隐婚 总76)含 6 处重演(全场最多)、4 数值矛盾;不可追本(武神60.8)仅 2 处重演。
# 故承重微观计数(重演/spine薄网/final_consistent/预告跳过)降为 advisory,硬门只留"灾难级+定类硬伤"。
SHIP_GATE_DEFAULTS = {
    "too_short_chapters": 3,         # 过短<70% 章数 ≥ → 拦(定类质量地板,非承重)
    "dark_ratio_max": 0.25,          # 暗黑饱和比 > → 拦(定类)
    "seam_residual_max": 8,          # 残缝 > → 拦(章缝;human-eval 未越线,保留)
    "reenact_min": 7,                # 事件重演 ≥ → 拦。旧=1(误杀100%);human可追本含6处→只挡极端泛滥
    "spine_net_min": 6,              # Spine薄网真矛盾(数值+身份) ≥ → 拦。旧=2;human可追本含4→留头寸
    "block_on_climax_skip": False,   # 预告跳过 是否硬拦。旧=硬拦;仅命中可追本(星厨74.8"基本连得上")→降advisory
    "block_on_final_inconsistent": False,  # final_consistent=否 是否硬拦。旧=硬拦;反相关(只命中隐婚/团宠两可追本)→降advisory
    "intra_repeat_thr": 0.08,        # 章内12-gram双半重合 > → 判整章双版本(检测侧用,非门内)
    "opening_immersion_min": 40,     # 开篇代入感分 < → 拦(读者无法代入的灾难地板)。editor-eval-2(量产盘10本)校准:
    "early_repeat_immersion_cap": 30,  # 早段重复(ch1-k 同事件重述)检出>0 → 代入感封顶此值,复用上面硬门。
}                                    #   买来代入感30→人承重40(最低,"第二章重复了")拦;其余≥65→承重≥50 安全;0=关闭。
                                     #   注:这是 eval-5"craft 类不进门"的定向例外——仅最低段灾难地板,且 best-of-N 重掷救济,非裁质量


def evaluate_ship_gate(sig: dict, thr: dict | None = None) -> list[str]:
    """交付门策略（纯函数,可测,阈值来自 config）。signals dict → ship_issues 列表。
    行为与旧内联门等价(D1 重构);阈值经人工校准,默认见 SHIP_GATE_DEFAULTS。signals 键见 produce.run() 组装处。"""
    t = {**SHIP_GATE_DEFAULTS, **(thr or {})}
    issues: list[str] = []
    if sig.get("阵营串线", 0) > 0:
        issues.append(f"阵营串线{sig['阵营串线']}条(canon级硬伤)")
    if sig.get("过短章数", 0) >= t["too_short_chapters"]:
        issues.append(f"{sig['过短章数']}章过短<70%(二次扩写后仍稀薄)")
    if sig.get("暗黑比", 0) > t["dark_ratio_max"]:
        issues.append(f"暗黑饱和(暗黑比{sig['暗黑比']}>{t['dark_ratio_max']})")
    if sig.get("预告跳过") and t.get("block_on_climax_skip"):
        issues.append(f"预告事件被跳过未演({sig['预告跳过']})")
    if sig.get("plan维14复活", 0) > 0 and not sig.get("事实表跑过"):
        issues.append(f"死人复活{sig['plan维14复活']}处(plan维14,事实表未跑兜底)")
    if sig.get("事实表复活残留", 0) > 0:
        issues.append(f"事实表死人复活{sig['事实表复活残留']}处(verify确认,修复未净)")
    if sig.get("残缝", 0) > t["seam_residual_max"]:
        issues.append(f"残缝{sig['残缝']}处(章缝修复采用不足)")
    if not sig.get("final_consistent", True) and t.get("block_on_final_inconsistent"):
        issues.append("final_consistent=false(连续性残留)")
    if sig.get("事件重演", 0) >= t["reenact_min"]:
        issues.append(f"事件重演{sig['事件重演']}处(控制面核对)")
    if sig.get("章内双版本"):
        issues.append(f"章内双版本{sig['章内双版本']}(整章重演)")
    if sig.get("数值真矛盾", 0) + sig.get("身份真矛盾", 0) >= t["spine_net_min"]:
        issues.append(f"Spine薄网真矛盾: 数值{sig.get('数值真矛盾', 0)}/身份{sig.get('身份真矛盾', 0)}"
                      f"条(起草违反冻结事实,详见fact_table.json)")
    if sig.get("承重审计崩溃"):
        issues.append("承重事实审计非预期中断,结果不可信(不可判定一致性,需重跑)")
    imm = sig.get("开篇代入感")
    if sig.get("早段重复", 0) and isinstance(imm, (int, float)):
        imm = min(imm, t.get("early_repeat_immersion_cap", 30))   # 早段同事件重述=代入崩,封顶
    if isinstance(imm, (int, float)) and t.get("opening_immersion_min", 0) and imm < t["opening_immersion_min"]:
        issues.append(f"开篇代入感{imm}<{t['opening_immersion_min']}(读者无法代入,editor-eval-2:30→人承重40)")
    return issues


def structural_lite(plan: dict, dna: dict) -> dict:
    """轻量结构指标：场景/钩子/爽点覆盖（plan/dna 派生，确定性）。"""
    scenes = [sc for ch in plan.get("chapters", []) for sc in ch["scenes"]]
    dscenes = dna.get("scenes", [])
    hooks = sum(1 for s in dscenes if s.get("hooks"))
    payoffs = sum(1 for s in dscenes if s.get("payoffs"))
    n = len(dscenes) or 1
    return {"chapters": len(plan.get("chapters", [])), "scenes": len(scenes),
            "hook_coverage": round(hooks / n, 2), "payoff_coverage": round(payoffs / n, 2)}


async def gold_pk(cli: Client, scene: str, gold: str) -> dict:
    """大件①：场景 vs 金标(95上锚) 成对 PK，判是否达标 + 差距。"""
    sys_p, usr_t = prompts.GOLD_PK
    for _ in range(2):
        raw = await cli.complete("pk_final", sys_p, usr_t.format(gold=gold, scene=scene[:4000]),
                                 json_mode=True, max_tokens=2500, temperature=0.2)
        r = _safe_json(raw)
        if isinstance(r, dict) and "reaches_gold" in r:
            return r
    return {"reaches_gold": None, "gap": "(金标PK解析失败)"}


async def refine_scene(cli: Client, scene: str, gold: str, gap: str) -> str:
    """大件②：对照金标按差距精修场景（学语感不照抄情节）。"""
    sys_p, usr_t = prompts.REFINE
    out = await cli.complete("draft", sys_p, usr_t.format(gold=gold, gap=gap, scene=scene),
                             max_tokens=8000, temperature=0.8)
    out = "\n".join(ln for ln in out.split("\n") if not _MARKER_RE.match(ln)).strip()
    return out or scene
