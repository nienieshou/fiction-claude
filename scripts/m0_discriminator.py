"""判别器验证实验(决定 test-time compute 路线生死):
对照PK(GOLD_PK,候选vs金标打分)和绝对锦标赛(PICK)选出的候选,是否真的更好(Fable盲评)?
- 判别器有区分力 → 大N选优能吃模型尾部,值得开 test-time compute;
- 判别器是噪声(Top1≈Bottom1) → 大N白烧,只剩微调。
每场景生成N候选,GOLD_PK打分取Top1/Bottom1,盲分配A/B供人盲评;真值另存。
"""
import asyncio, json, sys, random
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki import gate, prompts
from hiki.slice_validate import _draft_candidates, _load_gold

D = Path("output/ZYGGY03733团宠小师妹靠摆烂带飞全宗门_full")
bible = json.load(open(D / "bible.json", encoding="utf-8"))
plan = json.load(open(D / "plan.json", encoding="utf-8"))
voice = bible.get("voice", "网文白话")
gold = _load_gold(voice)
ordered = [sc for ch in plan["chapters"] for sc in ch["scenes"]]
spc = max(1.0, len(ordered) / max(1, len(plan["chapters"])))
target = int(3500 / spc * 0.92)
N = 6
random.seed(42)
# 4场景: 开篇/结局高点 + 2普通(1/3,2/3处)
idxs = [0, len(ordered) // 3, 2 * len(ordered) // 3, len(ordered) - 2]


async def pick_winner(cli, cands):
    labeled = "\n\n".join(f"【候选{i+1}】\n{c[:2500]}" for i, c in enumerate(cands))
    sys_p, usr_t = prompts.PICK
    raw = await cli.complete("pk_final", sys_p, usr_t.format(n=len(cands), candidates=labeled),
                             json_mode=True, max_tokens=300, temperature=0.2)
    r = gate._safe_json(raw) or {}
    w = r.get("winner")
    return (w - 1) if isinstance(w, int) and 1 <= w <= len(cands) else 0


async def main():
    cli = Client()
    blind, truth = [], []
    for si, idx in enumerate(idxs):
        sc = ordered[idx]
        cands = await _draft_candidates(cli, sc, bible, voice, target, N, gold=gold, context="")
        cands = [c for c in cands if c and len(c) > 200]
        if len(cands) < 3:
            continue
        pks = await asyncio.gather(*[gate.gold_pk(cli, c, gold) for c in cands])
        scores = [float(pk.get("score") or 0) for pk in pks]
        order = sorted(range(len(cands)), key=lambda i: scores[i], reverse=True)
        top, bot = order[0], order[-1]
        pickw = await pick_winner(cli, cands)
        ab = [(top, "GOLD_Top1"), (bot, "GOLD_Bottom1")]
        random.shuffle(ab)
        blind.append({"scene": si + 1, "brief": str(sc.get("brief", ""))[:80],
                      "A": cands[ab[0][0]], "B": cands[ab[1][0]]})
        truth.append({"scene": si + 1, "A_is": ab[0][1], "B_is": ab[1][1],
                      "gold_scores_desc": sorted(scores, reverse=True),
                      "score_range": [min(scores), max(scores), round(max(scores) - min(scores), 1)],
                      "pick_winner": pickw, "pick_eq_goldtop": pickw == top})
    out = Path("output/_disc")
    out.mkdir(exist_ok=True)
    with open(out / "blind.md", "w", encoding="utf-8") as f:
        f.write("# 判别器盲评 — 每场景读A/B,判哪个更好看(网文读者尺:钩子/爽点/对话/画面/语感)\n\n")
        for b in blind:
            f.write(f"## 场景{b['scene']}（brief: {b['brief']}）\n\n### 【A】\n{b['A']}\n\n### 【B】\n{b['B']}\n\n---\n\n")
    json.dump(truth, open(out / "truth.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✓ {len(blind)}场景 N={N} | ¥{cli.cost_cny:.2f}")
    for t in truth:
        print(f"  场景{t['scene']}: GOLD分{t['gold_scores_desc']} 区分度{t['score_range'][2]} | "
              f"PICK选中=GOLD_Top1? {t['pick_eq_goldtop']}")
    print("→ 读 output/_disc/blind.md 盲评A/B,再对 truth.json 算判别器命中率")


if __name__ == "__main__":
    asyncio.run(main())
