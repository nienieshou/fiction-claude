"""承重 rubric LLM-judge(B-接线 验证)：对成品全文单 pass(fact_audit=v4-pro/1M)按 ConStory 风格
承重分类法打 0-100 承重分,锚定网文编辑真值(editor-eval-1)。验证能否分开 承重30 vs 70 档。

跑: $env:PYTHONPATH="src"; python scripts/load_bearing_eval.py
只评承重(一致性),不评笔力/拉力/人。一次性验证脚本(过判据再考虑接线进门)。
"""
import asyncio
import glob
import io
import json
import os
import re
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # → 项目根,不依赖 cwd
sys.path.insert(0, "src")
from hiki.client import Client          # noqa: E402
from hiki import gate                   # noqa: E402

# 编辑承重真值 + 原话 by 源ID（assets/hfl.jsonl editor-eval-1）—— 用作 few-shot 严重度校准
EDITOR = {
    "BPBXS00052": ("极品全能小村医", 30, "父亲'出车祸凑手术费'后又'被绑架'，致命事件双版本，逻辑混乱"),
    "CPBGX00192": ("灵气复苏", 65, "承重尚可，无明显逻辑错误（该书扣分在人物介绍，不在承重）"),
    "CPBXN00188": ("冰川探墓", 40, "小细节逻辑bug，前后文不连贯，没说清前因后果"),
    "CPBXN00233": ("末世带娃", 30, "前后剧情矛盾，逻辑不通"),
    "DYBXN00061": ("乡村桃运神医", 70, "承重可，无硬伤，可出货（全场最佳）"),
}
ED = {k: v[1] for k, v in EDITOR.items()}


def fewshot_block(exclude_sid: str) -> str:
    lines = ["【人类编辑承重评分范例——学习其严重度尺度，给目标书对齐，勿过度报致命】"]
    for sid, (name, sc, note) in EDITOR.items():
        if sid == exclude_sid:
            continue
        lines.append(f"- 《{name}》承重{sc}：{note}")
    lines.append("要点：只有读者能察觉的致命矛盾（事件双版本/前后剧情矛盾/前因后果缺失）才把承重压到 30-40；"
                 "技术性小不一致不致命；无明显逻辑错误≈65；无硬伤可出货≈70。对齐此尺度，别把小瑕疵当致命。")
    return "\n".join(lines)

SYS = ("你是严格的网文「承重」审稿编辑。承重=结构/事实/逻辑一致性，"
       "不含笔力/拉力/代入感。只查跨章一致性硬伤，按 rubric 给 0-100 承重分。")

RUBRIC = """【只查这 5 类承重缺陷】
1. 事件双互斥版本：同一事件两种矛盾写法，或同人物状态互斥（例：父亲先"车祸住院"凑钱，后又"被绑架"且无衔接）。
2. 状态矛盾：已死复活 / 修为倒退 / 人物已离开却又在场。
3. 时序倒退·场景跳跃：前章已到B后章又回A；时间倒流；场景无过渡硬跳。
4. 因果断裂：关键转折无前因后果交代。
5. 副线悬空：角色/伏笔引入无铺垫，或铺垫后无回收。

【评分锚（对齐人类编辑尺，务必照此校准）】
- 无一致性硬伤、剧情连贯 ≈ 70（可出货）。
- 尚可、无明显逻辑错误 ≈ 65。
- 因果断裂/场景跳跃较多、细节逻辑bug ≈ 40-55。
- 逻辑混乱、有致命事件双版本/前后剧情矛盾 ≈ 30。

【输出 JSON】{"承重分": int, "致命": [{"类型":"", "章":"", "问题":""}], "中": [...], "轻": [...], "总评": ""}
只输出承重一致性问题，不要评论文笔或爽点。"""


async def score(cli: Client, text: str, exclude_sid: str) -> dict:
    usr = fewshot_block(exclude_sid) + "\n\n" + RUBRIC + "\n\n===== 成品全文（60章） =====\n" + text
    r: dict = {}
    for t in range(3):                       # 修 flaky:v4-pro 思考模式 over 22万字 偶发吐空 → 重试
        raw = await cli.complete("fact_audit", SYS, usr, json_mode=True,
                                 max_tokens=4000, temperature=0.2 + 0.1 * t)
        r = gate._safe_json(raw) or {}
        if isinstance(r.get("承重分"), (int, float)):
            return r
    return r


async def main() -> None:
    cli = Client()
    dirs = {}
    for d in glob.glob("output/*_full"):
        m = re.match(r"[A-Za-z]+\d+", os.path.basename(d))
        if m and m.group(0) in ED and os.path.exists(os.path.join(d, "final.md")):
            dirs[m.group(0)] = d

    async def one(sid):
        d = dirs.get(sid)
        if not d:
            return sid, None
        text = open(os.path.join(d, "final.md"), encoding="utf-8").read()
        return sid, await score(cli, text, exclude_sid=sid)   # 留一法:范例不含目标本,无泄漏

    results = await asyncio.gather(*[one(s) for s in ED])

    lines = ["源ID | 编辑承重 | 机器承重 | 致命/中/轻 | 总评"]
    pairs = []
    for sid, r in results:
        ed = ED[sid]
        if not r:
            lines.append(f"{sid} | {ed} | (无final.md/失败)")
            continue
        s = r.get("承重分")
        nf, nm, nl = len(r.get("致命") or []), len(r.get("中") or []), len(r.get("轻") or [])
        lines.append(f"{sid} | {ed} | {s} | {nf}/{nm}/{nl} | {(r.get('总评') or '')[:70]}")
        if isinstance(s, (int, float)):
            pairs.append((ed, s))
    # 判据:能否分开 30档 与 70档(单调性/排序相关)
    if len(pairs) >= 2:
        import statistics
        lo = [m for e, m in pairs if e <= 40]
        hi = [m for e, m in pairs if e >= 65]
        lines.append("")
        lines.append(f"低档(编辑≤40)机器均={statistics.mean(lo):.0f} vs 高档(编辑≥65)机器均={statistics.mean(hi):.0f}"
                     if lo and hi else "(档位样本不足)")
        order = sorted(pairs, key=lambda p: p[1])
        lines.append("机器分升序对应编辑分: " + " ".join(f"{m:.0f}→ed{e}" for e, m in order))
    lines.append(f"\ncalls={cli.calls} cost=¥{cli.cost_cny:.2f}")
    io.open("prototype/_lb.txt", "w", encoding="utf-8").write("\n".join(lines))
    print("done", len(pairs), "scored")


if __name__ == "__main__":
    asyncio.run(main())
