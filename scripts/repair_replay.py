"""良品线点修(2026-06-13): 把交付门'事件重演'的章号从 report 的 控制面重演核对 字段
抽成 repair_targets.json,喂 point_repair 做章级定向重写(删重演/承接推进),再复检交付。
用法: PYTHONPATH=src python scripts/repair_replay.py <out_dir> [<out_dir> ...]
"""
import asyncio, json, re, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki import point_repair

_CH = re.compile(r"第(\d+)章重演\[(.*?)\]")
_ISSUE = ("本章与前章存在事件重演：重复演绎了已发生的情节「{ev}」。"
          "请删除该重复演绎，改为承接前章结尾继续推进新情节，"
          "严禁重写或回放已发生的事件、对话、场景。")


def build_targets(out_dir: Path) -> int:
    rep = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    targets = []
    for entry in rep.get("控制面重演核对") or []:
        m = _CH.search(str(entry))
        if m:
            targets.append({"ch": int(m.group(1)), "issue": _ISSUE.format(ev=m.group(2)[:120])})
    (out_dir / "repair_targets.json").write_text(
        json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(targets)


async def main():
    for arg in sys.argv[1:]:
        d = Path(arg)
        n = build_targets(d)
        print(f"\n[{d.name[:24]}] 建 {n} 个重演点修目标 → 跑 point_repair")
        if n == 0:
            print("  无重演目标,跳过"); continue
        await point_repair.run(d)


if __name__ == "__main__":
    asyncio.run(main())
