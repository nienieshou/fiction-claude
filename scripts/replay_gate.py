"""回放新交付门判据于盘上全部 report.json,对照已知人工/Fable 分。
通过标准: 分数≤65 全拦 / ≥68 全放。误拦好书 → 调残缝阈值(初拍8)。
注: final_consistent 判据只对带 章缝_检出 字段的新报告生效(旧报告该位被篇幅bug污染,round6修的)。"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path("output")
KNOWN = {  # 源目录名片段 → (分, 评分人)。65-68灰区不参与通过判定,仅展示。
    "暴君偷听": (37, "总编辑"), "全球陆沉": (62, "总编辑"), "荒年超市": (64.25, "总编辑"),
    "逃荒路上": (68.75, "总编辑"), "大佬她美飒": (73, "总编辑"),
    "团宠小师妹靠摆烂带飞全宗门_full_round6": (75.25, "总编辑"),
    "团宠小师妹靠摆烂带飞全宗门_full": (66.4, "fable"),
    "穿书后我养了偏执男主": (65.2, "fable"),
    "冷战三年": (64.7, "fable"), "灵气复苏": (63.0, "fable"),
}
SEAM_TH = int(sys.argv[1]) if len(sys.argv) > 1 else 8


def cur_gate(rep: dict) -> list[str]:
    """现行门判据,从report字段统一重建(旧报告先于deliverable字段,不能当'放')。"""
    issues = []
    hard = rep.get("audit_承重_确定性硬检") or {}
    fl = hard.get("维2阵营串线") or []
    if isinstance(fl, list) and fl and fl != ["无"]:
        issues.append(f"串线{len(fl)}条")
    mech = rep.get("mechanical") or []
    n_short = sum(1 for m in mech if isinstance(m, str) and "过短" in m)
    if n_short >= 3:
        issues.append(f"过短{n_short}章")
    if (rep.get("暗黑比") or 0) > 0.25:
        issues.append(f"暗黑饱和{rep.get('暗黑比')}")
    return issues


def new_gate(rep: dict) -> list[str]:
    issues = []
    hard = rep.get("audit_承重_确定性硬检") or {}
    rev = hard.get("维14死人复活") or []
    if isinstance(rev, list) and rev and rev != ["无"]:
        issues.append(f"死人复活{len(rev)}处")
    if "章缝_检出" in rep:                      # 新报告才有,亦是 final_consistent 已修的时代标记
        fixed = rep.get("章缝_修复") or []
        n_fixed = 0 if fixed == ["无"] else len(fixed)
        residual = (rep.get("章缝_检出") or 0) - n_fixed
        if residual > SEAM_TH:
            issues.append(f"残缝{residual}处")
        if rep.get("final_consistent") is False:
            issues.append("final_consistent=false")
    return issues


rows = []
for rp in sorted(OUT.glob("*_full*/report.json")):
    rep = json.loads(rp.read_text(encoding="utf-8"))
    if rep.get("rejected"):
        continue
    tag = rp.parent.name
    # 片段匹配取最长命中(防"团宠..._full"误匹配"_full_round6"目录)
    hits = [(k, v) for k, v in KNOWN.items() if k in tag]
    score = max(hits, key=lambda kv: len(kv[0]))[1] if hits else None
    cur = cur_gate(rep)
    new_iss = new_gate(rep)
    rows.append((tag[:34], score, bool(cur), bool(cur) or bool(new_iss),
                 "；".join(cur + new_iss) or "—"))

print(f"残缝阈值={SEAM_TH}")
print(f"{'书':<36}{'分':>10}  现行门  +新判据  命中明细")
ok = True
for tag, score, ob, nb, why in rows:
    s = f"{score[0]}({score[1][:2]})" if score else "无分"
    print(f"{tag:<36}{s:>10}  {'拦' if ob else '放':^5}  {'拦' if nb else '放':^5}  {why}")
    if score:
        if score[0] <= 65 and not nb:
            ok = False
            print("   ^^ 漏放烂书!")
        if score[0] >= 68 and nb:
            ok = False
            print("   ^^ 误拦好书!")
print("\n回放结论:", "通过(≤65全拦/≥68全放,65-68灰区不判)" if ok else "未通过,需调阈值或弃用某判据")
