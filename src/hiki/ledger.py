"""时序状态账本（A 架构·动态层）。

从 plan 的逐场景时序元数据确定性派生"此刻状态快照"，并做确定性时序校验
（场景/初遇/事件唯一性、伏笔 plant→payoff 序）。LLM 裁判对时序/冗余是瞎的
（人工校准实证），故时序一致性必须结构化 + 确定性，不走 LLM judge。
"""
from __future__ import annotations


def _rel_pairs(raw) -> list[list]:
    """安全取 [str,str] 关系对：LLM 偶吐嵌套/非串/非2元 → 跳过，绝不崩。"""
    out = []
    for p in raw or []:
        if isinstance(p, (list, tuple)) and len(p) == 2 \
                and isinstance(p[0], str) and isinstance(p[1], str) and p[0].strip() and p[1].strip():
            out.append([p[0].strip(), p[1].strip()])
    return out


def _scene_meta(sc: dict) -> dict:
    return {
        "event_id": (sc.get("event_id") or "").strip(),
        "first_appearances": [c.strip() for c in (sc.get("first_appearances") or []) if isinstance(c, str) and c.strip()],
        "relationships_formed": _rel_pairs(sc.get("relationships_formed")),
        "time_marker": (sc.get("time_marker") or "").strip(),
        "foreshadow_plant": [x for x in (sc.get("foreshadow_plant") or []) if x],
        "foreshadow_payoff": [x for x in (sc.get("foreshadow_payoff") or []) if x],
        "deaths": [c.strip() for c in (sc.get("deaths") or []) if isinstance(c, str) and c.strip()],
        "power_after": _rel_pairs(sc.get("power_after")),
    }


def validate_timeline(scenes: list[dict]) -> list[str]:
    """确定性时序硬校验：事件/初遇/登场唯一性（高可信、低误报）。伏笔序见 check_foreshadow(模糊advisory)。"""
    issues: list[str] = []
    seen_event, seen_appear, seen_rel = set(), set(), set()
    for i, raw in enumerate(scenes):
        m = _scene_meta(raw)
        if m["event_id"]:
            if m["event_id"] in seen_event:
                issues.append(f"场景{i}事件重复(同一beat写两遍): {m['event_id']}")
            seen_event.add(m["event_id"])
        for c in m["first_appearances"]:
            if c in seen_appear:
                issues.append(f"场景{i}: 「{c}」重复初次登场")
            seen_appear.add(c)
        for a, b in m["relationships_formed"]:
            key = frozenset((a, b))
            if key in seen_rel:
                issues.append(f"场景{i}: 「{a}/{b}」重复初遇/重复结识")
            seen_rel.add(key)
    return issues


def check_foreshadow(scenes: list[dict]) -> list[str]:
    """维7 伏笔序(模糊 advisory)：payoff 与任一 plant 有 2 字关键词重叠即算已铺垫，杜绝误报。
    第15鲁棒类: LLM偶把伏笔条目吐成数字/嵌套 → 只收str(len(int)崩过符术师整本)。"""
    issues, planted = [], []
    for raw in scenes:
        planted += [x for x in _scene_meta(raw)["foreshadow_plant"] if isinstance(x, str)]
    def _seeded(p: str) -> bool:
        return any(p[j:j + 2] in q for q in planted for j in range(len(p) - 1)) if planted else False
    planted2 = []
    for i, raw in enumerate(scenes):
        m = _scene_meta(raw)
        for p in m["foreshadow_payoff"]:
            if not isinstance(p, str):
                continue
            if not any(p[j:j + 2] in q for q in planted2 for j in range(max(0, len(p) - 1))):
                if not _seeded(p):                 # 全书任何 plant 都无关键词重叠才算孤儿
                    issues.append(f"场景{i}: 伏笔「{p[:14]}」疑似无铺垫(孤儿payoff)")
        planted2 += [x for x in m["foreshadow_plant"] if isinstance(x, str)]
    return issues


def dedup_first_meetings(scenes: list[dict]) -> int:
    """确定性去重(治'重复初遇'0连续性杀手)：每人只在首次出现保留 first_appearance、
    每对只首次保留 relationship；清掉后续场景的重复标记 → 审计干净 + state_before 准确
    (前情账本正确告知'已结识,不得再写初遇')。返回清掉的重复数。"""
    seen_appear, seen_rel, removed = set(), set(), 0
    for sc in scenes:
        new_fa = []
        for c in sc.get("first_appearances") or []:
            c = c.strip() if isinstance(c, str) else ""
            if c and c not in seen_appear:
                seen_appear.add(c); new_fa.append(c)
            elif c:
                removed += 1
        sc["first_appearances"] = new_fa
        new_rf = []
        for a, b in _rel_pairs(sc.get("relationships_formed")):
            key = frozenset((a, b))
            if key not in seen_rel:
                seen_rel.add(key); new_rf.append([a, b])
            else:
                removed += 1
        sc["relationships_formed"] = new_rf
    return removed


def state_before(scenes: list[dict], idx: int) -> dict:
    """场景 idx 之前的累积状态快照（确定性派生，不依赖 LLM、可并行）。"""
    appeared: list[str] = []
    rel: list[str] = []
    events: list[str] = []
    dead: list[str] = []
    power: dict[str, str] = {}
    time = ""
    for raw in scenes[:idx]:
        m = _scene_meta(raw)
        for c in m["first_appearances"]:
            if c not in appeared:
                appeared.append(c)
        for a, b in m["relationships_formed"]:
            tag = f"{a}↔{b}"
            if tag not in rel:
                rel.append(tag)
        for c in m["deaths"]:
            if c not in dead:
                dead.append(c)
        for who, p in m["power_after"]:          # plan 已经过 fix_power_monotonic,最近值即最高值
            power[who] = p
        if m["event_id"]:
            events.append(m["event_id"])
        if m["time_marker"]:
            time = m["time_marker"]
    return {"appeared": appeared, "relationships": rel, "events": events, "dead": dead,
            "power": power, "time": time}


def format_context(snap: dict) -> str:
    """把状态快照渲染成注入起草的"前情账本"。"""
    if not snap["events"]:
        return "（本场景为开篇，无前情）"
    parts = []
    if snap["appeared"]:
        parts.append("已登场人物: " + "、".join(snap["appeared"]))
    if snap["relationships"]:
        parts.append("已结识关系(不得再写初遇): " + "、".join(snap["relationships"]))
    if snap.get("dead"):
        parts.append("已死亡/永久退场(绝不得再出场/复活): " + "、".join(snap["dead"]))
    if snap.get("power"):
        parts.append("当前修为(此刻的真实境界——可以隐藏示弱,但绝不得写成更低境界/重新突破已过的境界): "
                     + "、".join(f"{w}={p}" for w, p in list(snap["power"].items())[:8]))
    if snap["events"]:
        parts.append("已发生事件(不得重写/重复/换角度重演): " + "；".join(snap["events"]))
    if snap["time"]:
        parts.append("当前时间: " + snap["time"])
    return "\n".join(parts)
