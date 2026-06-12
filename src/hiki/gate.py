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


def structural_lite(plan: dict, dna: dict) -> dict:
    """轻量结构指标：场景/钩子/爽点覆盖（完整 5 指标见 metrics.py）。"""
    scenes = [sc for ch in plan.get("chapters", []) for sc in ch["scenes"]]
    dscenes = dna.get("scenes", [])
    hooks = sum(1 for s in dscenes if s.get("hooks"))
    payoffs = sum(1 for s in dscenes if s.get("payoffs"))
    n = len(dscenes) or 1
    return {"chapters": len(plan.get("chapters", [])), "scenes": len(scenes),
            "hook_coverage": round(hooks / n, 2), "payoff_coverage": round(payoffs / n, 2)}


async def reconcile_bible(cli: Client, bible: dict, issues: list[str]) -> dict:
    """闭环修复 step1：据审计问题校订圣经（补漏角色/纠错设定）。"""
    sys_p, usr_t = prompts.RECONCILE
    raw = await cli.complete("plan", sys_p, usr_t.format(
        bible=json.dumps(bible, ensure_ascii=False), issues="；".join(issues)),
        json_mode=True, max_tokens=3000, temperature=0.2)
    try:
        fixed = json.loads(raw)
        return fixed if fixed.get("protagonist") else bible
    except Exception:
        return bible


async def repair_chapter(cli: Client, text: str, bible: dict, issues: list[str]) -> str:
    """闭环修复 step2：据圣经定向修复本章不一致，其余不动。"""
    sys_p, usr_t = prompts.REPAIR
    out = await cli.complete("draft", sys_p, usr_t.format(
        bible=json.dumps(bible, ensure_ascii=False), issues="；".join(issues), text=text),
        max_tokens=8000, temperature=0.3)
    out = "\n".join(ln for ln in out.split("\n") if not _MARKER_RE.match(ln)).strip()
    return out or text


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
