"""E3 Slice1 真数据不变量 smoke: 对真 assets/hfl.jsonl + gold_regression。
characterization 性质: 钉当前快照(hfl=76行); hfl 增长时更新计数。
76 = 旧60 + Stage-0 6 + A档 6 + B档 4(valB opus×2+gpt55×2); 均 proxy 空间, 不影响 editor/gold 不变量。"""
from pathlib import Path

from hiki import calibration

ROOT = Path(__file__).resolve().parents[1]
HFL = ROOT / "assets" / "hfl.jsonl"
GOLD = ROOT / "assets" / "gold_regression"


def test_realdata_structure_and_snapshot():
    rows, errors = calibration.load_hfl(HFL)
    # 结构不变量(对数据增长稳健)
    assert errors == [], f"hfl 有解析错误行: {errors}"
    assert all(r.truth_space == "editor" for r in rows if r.scorer == "网文编辑")
    # 当前快照(hfl=76 行; 增长时更新以下精确值)
    assert len(rows) == 76
    compat = calibration.compat_report(rows, errors)
    assert compat["n_ground_truth"] == 14
    assert compat["by_truth_space"]["editor"] == 14

    fa = calibration.false_accept_lens(rows)
    assert fa["n_editor_with_deliverable"] == 14
    assert {f["slug"] for f in fa["flagged"]} == {
        "BPBXS00052", "CPBXN00188", "CPBXN00233", "ZYGGY02079", "ZYGGY03052"}

    gold = calibration.load_gold_signal_vectors(GOLD)
    prov = calibration.provenance_divergence(rows, gold)
    assert prov["n_overlap"] == 5
    assert prov["n_divergent"] == 5
    assert prov["n_inconclusive"] == 0
    assert prov["n_provenance_matched"] == 0   # 核心发现: 0 可拟合对齐

    # format_report 不崩且给结论
    out = calibration.format_report(compat, fa, prov)
    assert "0 条可拟合对齐" in out
