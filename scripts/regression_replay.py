"""飞轮②: 回归重放硬门——每轮工程落地后跑,银行里已能命中的病例(baseline_hit=true)
若变 miss,本轮工程不得进产线(防 r7缺陷R9复发类无声回吐)。
首跑 --baseline 回填 baseline_hit。确定性检测免费,LLM 类只对病例定向调用(~¥0.3)。
用法: python scripts/regression_replay.py [--baseline]
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki import prompts, gate, audit
from hiki.client import Client
from hiki.prose_facts import split_chapters, fact_table_audit
from hiki import prose_continuity

BANK = Path("assets/defect_bank.jsonl")
_cache: dict[str, list[str]] = {}


def chs_of(path: str) -> list[str]:
    if path not in _cache:
        _cache[path] = split_chapters((Path(path) / "final.md").read_text(encoding="utf-8"))
    return _cache[path]


async def hit(cli: Client, e: dict) -> bool | None:
    """该病例当前是否被对应仪器命中。None=该仪器无自动重放(none/人工类)。"""
    det = e["detector"]
    try:
        chs = chs_of(e["path"])
    except FileNotFoundError:
        return None
    ch = e.get("ch") or 1
    if det == "broken_prose":
        return any(f"第{ch}章" in x for x in audit.broken_prose(chs))
    if det == "era_anachronism":
        return any(f"第{ch}章" in x for x in audit.era_anachronism(chs))
    if det == "adj_dup":                              # 定向只查该对
        sys_c, usr_c = prompts.ADJ_DUP_CHECK
        for t in range(3):
            raw = await cli.complete("chunk_extract", sys_c,
                                     usr_c.format(prev=chs[ch - 2][-1800:], head=chs[ch - 1][:2200]),
                                     json_mode=True, max_tokens=300, temperature=0.1 + 0.1 * t)
            r = gate._safe_json(raw) or {}
            if isinstance(r, dict) and "dup" in r:
                return r.get("dup") is True
        return False
    if det == "fact_table_deaths":                    # 全书事实表跑一遍,看该人物是否在生死finding里
        ft = await fact_table_audit(cli, chs)
        who = e.get("quote", "")
        return any(f.get("cat") == "生死" and who in str(f.get("who", "")) for f in ft["findings"])
    if det == "fact_table_power":
        ft = await fact_table_audit(cli, chs)
        return any(f.get("cat") == "数值" and f.get("conf") == "中" for f in ft["findings"])
    return None                                       # none/advisory_verify/content_filter/ending_check=暂无定向重放


async def main():
    baseline = "--baseline" in sys.argv
    entries = [json.loads(ln) for ln in BANK.read_text(encoding="utf-8").splitlines() if ln.strip()]
    cli = Client()
    # fact_table 类同书去重跑(贵的只跑一次/书)
    results = []
    for e in entries:
        h = await hit(cli, e)
        results.append(h)
        tag = {True: "命中", False: "MISS", None: "无自动重放"}[h]
        print(f"{e['id']} [{e['detector']}] {e['book']} ch{e.get('ch')} {e['issue'][:24]} → {tag}")
    regressions = []
    for e, h in zip(entries, results):
        if baseline:
            e["baseline_hit"] = h
        elif e.get("baseline_hit") is True and h is False:
            regressions.append(e["id"])
    if baseline:
        BANK.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
                        encoding="utf-8")
        n_hit = sum(1 for h in results if h is True)
        print(f"\nbaseline 回填: 命中 {n_hit} / 可重放 {sum(1 for h in results if h is not None)}"
              f" / 总 {len(entries)} | ¥{cli.cost_cny:.2f}")
    else:
        print(f"\n回归判定: {'⛔ 回吐! ' + str(regressions) + ' → 本轮工程不得进产线' if regressions else '✅ 无回吐'}"
              f" | ¥{cli.cost_cny:.2f}")


asyncio.run(main())
