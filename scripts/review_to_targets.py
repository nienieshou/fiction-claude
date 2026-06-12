"""飞轮④: 评审结构化findings → repair_targets.json + defect_bank 追加。
评审协议约定最终输出含 JSON 块: {"findings":[{"ch":31,"cat":"邻章互斥","issue":"...","quote":"..."}]}
用法: python scripts/review_to_targets.py <out_dir> <findings.json> [--book 名 --version 标签]
quote 逐条 grep 验证(预评轮纪律),验证不过的不入库不入targets。
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")
from hiki.prose_facts import split_chapters, _norm

out_dir = Path(sys.argv[1])
findings = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
book = sys.argv[sys.argv.index("--book") + 1] if "--book" in sys.argv else out_dir.name[:12]
ver = sys.argv[sys.argv.index("--version") + 1] if "--version" in sys.argv else "current"

chs = split_chapters((out_dir / "final.md").read_text(encoding="utf-8"))
targets, banked, rejected = [], [], []
for f in findings.get("findings", []):
    ch, q = f.get("ch"), str(f.get("quote", ""))
    ok = (isinstance(ch, int) and 1 <= ch <= len(chs)
          and (not q or len(_norm(q)) < 6 or _norm(q)[:24] in _norm(chs[ch - 1])
               or any(_norm(q)[:24] in _norm(chs[i]) for i in range(max(0, ch - 2), min(len(chs), ch + 1)))))
    if ok:
        targets.append({"ch": ch, "issue": f"{f.get('cat', '')}: {f.get('issue', '')}"[:160]})
        banked.append({"book": book, "path": str(out_dir).replace("\\", "/"), "ch": ch,
                       "cat": f.get("cat", ""), "issue": f.get("issue", "")[:80],
                       "quote": q[:40], "detector": f.get("detector", "none"),
                       "verified_by": "fable_review+grep", "version": ver, "baseline_hit": None})
    else:
        rejected.append(f)
(out_dir / "repair_targets.json").write_text(json.dumps(targets, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
bank = Path("assets/defect_bank.jsonl")
n0 = sum(1 for _ in bank.open(encoding="utf-8"))
with bank.open("a", encoding="utf-8") as fp:
    for i, e in enumerate(banked):
        e["id"] = f"D{n0 + i + 1:03d}"
        e["date"] = "auto"
        fp.write(json.dumps(e, ensure_ascii=False) + "\n")
print(f"targets {len(targets)} 条 → {out_dir / 'repair_targets.json'} | 入库 {len(banked)} | "
      f"grep拒绝 {len(rejected)} 条: {[r.get('quote', '')[:15] for r in rejected[:3]]}")
