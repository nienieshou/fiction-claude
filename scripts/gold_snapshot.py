# scripts/gold_snapshot.py
"""金标快照工具(E2 Tier-A): output/<dir>/report.json → assets/gold_regression/<slug>/fixture.json。
自校验=经桥接还原的门决策须与 report.deliverable 一致,否则拒写(信号向量不足以复现决策)。
用法: python scripts/gold_snapshot.py [--repin <slug>]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hiki import gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "assets" / "gold_regression"

# slug → (output 目录名, 角色)。角色: reject_guard|clean_guard|snapshot
ROSTER = {
    "BPBXS00052": ("BPBXS00052极品全能小村医_20260625_full", "reject_guard"),
    "CPBGX00031": ("CPBGX00031我真不是大罗金仙带房穿越修仙世界73W_20260625_full", "snapshot"),
    "CPBGX00056": ("CPBGX00056反派：记忆曝光女主为我痛哭反派记忆曝光全世界都为我流泪73w_20260625_full", "reject_guard"),
    "CPBGX00192": ("CPBGX00192灵气复苏：开局无限合成_20260625_full", "snapshot"),
    "CPBXN00188": ("CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full", "clean_guard"),
    "ZYGGY02079": ("ZYGGY02079农女为后：皇上独宠我", "clean_guard"),
    "ZYGGY02252": ("ZYGGY02252归隐田园：执子手共白头", "clean_guard"),
}


def snapshot_one(report: dict, slug: str, role: str) -> dict:
    sv = report["signals"]
    gi = gate.signal_vector_to_gate_input(sv)
    issues = gate.evaluate_ship_gate(gi)
    replay_deliverable = not issues
    if replay_deliverable != bool(report.get("deliverable")):
        raise ValueError(
            f"{slug} 决策不一致: 还原 deliverable={replay_deliverable} != "
            f"report={report.get('deliverable')}(信号向量不足以复现门决策,需 extra 或重跑)")
    return {
        "slug": slug,
        "role": role,
        "signal_schema_version": sv.get("schema_version"),
        "signals": sv,
        "expected_deliverable": replay_deliverable,
        "expected_ship_issues": issues,
    }


def _read_report(out_dir_name: str) -> dict:
    p = ROOT / "output" / out_dir_name / "report.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _write_fixture(fx: dict) -> Path:
    d = GOLD / fx["slug"]
    d.mkdir(parents=True, exist_ok=True)
    p = d / "fixture.json"
    p.write_text(json.dumps(fx, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main(argv: list[str]) -> None:
    only = None
    if argv and argv[0] == "--repin":
        if len(argv) < 2 or not argv[1].strip():
            sys.exit("--repin 需要一个 slug 参数,例如: python scripts/gold_snapshot.py --repin CPBXN00188")
        only = argv[1]
    for slug, (out_dir, role) in ROSTER.items():
        if only and slug != only:
            continue
        fx = snapshot_one(_read_report(out_dir), slug, role)
        p = _write_fixture(fx)
        print(f"{'拒' if not fx['expected_deliverable'] else '放'}  {slug}  → {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
