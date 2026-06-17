"""A-M0: 验证「事件/状态账」可行性 —— 抽取每个人物的状态时间线(registry 空间),
看编辑/机器实证的真矛盾(父亲 车祸↔绑架 / 生前↔活着)能否被**枚举**出来(可裁),
而非埋在 21 万字 prose 里(不可枚举=A2 18%召回)。

判据(event_subplot_spine.md §5):≥2/3 病例在状态时间线里可枚举 → A 接线 plan 层。
跑: python scripts/event_spine_m0.py    (chunk_extract=v4-flash 走量,纯抽取非评判)
"""
import asyncio
import io
import os
import re
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "src")
from hiki.client import Client          # noqa: E402
from hiki import gate                   # noqa: E402

# 病例:源ID → (关键人物关键词, 已知真矛盾)
CASES = {
    "BPBXS00052": (["父亲", "爹", "爸"], "父亲:车祸凑钱 ↔ 被绑架(事件双版本)"),
    "DYBXN00061": (["父亲", "爹", "王建国"], "父亲:第1章生前(已故) ↔ 第3章活着在场"),
}

SYS = "你是信息抽取器，只忠实抽取文本显式写出的人物状态/重大遭遇，不推断、不评判、不补全。"
DEATH = re.compile(r"死|去世|已故|身亡|生前|遇害|过世|亡")


def split_chapters(text):
    parts = re.split(r"(第[一二三四五六七八九十百零0-9]+章)", text)
    chs = []
    for i in range(1, len(parts), 2):
        chs.append((i // 2 + 1, parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")))
    return chs


async def book_timeline(cli, chs, keys):
    """目标化:全文单 pass 只追踪指定人物(父亲/王建国)的状态时间线 —— 配角矛盾靠定向抽取,非泛抽。"""
    full = "\n".join(f"【第{n}章】{t}" for n, t in chs)
    usr = (f"通读全文，**只追踪人物【{'/'.join(keys)}】**的状态与重大遭遇时间线。"
           "列出每次明确写到其 生死状态/重大遭遇（车祸/绑架/受伤/被囚/死亡/已故/生前/在场行动）的 章号+原文短引。\n"
           '输出JSON: {"timeline":[{"章":数字,"状态":"","引文":"≤20字"}]}\n\n全文:\n' + full[:600000])
    for t in range(3):                       # fact_audit 思考模式 over 大输入 偶发吐空→重试
        raw = await cli.complete("fact_audit", SYS, usr, json_mode=True, max_tokens=3000, temperature=0.2 + 0.1 * t)
        r = gate._safe_json(raw) or {}
        if r.get("timeline"):
            for e in r["timeline"]:
                e["人物"] = keys[0]
            return r["timeline"]
    return []


def scan(timeline, keys):
    # 聚焦关键人物
    rows = [e for e in timeline if isinstance(e, dict) and any(k in str(e.get("人物", "")) for k in keys)]
    rows.sort(key=lambda e: e.get("章") or 0)
    # 死后又活/在场 矛盾
    deaths = [e for e in rows if DEATH.search(str(e.get("状态", "")))]
    flags = []
    if deaths:
        first_death = min(e.get("章") or 0 for e in deaths)
        after = [e for e in rows if (e.get("章") or 0) > first_death and not DEATH.search(str(e.get("状态", "")))]
        if after:
            flags.append(f"死/已故(第{first_death}章) → 之后仍在场/行动(第{after[0].get('章')}章:{after[0].get('状态')})")
    # 互斥重大事件(同人不同遭遇)
    incidents = set(str(e.get("状态", "")) for e in rows if re.search(r"车祸|绑架|被囚|重伤", str(e.get("状态", ""))))
    if len(incidents) >= 2:
        flags.append("互斥重大遭遇: " + " | ".join(list(incidents)[:4]))
    return rows, flags


async def main():
    cli = Client()
    dirs = {}
    for d in __import__("glob").glob("output/*_full"):
        m = re.match(r"[A-Za-z]+\d+", os.path.basename(d))
        if m and m.group(0) in CASES and os.path.exists(os.path.join(d, "final.md")):
            dirs[m.group(0)] = d
    out = []
    caught = 0
    for sid, (keys, known) in CASES.items():
        d = dirs.get(sid)
        out.append(f"\n========== {sid} ==========")
        out.append(f"已知真矛盾: {known}")
        if not d:
            out.append("(无 final.md)")
            continue
        chs = split_chapters(open(os.path.join(d, "final.md"), encoding="utf-8").read())
        tl = await book_timeline(cli, chs, keys)
        rows, flags = scan(tl, keys)
        out.append(f"抽出该人物状态条目 {len(rows)} 条(registry 空间):")
        for e in rows[:14]:
            out.append(f"  第{e.get('章')}章: {e.get('状态')}")
        out.append("枚举到的矛盾: " + (" ; ".join(flags) if flags else "（未枚举到——抽取漏/需调）"))
        if flags:
            caught += 1
    out.append(f"\n=== 判据: {caught}/{len(CASES)} 病例在状态时间线可枚举矛盾 ===")
    out.append(f"calls={cli.calls} cost=¥{cli.cost_cny:.2f}")
    io.open("prototype/_am0.txt", "w", encoding="utf-8").write("\n".join(out))
    print("done", caught, "/", len(CASES))


if __name__ == "__main__":
    asyncio.run(main())
