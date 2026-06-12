"""R11-3 灰区判读校验: 8个已知案例(4真矛盾/4噪声),要求 真≥3/4保留 且 噪声≥3/4滤除。"""
import asyncio
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki import prompts, gate
from hiki.client import Client

CASES = [  # (claim, 期望real)
    ("正文中沈清梨母亲已死(土葬十几年),第18章又称母亲李雪活着被囚京城,第46章又称李雪是敌方棋子现任妻", True),
    ("正文'青阳武堂'与圣经'天一武堂'同一机构两个名字并存", True),
    ("圣经中骆恒为金丹期,正文却回忆其为炼气九层突破", True),
    ("冥夙圣经设定为神龙,但正文自称为银蛇本体,物种矛盾", True),
    ("正文第2章出现圣经未设定的角色'郑金花'(一次性病友龙套)", False),
    ("魔皇(篡位者)角色未在圣经定义", False),
    ("宋糯使用冰系异能凝冰刺,圣经设定她只有水木双系", False),
    ("揽月goal从求死变为合作夺位,与圣经初始goal不符", False),
]
BIBLE = '{"protagonist":{"name":"主角","power":"练气"},"characters":[{"name":"骆恒","power":"金丹期"}],"setting":"修仙世界"}'


async def main():
    cli = Client()
    sys_p, usr_t = prompts.ADVISORY_VERIFY
    res = await asyncio.gather(*[
        cli.complete("chunk_extract", sys_p, usr_t.format(claim=c, bible_excerpt=BIBLE),
                     json_mode=True, max_tokens=200, temperature=0.1) for c, _ in CASES])
    keep_t = drop_f = 0
    for (c, want), r in zip(CASES, res):
        v = gate._safe_json(r) or {}
        got = v.get("real")
        ok = (got is not False) if want else (got is False)
        if want and ok:
            keep_t += 1
        if not want and ok:
            drop_f += 1
        print(f"{'✓' if ok else '✗'} 期望{'真' if want else '噪'} 判{got}: {c[:36]} | {v.get('why', '')}")
    print(f"\n真矛盾保留 {keep_t}/4 | 噪声滤除 {drop_f}/4 | "
          f"{'✅达标' if keep_t >= 3 and drop_f >= 3 else '⛔不达标,调prompt'} | ¥{cli.cost_cny:.2f}")


asyncio.run(main())
