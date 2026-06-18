"""项1 可行性探针:文本复活beat检测能否区分 ③忠实复活(上官尔蓝,清晰重生→该放) vs ②漏复活(桑念,模糊→该拦)。
判据:上官尔蓝 beat_rendered=True、桑念 beat_rendered=False。成立则文本beat检测=项1正解(优于维14取交集)。零起草。"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki.prose_facts import split_chapters

CASES = [("output/_revalidate/ZTGGY02021_revalidate", "上官尔蓝", 1, 8, "基线认证·疑清晰重生"),
         ("output/_revalidate/ZTGGX02751_revalidate", "桑念", 51, 53, "已验:树精重生(应③)"),
         ("output/_revalidate/ZTGGX02751_revalidate", "纳珈", 28, 34, "无弧·真②候选")]

SYS = ("你是连续性核查员,只依据给定正文判断,不脑补。判断'死后又出场'是否被文本**清楚交代了复活/归来机制**"
       "(复活/重生/转世/还魂/假死被揭穿/被救活等,读者能看懂他为何还活着),还是文本只是让死者又出现却**毫无交代**(矛盾)。只输出JSON。")


async def main():
    cli = Client()
    for d, who, ca, cb, note in CASES:
        chs = split_chapters((Path(d) / "final.md").read_text(encoding="utf-8"))
        seg = "\n\n".join(chs[ca - 1:cb])[:24000]      # 死亡章~再现章
        u = (f"角色「{who}」在第{ca}章死亡、第{cb}章又作为活人出场。下面是第{ca}–{cb}章正文。\n"
             f"问:这之间文本**是否清楚交代了「{who}」复活/归来的机制**?\n"
             '输出JSON:{"beat_rendered":true/false,"mechanism":"若有,一句话机制;无则空","evidence":"关键引证≤30字"}\n\n'
             + seg)
        raw = await cli.complete("fact_audit", SYS, u, json_mode=True, max_tokens=900, temperature=0.2)
        try:
            r = json.loads(raw)
        except Exception:
            r = {"beat_rendered": None, "raw": raw[:160]}
        verdict = "③放行(advisory)" if r.get("beat_rendered") else "②拦截(gate)"
        print(f"{who}({note}): beat_rendered={r.get('beat_rendered')} → {verdict}")
        print(f"   机制={r.get('mechanism')!r} 证={r.get('evidence')!r}")
        if r.get("beat_rendered") is None:
            print(f"   [DEBUG raw]={r.get('raw') or raw[:160]!r}")
    print(f"\n¥{cli.cost_cny:.2f} | {cli.calls} calls")


asyncio.run(main())
