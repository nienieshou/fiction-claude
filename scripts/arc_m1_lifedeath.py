"""生死弧抽取 v2(M1) — 硬化召回,验证能否把主角从 uncertain 救成 dies_returns。

v1(arc_m0)病灶:单趟judge,高频主角(桑念4166)的真复活信号被"死意/想死/没死吧"比喻噪声淹 → uncertain。
v2 三处硬化:
  1. 去噪检索:实死动词(死亡/陨落/殒命…)与比喻"死"分开;复活强标记(复活/重生/死而复生)优先于弱(苏醒/睁眼)。
  2. 两段式:Pass1 只问"有无真实死亡(非比喻)+列事件";Pass2 对真死逐个判"之后是否归来"。
  3. 集成:Pass2 复活判定跑 3 票多数表决(治单趟抽风)。
判据(硬):桑念(真值=死而复生)能否从 v1 的 uncertain → dies_returns。能=召回过线,左移可设前向权威;否=只能 advisory。
"""
import asyncio
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki.prose_facts import split_chapters

STRONG_DEATH = ["死亡", "陨落", "殒命", "殒身", "丧命", "身亡", "气绝", "魂飞魄散", "毙命",
                "丧生", "身死", "死去", "惨死", "战死", "阵亡", "已死", "死了", "咽气", "尸体"]
REVIVE_STRONG = ["复活", "重生", "死而复生", "起死回生", "还魂", "转世", "诈死", "假死",
                 "并未死", "没有死", "其实没死", "活了过来", "活着回来", "死里逃生"]
REVIVE_WEAK = ["苏醒", "醒过来", "睁开眼", "又活", "还活着", "归来", "重新出现", "回来了"]
# 真值:独立 ground-truth(grep源书坐实),用于判 v2 是否救回
GT = {"桑念": "dies_returns", "路泽": "dies_returns", "施容": "dies_returns",
      "刀疤脸": "not_a_character", "瘦高个": "not_a_character"}


def sents(txt):
    return [s.strip() for s in re.split(r"[。！？\n]", txt) if s.strip()]


def evid(txt, who, kws, cap=50):
    out, n, pos = [], len(txt), 0
    for s in sents(txt):
        pos = txt.find(s, pos)
        if who in s and any(k in s for k in kws):
            out.append(f"[{int(100*pos/max(1,n))}%] {s[:90]}")
        if len(out) >= cap:
            break
    return out


SYS = ("你是中文小说事实核查员,只依据证据句判断,绝不脑补。严格区分:真实死亡 vs 比喻/担心/威胁"
       "('吓死''想死''没死吧?''死意');真实复活/重生/转世/假死归来 vs 仅是从睡梦中醒来或他人之死。只输出 JSON。")


async def pass1_deaths(cli, who, dev):
    u = (f"角色:{who}\n【含'{who}'+死亡词的证据句(书内位置%)】\n" + ("\n".join(dev) or "(无)")
         + f"\n\n问:源书中『{who}』本人是否发生过**真实死亡**(被杀/陨落/身亡,排除比喻与他人之死)?\n"
         '输出 JSON:{"has_real_death":true/false,"deaths":["位置%+一句引文",...],"note":"一句话"}')
    try:
        return json.loads(await cli.complete("fact_audit", SYS, u, json_mode=True, max_tokens=500, temperature=0.2))
    except Exception as e:
        return {"has_real_death": None, "err": str(e)[:80]}


async def pass2_returns(cli, who, deaths, rev, temp):
    u = (f"角色:{who}\n已确认其真实死亡事件:\n" + ("\n".join(f"- {d}" for d in (deaths or [])) or "(无)")
         + "\n\n【含'{0}'+复活/归来词的证据句】\n".format(who) + ("\n".join(rev) or "(无)")
         + f"\n\n问:『{who}』在上述死亡之后,源书是否让其**复活/重生/转世/假死归来/被证实没死**并继续活动?\n"
         '输出 JSON:{"returns":true/false,"mechanism":"机制一句","evidence":"最关键源文引证","confidence":"高|中|低"}')
    try:
        return json.loads(await cli.complete("fact_audit", SYS, u, json_mode=True, max_tokens=400, temperature=temp))
    except Exception:
        return {"returns": None}


async def arc_v2(cli, who, txt, freq):
    if freq == 0:
        return {"kind": "not_a_character", "dies": False, "returns": False}
    dev, rev = evid(txt, who, STRONG_DEATH), evid(txt, who, REVIVE_STRONG + REVIVE_WEAK)
    p1 = await pass1_deaths(cli, who, dev)
    if not p1.get("has_real_death"):
        return {"kind": "never_dies", "dies": False, "returns": False, "p1": p1}
    votes = await asyncio.gather(*[pass2_returns(cli, who, p1.get("deaths"), rev, t) for t in (0.2, 0.5, 0.8)])
    rets = [v.get("returns") for v in votes]
    returns = rets.count(True) >= 2
    kind = "dies_returns" if returns else "dies_final"
    best = next((v for v in votes if v.get("returns") == returns), votes[0])
    return {"kind": kind, "dies": True, "returns": returns, "vote": f"{rets.count(True)}/3",
            "mechanism": best.get("mechanism"), "evidence": best.get("evidence"), "p1_deaths": p1.get("deaths")}


def rewrite_revive(final_md, who, ch_a):
    chs = split_chapters(final_md)
    after = "\n".join(chs[max(0, ch_a - 1):])
    return [k for k in (REVIVE_STRONG + REVIVE_WEAK)
            if any((who in s and k in s) for s in sents(after))]


def classify(arc, rw, freq):
    k = arc.get("kind")
    if freq == 0 or k == "not_a_character":
        return "①凭空编造(源书无此人)"
    if k == "dies_returns":
        return "③忠实复活(门误杀)" if rw else "②漏复活情节(应补beat)"
    if k == "never_dies":
        return "①凭空编造(源书该角色不死)"
    if k == "dies_final":
        return "①b真矛盾·方向反(源永久死,复写却复活)"
    return "?待人工"


async def main():
    cli = Client()
    items = []
    for d in sorted(glob.glob("output/*_full")):
        ftp = Path(d) / "fact_table.json"
        if not ftp.exists():
            continue
        for f in (json.loads(ftp.read_text(encoding="utf-8")).get("findings") or []):
            if f.get("cat") == "生死" and f.get("ch_a") and f.get("ch_b"):
                items.append((d, f))
    print(f"待判 {len(items)} 条,跨 {len({d for d,_ in items})} 本\n")
    srcs = {d: (Path(next(iter(glob.glob(d+'/source/*.txt')))).read_text(encoding='utf-8', errors='ignore')
                if glob.glob(d+'/source/*.txt') else "") for d in {d for d, _ in items}}

    res = []
    for d, f in items:
        who, txt = f["who"], srcs[d]
        freq = txt.count(who) if txt else 0
        arc = await arc_v2(cli, who, txt, freq)
        fm = Path(d) / "final.md"
        rw = rewrite_revive(fm.read_text(encoding="utf-8"), who, f["ch_a"]) if fm.exists() else []
        cls = classify(arc, rw, freq)
        gt = GT.get(who)
        flag = ""
        if gt:
            flag = " ✅救回" if arc.get("kind") == gt else f" ❌仍错(真值={gt})"
        res.append({"who": who, "freq": freq, "die": f["ch_a"], "back": f["ch_b"],
                    "kind": arc.get("kind"), "vote": arc.get("vote"), "rw_revive": bool(rw),
                    "class": cls, "gt": gt, "mechanism": arc.get("mechanism")})
        print(f"  {who}({freq}) 死@{f['ch_a']} | v2:{arc.get('kind')} 票{arc.get('vote','-')} "
              f"复写复活:{bool(rw)} → {cls}{flag}")

    Path("output/_arc_m1.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    c = Counter(r["class"].split("(")[0] for r in res)
    n = len(res)
    fp = sum(v for k, v in c.items() if k.startswith("③"))
    drop = sum(v for k, v in c.items() if k.startswith("②"))
    print(f"\n=== v2 分类 ({n}) ===")
    for k, v in c.most_common():
        print(f"  {k}: {v}")
    # 真值复核
    checks = [r for r in res if r["gt"]]
    ok = sum(1 for r in checks if r["kind"] == r["gt"])
    print(f"\n真值复核(独立grep坐实): {ok}/{len(checks)} 命中")
    for r in checks:
        print(f"  {r['who']}: v2={r['kind']} 真值={r['gt']} {'✅' if r['kind']==r['gt'] else '❌'}")
    print(f"\n门误杀③+漏复活②(非真编造): {fp+drop}/{n}={ (fp+drop)/max(1,n):.0%}")
    print(f"¥{cli.cost_cny:.2f} | {cli.calls} calls → output/_arc_m1.json")
    sn = next((r for r in res if r["who"] == "桑念"), None)
    print("\n硬判据 桑念:", f"{sn['kind']} →", "✅过线(可设前向权威)" if sn and sn["kind"] == "dies_returns"
          else "❌未过线(召回仍不足,只能advisory)")


asyncio.run(main())
