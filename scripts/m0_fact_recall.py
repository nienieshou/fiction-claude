"""对账环 M0: 在冷战/灵气两本已知病例上测召回。判据: 召回≥70%接产线,<50%降级advisory。
真值=第7跑 Fable 四维评审坐实清单(引文已逐条grep验过)。
匹配规则: 类别同 + 实体名互含(或出现在why里) + 章号差≤3 → 命中。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.prose_facts import fact_audit, split_chapters
from hiki.client import Client

TRUTH = {
    "output/ZYGXY01847冷战三年，离婚当日纪总哭红了眼_full": [
        {"cat": "生死", "who": "纪老夫人", "ch": 47},   # 15章死亡火化,47章复活,后又二次死亡
        {"cat": "时间轴", "who": "奚曼", "ch": 45},      # 女儿先于受孕: 24章B超 vs 45章妊娠八周
        {"cat": "数值", "who": "婚", "ch": 60},          # 婚龄四年/五年/三年/两年前四版本
        {"cat": "身份", "who": "白清霜", "ch": 59},      # 生母轮廓→下毒保姆
        {"cat": "身份", "who": "温苒", "ch": 31},        # 医师→实习→网红→合伙人四次换皮
    ],
    "output/CPBGX00192灵气复苏：开局无限合成_full": [
        {"cat": "体系", "who": "级", "ch": 32},          # ≥6套等级阶梯混用(气血卡/炼体层/品/境…)
        {"cat": "数值", "who": "司天宇", "ch": 3},       # 十一卡→气血7.2
        {"cat": "数值", "who": "陆景", "ch": 4},         # 16.12卡→档案14.32/入学检测2.1
        {"cat": "生死", "who": "冉剑锋", "ch": 59},      # 同章化血雾又被擒着奄奄一息
        {"cat": "生死", "who": "龙御", "ch": 60},        # 59章化光点消散,60章在陆景身边
        {"cat": "身份", "who": "武堂", "ch": 4},         # 青阳武堂vs天一武堂双名
    ],
}


def match(t: dict, f: dict) -> bool:
    if t["cat"] != f.get("cat"):
        return False
    who_f = str(f.get("who", ""))
    name_ok = (t["who"] in who_f or (who_f and who_f in t["who"])
               or t["who"] in str(f.get("why", "")))
    ch_ok = any(isinstance(f.get(k), int) and abs(f[k] - t["ch"]) <= 3
                for k in ("ch_a", "ch_b"))
    return name_ok and ch_ok


async def main():
    cli = Client()
    tot_t = tot_hit = tot_f = tot_v = 0
    for d, truths in TRUTH.items():
        chs = split_chapters((Path(d) / "final.md").read_text(encoding="utf-8"))
        rep = await fact_audit(cli, chs)
        fs = rep["findings"]
        hits = [t for t in truths if any(match(t, f) for f in fs)]
        miss = [t for t in truths if t not in hits]
        tot_t += len(truths); tot_hit += len(hits); tot_f += len(fs); tot_v += rep["n_verified"]
        print(f"\n== {d.split('/')[-1][:24]} 召回 {len(hits)}/{len(truths)} "
              f"报告{len(fs)}条(验真{rep['n_verified']}) 漏检:{[m['who'] + m['cat'] for m in miss]}")
        for f in fs:
            print(f"  [{f['cat']}]{'✓' if f['verified'] else '✗'} {f.get('who', '')}: "
                  f"ch{f.get('ch_a')}vs{f.get('ch_b')} {str(f.get('why', ''))[:44]}")
        (Path(d) / "fact_audit.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    rec = tot_hit / tot_t
    prec_proxy = tot_v / max(1, tot_f)
    print(f"\n总召回 {tot_hit}/{tot_t}={rec:.0%} | 引文验真率 {tot_v}/{tot_f}={prec_proxy:.0%} | ¥{cli.cost_cny:.2f}")
    print("判定:", "≥70% 接产线" if rec >= 0.7
          else ("50-70% 灰区,加重试/调prompt再测" if rec >= 0.5 else "<50% 降级advisory,路线B风险上调"))


asyncio.run(main())
