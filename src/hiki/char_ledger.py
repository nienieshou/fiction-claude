"""角色状态账本(C1 起步: 仅死人复活)。纯确定性, 零 LLM/IO。

把死人复活在 6 路径/3 数据模型(plan维度/事实表findings/roster)上的重复检测
收口为单一来源: 各路把 死亡/出场事件 写入 ledger(带 source provenance),
ledger 确定性地配对成 RevivalRecord。门裁决按 source 优先级显式化(复现今天)。

后续 C2 修为 / C3 身份 / C5 name 谓词 往本模块加 sibling concern。
"""
from __future__ import annotations
from dataclasses import dataclass, field

# 门级来源优先级: facts(事实表权威) > plan(回退) > roster(仅叙事修复, 不进门)
SOURCE_PRECEDENCE = ("facts", "plan", "roster")
_GATING_SOURCES = frozenset({"facts", "plan"})   # roster 仅修复


@dataclass(frozen=True)
class DeathEvent:
    who: str
    ch: int
    clue: str
    source: str


@dataclass(frozen=True)
class AppearanceEvent:
    who: str
    ch: int
    source: str


@dataclass(frozen=True)
class RevivalRecord:
    who: str
    death_ch: int
    revive_ch: int
    clue: str
    sources: frozenset
    confidence: str = "高"   # 复活 findings 现状一律 高; 仅携带, 不驱动本期裁决


class RevivalLedger:
    """死亡/出场事件账本。record_* 写入, revivals() 确定性配对。"""

    def __init__(self) -> None:
        self._deaths: list[DeathEvent] = []
        self._apps: list[AppearanceEvent] = []

    def record_death(self, who: str, ch: int, clue: str = "", source: str = "facts") -> None:
        if who and isinstance(ch, int):
            self._deaths.append(DeathEvent(who.strip(), ch, clue or "", source))

    def record_appearance(self, who: str, ch: int, source: str = "facts") -> None:
        if who and isinstance(ch, int):
            self._apps.append(AppearanceEvent(who.strip(), ch, source))

    def revivals(self) -> list[RevivalRecord]:
        """同 who: 取最早 death_ch, 其后最早 appearance → 一条 RevivalRecord。
        多源命中并 sources。确定性(按 who 排序输出)。"""
        deaths_by_who: dict[str, list[DeathEvent]] = {}
        for d in self._deaths:
            deaths_by_who.setdefault(d.who, []).append(d)
        apps_by_who: dict[str, list[AppearanceEvent]] = {}
        for a in self._apps:
            apps_by_who.setdefault(a.who, []).append(a)

        out: list[RevivalRecord] = []
        for who in sorted(deaths_by_who):
            ds = sorted(deaths_by_who[who], key=lambda d: d.ch)
            death_ch = ds[0].ch
            clue = next((d.clue for d in ds if d.clue), "")
            later = sorted(a.ch for a in apps_by_who.get(who, []) if a.ch > death_ch)
            if not later:
                continue
            revive_ch = later[0]
            srcs = frozenset({d.source for d in ds}
                             | {a.source for a in apps_by_who.get(who, []) if a.ch > death_ch})
            out.append(RevivalRecord(who, death_ch, revive_ch, clue, srcs, "高"))
        return out

    def resolve_gating(self, verified: list[RevivalRecord]) -> list[RevivalRecord]:
        """按 source 优先级输出"进门"集合: 任一 gating 源(facts/plan)命中即进门;
        仅 roster 来源 = 仅叙事修复, 不进门。复现今天 P2 权威/P1 回退/P3 仅修复。"""
        return [r for r in verified if r.sources & _GATING_SOURCES]
