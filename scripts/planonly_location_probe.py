"""plan-only 探针:只重跑 plan 阶段(载现成 bible+scenes),量 location 槽覆盖率/漂移。零起草、零重抽 mine。
判据:覆盖率高=LLM 真填了 location;漂移低=确从冻结地点表取名(非自由编)。不动真 plan.json(写 temp)。"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
os.environ["HIKI_SPINE"] = "1"                      # 必须:places 注入 + check_places 都 behind 此开关
from hiki.client import Client
from hiki import produce, audit

BOOK = Path("output/ZTGGX02751听说我死后成了反派白月光_20260617_full")
TMP = Path("output/_planonly_tmp"); TMP.mkdir(exist_ok=True)


async def main():
    bible = json.loads((BOOK / "bible.json").read_text(encoding="utf-8"))
    scenes = json.loads((BOOK / "scenes.json").read_text(encoding="utf-8"))
    canon = [p.get("name", "").strip() for p in (bible.get("places") or [])
             if isinstance(p, dict) and p.get("name")]
    print(f"冻结地点表({len(canon)}): {('、'.join(canon))[:120]}\n")

    cli = Client()
    r = await produce._stage_plan(cli, bible, scenes, TMP, 60, force=True)
    ordered = r["ordered"]
    n = len(ordered)
    locs = [(s.get("location") or "").strip() for s in ordered if (s.get("location") or "").strip()]
    drift = audit.check_places(bible, ordered)
    in_canon = [l for l in locs if any(c in l for c in canon)]

    print(f"\n=== location 槽实测({n} 场景) ===")
    print(f"覆盖率: {len(locs)}/{n} = {len(locs)/max(1,n):.0%}")
    print(f"命中冻结地点(子串): {len(in_canon)}/{len(locs)} = {len(in_canon)/max(1,len(locs)):.0%}")
    print(f"漂移(advisory,非canon): {len(drift)}/{n} = {len(drift)/max(1,n):.0%}")
    from collections import Counter
    print("\nlocation 分布 top:")
    for v, c in Counter(locs).most_common(12):
        tag = "✓canon" if any(x in v for x in canon) else "⚠漂移"
        print(f"   {c:>2}× {v[:24]} {tag}")
    if drift:
        print(f"\n漂移样本: {drift[:8]}")
    print(f"\n¥{cli.cost_cny:.2f} | {cli.calls} calls")


asyncio.run(main())
