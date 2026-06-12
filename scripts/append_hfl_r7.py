"""一次性: HFL 账本追加第7跑 Fable 四维评分(scorer=fable,与人工分隔离)。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
recs = [
    {"date": "2026-06-11", "scorer": "fable", "round": 7, "title": "前妻归来：温医生她不将就",
     "source": "ZYGXY01847冷战三年，离婚当日纪总哭红了眼",
     "dims": {"拉力": 74, "笔力": 73, "人": 65, "承重": 40}, "total": 64.7,
     "comments": "拉力:单章钩子在线但章末钩子赖账(31章律师函无下文)爽点靠堆尸体;笔力:高光章近人写/低谷章纲要体方差大;人:女主单场主动但人设四次换皮(医师→实习→网红→合伙人);承重:纪老夫人二次死亡/女儿先于受孕/婚龄四版本/缅北线悬空",
     "auto_signals": {"final_consistent": True, "维14死人复活": 1, "章缝_检出": 23, "章缝_修复": 17, "暗黑比": 0.02},
     "version": "round7-fact-eval"},
    {"date": "2026-06-11", "scorer": "fable", "round": 7, "title": "全球屠神后，我开启星辰征途",
     "source": "CPBGX00192灵气复苏：开局无限合成",
     "dims": {"拉力": 72, "笔力": 68, "人": 60, "承重": 47}, "total": 63.0,
     "comments": "拉力:章章有钩但傀儡战钩子蒸发/一拳之威×3/十秒团灭;笔力:中后期震惊体+断头残句(ch31/32);人:主角自驱但零内面成长全员功能件;承重:6套等级体系混用/数值倒退互斥/冉剑锋龙御须佐同章死活/青阳天一武堂双名",
     "auto_signals": {"final_consistent": False, "维14死人复活": 0, "章缝_检出": 29, "章缝_修复": 20, "暗黑比": 0.02},
     "version": "round7-fact-eval"},
]
with open("assets/hfl.jsonl", "a", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
lines = [json.loads(ln) for ln in open("assets/hfl.jsonl", encoding="utf-8") if ln.strip()]
print(f"ok 共{len(lines)}行, 末两行scorer={[r['scorer'] for r in lines[-2:]]}")
