"""A2' 事实表对账召回测试(同 m0_fact_recall 的11条真值)。判据: ≥50% 即入产线 advisory。
先跑 cross_check 纯函数自测(零API),再真API测两本。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.prose_facts import fact_table_audit, cross_check, split_chapters
from hiki.client import Client

# ---- 纯函数自测 ----
_t = [
    {"deaths": [{"who": "纪老夫人", "clue": "中风死亡"}], "present": ["温苒"], "power": [], "identity": [], "numbers": [["婚龄", "四年"]]},
    {"deaths": [], "present": ["温苒", "纪老夫人"], "power": [["陆景", "气血16.12卡"]], "identity": [["武堂", "青阳武堂"]], "numbers": []},
    {"deaths": [], "present": ["温苒"], "power": [["陆景", "气血14.32卡"]], "identity": [["武堂", "天一武堂"]], "numbers": [["婚龄", "三年"]]},
]
fs = cross_check(_t)
cats = {f["cat"] for f in fs}
assert any(f["cat"] == "生死" and f["who"] == "纪老夫人" and f["ch_b"] == 2 for f in fs), fs
assert any(f["cat"] == "数值" and f["who"] == "陆景" for f in fs), fs
assert any(f["cat"] == "身份" and f["who"] == "武堂" for f in fs), fs
assert any(f["cat"] == "数值" and f["who"] == "婚龄" for f in fs), fs
print("cross_check 纯函数自测 ok:", len(fs), "条")

TRUTH = {
    "output/ZYGXY01847冷战三年，离婚当日纪总哭红了眼_full": [
        {"cat": "生死", "who": "纪老夫人", "ch": 47},
        {"cat": "时间轴", "who": "奚曼", "ch": 45},
        {"cat": "数值", "who": "婚", "ch": 60},
        {"cat": "身份", "who": "白清霜", "ch": 59},
        {"cat": "身份", "who": "温苒", "ch": 31},
    ],
    "output/CPBGX00192灵气复苏：开局无限合成_full": [
        {"cat": "体系", "who": "级", "ch": 32},
        {"cat": "数值", "who": "司天宇", "ch": 3},
        {"cat": "数值", "who": "陆景", "ch": 4},
        {"cat": "生死", "who": "冉剑锋", "ch": 59},
        {"cat": "生死", "who": "龙御", "ch": 60},
        {"cat": "身份", "who": "武堂", "ch": 4},
    ],
}


def match(t: dict, f: dict) -> bool:
    if t["cat"] != f.get("cat") and not (t["cat"] == "体系" and f.get("cat") == "数值"):
        return False                                  # 体系混用常以数值倒退形态被抓,算命中
    who_f = str(f.get("who", ""))
    name_ok = (t["who"] in who_f or (who_f and who_f in t["who"])
               or t["who"] in str(f.get("why", "")))
    ch_ok = any(isinstance(f.get(k), int) and abs(f[k] - t["ch"]) <= 5
                for k in ("ch_a", "ch_b"))
    return name_ok and ch_ok


async def main():
    cli = Client()
    tot_t = tot_hit = 0
    for d, truths in TRUTH.items():
        chs = split_chapters((Path(d) / "final.md").read_text(encoding="utf-8"))
        rep = await fact_table_audit(cli, chs)
        fs = rep["findings"]
        hits = [t for t in truths if any(match(t, f) for f in fs)]
        miss = [t for t in truths if t not in hits]
        tot_t += len(truths)
        tot_hit += len(hits)
        print(f"\n== {d.split('/')[-1][:24]} 召回 {len(hits)}/{len(truths)} "
              f"报告{len(fs)}条(高置信{rep['n_high']}) 漏检:{[m['who'] + m['cat'] for m in miss]}")
        for f in fs:
            print(f"  [{f['cat']}/{f['conf']}] {f.get('who', '')}: {str(f.get('why', ''))[:50]}")
        (Path(d) / "fact_table.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    rec = tot_hit / tot_t
    print(f"\n总召回 {tot_hit}/{tot_t}={rec:.0%} | ¥{cli.cost_cny:.2f}")
    print("判定:", "≥50% 入产线advisory" if rec >= 0.5 else "<50% 继续只当实验工具")


asyncio.run(main())
