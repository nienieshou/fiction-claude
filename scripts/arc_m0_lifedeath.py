"""生死弧抽取原型(事前·源头) — 验证可行性。

问题:fact_audit 的"死人复活"门只查复写内部一致(死@ch_a→活@ch_b=矛盾),不读源、不识和解。
本原型对每条"生死"finding,从**源书**抽该角色的生死弧,把拒收拆成三类:
  ① 凭空编造  — 源书该角色根本不死(或不在源书) → 复写自己加了死亡,真缺陷
  ② 漏复活情节 — 源书有死后复生/假死归来,但复写保留死亡却剪掉了复活beat → 真缺陷(但修法=补复活)
  ③ 忠实复活  — 源书有死后复生,复写也写了复活beat → 门误杀(假阳性)

源弧靠 LLM(pro)读"角色×死亡/复活"证据句判定;复写是否含复活beat靠 grep final.md 兜底。
产出 output/_arc_m0.json + 假阳性率。判据:若 ②③(非真编造)占比高 → 证实门大面积误杀,值得把弧抽取左移到 mine。
"""
import asyncio
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki.prose_facts import split_chapters

DEATH_KW = ["死", "亡", "陨落", "殒命", "殒", "丧命", "毙", "咽气", "断气", "尸体",
            "遇害", "身亡", "战死", "阵亡", "气绝", "丧生", "身死", "魂飞魄散", "陨"]
REVIVE_KW = ["复活", "重生", "转世", "还魂", "活过来", "活了过来", "起死回生", "死而复生",
             "没死", "假死", "诈死", "醒过来", "苏醒", "复生", "又活", "重新睁",
             "归来", "还活着", "并未死", "未死", "重新出现", "活着回来", "死里逃生"]


def sentences(txt: str):
    return [s.strip() for s in re.split(r"[。！？\n]", txt) if s.strip()]


def evidence(txt: str, who: str, kws, cap=40):
    """含角色名 + 任一关键词的句子,带书内位置%。"""
    out, n = [], len(txt)
    pos = 0
    for s in sentences(txt):
        pos = txt.find(s, pos)
        if who in s and any(k in s for k in kws):
            pct = int(100 * pos / max(1, n))
            out.append(f"[{pct}%] {s[:90]}")
        if len(out) >= cap:
            break
    return out


SYS = ("你是中文小说事实核查员。只依据给定证据句判断某角色在**源书**里的生死弧,不脑补。"
       "区分:真实死亡 vs 比喻/威胁/担心(如'吓死''想死''没死吧?');"
       "真实复活/重生/转世/假死归来 vs 仅提及他人死亡。只输出 JSON。")


async def source_arc(cli, who, dev, rev):
    user = (f"角色:{who}\n\n【死亡相关证据句(书内位置%)】\n" + ("\n".join(dev) or "(无)")
            + "\n\n【复活/归来相关证据句】\n" + ("\n".join(rev) or "(无)")
            + "\n\n判断该角色在源书中的生死弧,输出 JSON:\n"
            '{"dies": true/false(是否真实死亡过), '
            '"returns": true/false(死后是否复活/重生/转世/假死归来/被证实没死), '
            '"kind": "never_dies|dies_returns|fake_death|dies_final|not_a_character|uncertain", '
            '"mechanism": "复活/归来机制一句话", "evidence": "最关键的一句源文引证", '
            '"confidence": "高|中|低"}')
    raw = await cli.complete("fact_audit", SYS, user, json_mode=True, max_tokens=600, temperature=0.3)
    try:
        return json.loads(raw)
    except Exception:
        return {"kind": "uncertain", "parse_error": raw[:200]}


def rewrite_has_revive(final_md: str, who: str, ch_a: int):
    """复写 ch_a 之后是否出现该角色的复活/归来beat(grep 兜底,粗)。"""
    chs = split_chapters(final_md)
    after = "\n".join(chs[max(0, ch_a - 1):])
    hits = [k for k in REVIVE_KW if (who[:2] in after and k in after
            and any((who in s and k in s) for s in sentences(after)))]
    return hits


def classify(arc, rw_hits, src_freq):
    if src_freq == 0 or arc.get("kind") == "not_a_character":
        return "①凭空编造(源书无此人/幻影配角)"
    kind = arc.get("kind")
    if kind in ("dies_returns", "fake_death") or (arc.get("dies") and arc.get("returns")):
        return "③忠实复活(门误杀)" if rw_hits else "②漏复活情节(应补beat)"
    if kind == "never_dies" or (arc.get("dies") is False):
        return "①凭空编造(源书该角色不死)"
    if kind == "dies_final":
        return "①b真矛盾·方向反(源书永久死,复写却让其复活)"
    return "?待人工(uncertain)"


async def main():
    cli = Client()
    findings = []
    for d in sorted(glob.glob("output/*_full")):
        ftp = Path(d) / "fact_table.json"
        if not ftp.exists():
            continue
        ft = json.loads(ftp.read_text(encoding="utf-8"))
        for f in (ft.get("findings") or []):
            if f.get("cat") == "生死" and f.get("ch_a") and f.get("ch_b"):
                findings.append((d, f))
    print(f"待判生死findings:{len(findings)} 条,跨 {len({d for d,_ in findings})} 本\n")

    srcs = {}
    for d in {d for d, _ in findings}:
        sp = next(iter(glob.glob(d + "/source/*.txt")), None)
        srcs[d] = Path(sp).read_text(encoding="utf-8", errors="ignore") if sp else ""

    results = []
    for d, f in findings:
        who = f["who"]
        txt = srcs[d]
        freq = txt.count(who) if txt else 0
        dev = evidence(txt, who, DEATH_KW)
        rev = evidence(txt, who, REVIVE_KW)
        arc = await source_arc(cli, who, dev, rev) if txt else {"kind": "no_source"}
        final_md = (Path(d) / "final.md")
        rw = rewrite_has_revive(final_md.read_text(encoding="utf-8"), who, f["ch_a"]) if final_md.exists() else []
        cls = classify(arc, rw, freq)
        results.append({"book": os.path.basename(d)[:26], "who": who, "src_freq": freq,
                        "die_ch": f["ch_a"], "back_ch": f["ch_b"],
                        "arc": arc, "rewrite_revive_hits": rw, "class": cls})
        print(f"  {who}({freq}) 死@{f['ch_a']}→活@{f['ch_b']} | 源弧:{arc.get('kind')}"
              f"(dies={arc.get('dies')},returns={arc.get('returns')}) | 复写复活:{bool(rw)} → {cls}")

    Path("output/_arc_m0.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    c = Counter(r["class"].split("(")[0] for r in results)
    total = len(results)
    fp = sum(v for k, v in c.items() if k.startswith("③"))
    drop = sum(v for k, v in c.items() if k.startswith("②"))
    real = sum(v for k, v in c.items() if k.startswith("①"))
    print(f"\n=== 分类汇总 ({total} 条) ===")
    for k, v in c.most_common():
        print(f"  {k}: {v}")
    print(f"\n门假阳性(③忠实复活,本不该拒): {fp}/{total}={fp/max(1,total):.0%}")
    print(f"漏复活情节(②真缺陷但修法=补beat,非un-kill): {drop}/{total}={drop/max(1,total):.0%}")
    print(f"真编造/真矛盾(①,门判对): {real}/{total}={real/max(1,total):.0%}")
    print(f"\n¥{cli.cost_cny:.2f} | {cli.calls} calls → output/_arc_m0.json")
    verdict = ("弧抽取能把忠实复活从真缺陷里分出来 → 值得左移到 mine 设为前向权威"
               if (fp + drop) >= total * 0.4 else "假阳性不显著,门基本判对,左移收益有限")
    print("判定:", verdict)


asyncio.run(main())
