"""生死弧抽取 v3(M2) — 全文窗读 + 跨窗实体追踪。验证:全读能否抽到 grep 抽不到的死亡/复活。

v1/v2 病灶已定位:生死事件用代词/诗化叙述(桑念死亡现场"绝望地闭上眼…光灭",名+关键词不同句),
grep 检索结构性抽不到 → 判断器再强也没用。v3 改用产线 mine 同款思路:全文切窗、逐窗 LLM 通读、
对目标角色抽死亡/复活事件,再跨窗按顺序串成生死弧。
硬判据:桑念(真值=死而复生,v1=uncertain,v2=never_dies)能否被全读抽出"死亡@窗i + 复活@窗j>i"。
能 → "mine 集成全读弧抽取"路线坐实(可设前向权威);否 → 召回这道坎全读也迈不过。
范围:决定性难例 ZTGGX02751(桑念/纳珈/萧濯尘)。过线后再扩 路泽/施容 两本(各~3M字,~¥2-3/本)。
"""
import asyncio
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client

_A = sys.argv[1:]
BOOK = _A[0] if _A else "output/ZTGGX02751听说我死后成了反派白月光_20260617_full"
TARGETS = _A[1].split(",") if len(_A) > 1 else ["桑念", "纳珈", "萧濯尘"]
GT = {"桑念": "dies_returns"} if not _A else {}   # 独立grep坐实:"她复活后"/"醒过来的桑念"
N_WINDOWS = 20


def windows(txt, n):
    """按字数均分,贴近句末边界切窗。"""
    L = len(txt)
    step = L // n
    out, i = [], 0
    for w in range(n):
        end = L if w == n - 1 else min(L, (w + 1) * step)
        nb = txt.find("。", end)
        end = (nb + 1) if (nb != -1 and nb - end < 2000) else end
        out.append((w, txt[i:end]))
        i = end
        if i >= L:
            break
    return out


SYS = ("你是中文小说事件抽取器。只就给定片段、只针对指定角色,抽取其**本人**明确发生的"
       "【死亡】(被杀/陨落/身亡/魂飞魄散,含诗化描写如'闭上眼,气息消散')或"
       "【复活】(复活/重生/转世/还魂/被证实假死归来/死而复生)事件。"
       "排除比喻('吓死''想死')、他人之死、单纯睡醒。无事件就返回空。只输出 JSON。")


async def extract_window(cli, wi, text, targets):
    u = (f"片段(全书第{wi+1}/{N_WINDOWS}段)。目标角色:{('、'.join(targets))}\n\n"
         + text +
         '\n\n输出 JSON:{"events":[{"who":"角色名","type":"死亡|复活","quote":"≤40字引文"}]}')
    try:
        r = await cli.complete("chunk_extract", SYS, u, json_mode=True, max_tokens=800, temperature=0.2)
        return wi, (json.loads(r).get("events") or [])
    except Exception as e:
        return wi, [{"_err": str(e)[:60]}]


def arc_from_events(evs):
    """evs: [(wi,type)] 排序后。有死亡且其后(含同窗)有复活 → dies_returns。"""
    deaths = sorted(wi for wi, t in evs if t == "死亡")
    revives = sorted(wi for wi, t in evs if t == "复活")
    if not deaths:
        return "dies_returns" if revives else "never_dies"   # 只见复活也算返生型
    if revives and max(revives) >= min(deaths):
        return "dies_returns"
    return "dies_final"


async def main():
    src = next(iter(glob.glob(BOOK + "/source/*.txt")))
    txt = Path(src).read_text(encoding="utf-8", errors="ignore")
    print(f"源书 {len(txt)} 字 → {N_WINDOWS} 窗,目标 {TARGETS}\n")
    cli = Client()
    wins = windows(txt, N_WINDOWS)
    results = await asyncio.gather(*[extract_window(cli, wi, t, TARGETS) for wi, t in wins])

    per = {who: [] for who in TARGETS}
    for wi, evs in sorted(results):
        for e in evs:
            if e.get("who") in per and e.get("type") in ("死亡", "复活"):
                per[e["who"]].append((wi, e["type"], e.get("quote", "")))

    print("=== 跨窗事件 ===")
    for who in TARGETS:
        evs = per[who]
        kind = arc_from_events([(wi, t) for wi, t, _ in evs])
        gt = GT.get(who)
        flag = (" ✅" if kind == gt else " ❌仍错") if gt else ""
        flag += f"(真值={gt})" if gt and kind != gt else ""
        print(f"\n{who} → 弧:{kind}{flag}  事件{len(evs)}条")
        for wi, t, q in evs:
            print(f"   窗{wi+1} [{t}] {q[:42]}")

    Path("output/_arc_m2.json").write_text(json.dumps(
        {who: {"kind": arc_from_events([(wi, t) for wi, t, _ in per[who]]),
               "events": per[who]} for who in TARGETS}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n¥{cli.cost_cny:.2f} | {cli.calls} calls → output/_arc_m2.json")
    if "桑念" in per:
        sn = arc_from_events([(wi, t) for wi, t, _ in per["桑念"]])
        print("硬判据 桑念:", sn,
              "→ ✅全读抽到死亡+复活,路线坐实(grep抽不到的它抽到了)" if sn == "dies_returns"
              else "→ ❌全读也没抽到,召回坎未过")


asyncio.run(main())
