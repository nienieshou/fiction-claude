"""E3 Slice1 校准审计 harness 单测(合成 fixture, 不依赖真 assets)。"""
import json
from pathlib import Path

from hiki import calibration


def _write_jsonl(tmp_path, rows_and_blanks):
    p = tmp_path / "hfl.jsonl"
    p.write_text("\n".join(rows_and_blanks) + "\n", encoding="utf-8")
    return p


def test_load_hfl_parses_and_derives(tmp_path):
    lines = [
        json.dumps({"scorer": "网文编辑", "title": "甲", "slug": "S1", "version": "v1",
                    "dims": {"拉力": 60, "笔力": 70, "人": 60, "承重": 30},
                    "total": 56.5, "auto_signals": {"deliverable": True, "章缝检出": 29}}, ensure_ascii=False),
        json.dumps({"scorer": "运营评委1", "slug": "S2",
                    "dims": {"故事性": 85, "笔力": 90, "人": 80, "承重": 40},
                    "auto_signals": {"grade": "A"}}, ensure_ascii=False),
        json.dumps({"scorer": "fable", "source": "src", "version": "r7",
                    "dims": {"拉力": 70}, "auto_signals": {"schema_version": 1, "deliverable": False}}, ensure_ascii=False),
        json.dumps({"scorer": "总编辑", "title": "丁",
                    "dims": {"拉力": 70, "笔力": 80, "人": 65, "承重": 50},
                    "auto_signals": {"note": "report被覆盖"}}, ensure_ascii=False),
    ]
    rows, errors = calibration.load_hfl(_write_jsonl(tmp_path, lines))
    assert errors == []
    assert len(rows) == 4
    r0 = rows[0]
    assert r0.line_no == 1 and r0.truth_space == "editor" and r0.dims_schema == "standard4"
    assert r0.signal_compat == "legacy" and r0.deliverable is True and r0.title == "甲" and r0.total == 56.5
    assert rows[1].truth_space == "ops" and rows[1].dims_schema == "story4" and rows[1].signal_compat == "none"
    assert rows[2].truth_space == "proxy" and rows[2].signal_compat == "frozen" and rows[2].deliverable is False
    assert rows[3].truth_space == "chief_editor" and rows[3].signal_compat == "none" and rows[3].deliverable is None


def test_load_hfl_failclosed_and_blanks(tmp_path):
    lines = [
        "",  # 空行 → 跳过
        '{"scorer": "网文编辑", "dims": {}, "auto_signals": {}}',  # 合法但空 → none
        "{not valid json",  # 畸形 → errors
        "[1,2,3]",  # 合法 JSON 但非 dict → errors
    ]
    rows, errors = calibration.load_hfl(_write_jsonl(tmp_path, lines))
    assert len(rows) == 1 and rows[0].signal_compat == "none"
    assert {e["line_no"] for e in errors} == {3, 4}
    assert all("error" in e and "raw" in e for e in errors)


def test_compat_report_counts(tmp_path):
    import json
    lines = [
        json.dumps({"scorer": "网文编辑", "slug": "A", "version": "v1",
                    "dims": {"拉力": 1, "笔力": 1, "人": 1, "承重": 1},
                    "auto_signals": {"deliverable": True}}, ensure_ascii=False),
        json.dumps({"scorer": "网文编辑", "slug": "B", "version": "v1",
                    "dims": {"拉力": 1, "笔力": 1, "人": 1, "承重": 1},
                    "auto_signals": {"deliverable": True}}, ensure_ascii=False),
        json.dumps({"scorer": "fable", "version": "r7", "dims": {},
                    "auto_signals": {"schema_version": 1}}, ensure_ascii=False),
    ]
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows, errors = calibration.load_hfl(p)
    rep = calibration.compat_report(rows, errors)
    assert rep["n_rows"] == 3 and rep["n_errors"] == 0 and rep["n_ground_truth"] == 2
    assert rep["by_truth_space"] == {"editor": 2, "proxy": 1}
    assert rep["buckets"]["editor|standard4|legacy|v1"] == 2
    assert rep["buckets"]["proxy|other|frozen|r7"] == 1


def _editor_row(slug, cz, deliv, total=60.0):
    import json
    return json.dumps({"scorer": "网文编辑", "slug": slug, "title": f"T-{slug}", "version": "v1",
                       "dims": {"拉力": 60, "笔力": 60, "人": 60, "承重": cz},
                       "total": total, "auto_signals": {"deliverable": deliv}}, ensure_ascii=False)


def test_false_accept_lens(tmp_path):
    import json
    lines = [
        _editor_row("LOW", 30, True),        # 命中: deliverable=True ∧ 承重<50
        _editor_row("EDGE", 50, True),       # 不命中: 50 不 <50
        _editor_row("HIGH", 70, True),       # 不命中: 承重≥floor
        _editor_row("REJECT", 20, False),    # 不命中: deliverable=False
        json.dumps({"scorer": "fable", "slug": "PX", "dims": {"承重": 10},
                    "auto_signals": {"deliverable": True}}, ensure_ascii=False),  # 非 editor 不计入
    ]
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows, _ = calibration.load_hfl(p)
    fa = calibration.false_accept_lens(rows)
    assert fa["floor"] == 50
    assert fa["n_editor_with_deliverable"] == 4          # 4 个 editor 带 deliverable(PX 是 fable)
    assert [f["slug"] for f in fa["flagged"]] == ["LOW"]
    assert fa["flagged"][0]["title"] == "T-LOW" and fa["flagged"][0]["承重"] == 30
    assert abs(fa["rate"] - 0.25) < 1e-9

    fa70 = calibration.false_accept_lens(rows, floor=70)
    assert {f["slug"] for f in fa70["flagged"]} == {"LOW", "EDGE"}  # 70 下 30/50 均命中


def test_load_gold_signal_vectors(tmp_path):
    import json
    (tmp_path / "S1").mkdir()
    (tmp_path / "S1" / "fixture.json").write_text(
        json.dumps({"slug": "S1", "signals": {"deliverable": True, "seam_detected": 25}}), encoding="utf-8")
    (tmp_path / "S2").mkdir()
    (tmp_path / "S2" / "fixture.json").write_text(
        json.dumps({"slug": "S2", "signals": {"deliverable": False}}), encoding="utf-8")
    gv = calibration.load_gold_signal_vectors(tmp_path)
    assert set(gv) == {"S1", "S2"} and gv["S1"]["seam_detected"] == 25


def test_provenance_divergence_classifies(tmp_path):
    import json
    # gold 冻结向量(直接构造,不落盘)
    gold = {
        "DIV": {"deliverable": False, "seam_detected": 25, "dark_ratio": 0.07},
        "INC": {"deliverable": True, "seam_detected": 29},
        "NOGOLD_IGNORED": {"deliverable": True},
    }
    lines = [
        # DIV: 共享 deliverable(True vs False)+ seam(29 vs 25) → divergent
        json.dumps({"scorer": "网文编辑", "slug": "DIV", "dims": {"承重": 30},
                    "auto_signals": {"deliverable": True, "章缝检出": 29, "暗黑比": 0.07}}, ensure_ascii=False),
        # INC: 共享 deliverable(True==True)+ seam(29==29),全等且无溯源 → inconclusive
        json.dumps({"scorer": "网文编辑", "slug": "INC", "dims": {"承重": 70},
                    "auto_signals": {"deliverable": True, "章缝检出": 29}}, ensure_ascii=False),
        # slug 不在 gold → 不入 overlap
        json.dumps({"scorer": "网文编辑", "slug": "MISSING", "dims": {"承重": 60},
                    "auto_signals": {"deliverable": True}}, ensure_ascii=False),
        # 非 editor → 不入 overlap
        json.dumps({"scorer": "fable", "slug": "DIV", "dims": {"承重": 50},
                    "auto_signals": {"deliverable": False}}, ensure_ascii=False),
    ]
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows, _ = calibration.load_hfl(p)
    prov = calibration.provenance_divergence(rows, gold)
    assert prov["n_overlap"] == 2 and prov["n_divergent"] == 1 and prov["n_inconclusive"] == 1
    assert prov["n_provenance_matched"] == 0
    by = {b["slug"]: b for b in prov["books"]}
    assert by["DIV"]["status"] == "divergent"
    assert "deliverable" in by["DIV"]["diffs"] and "seam_detected" in by["DIV"]["diffs"]
    assert by["INC"]["status"] == "inconclusive" and by["INC"]["diffs"] == {}


def test_comparable_bool_int_exclusion():
    assert calibration._comparable(True, 1) is False     # bool 不与 int 比(bool⊂int 陷阱)
    assert calibration._comparable(1, True) is False      # 对称
    assert calibration._comparable(True, False) is True   # bool 与 bool 可比
    assert calibration._comparable(1, 2) is True          # int 与 int 可比
    assert calibration._comparable(1.5, 2) is True        # float 与 int 可比
    assert calibration._comparable("a", "b") is False     # 非数值/非bool 不可比


def test_load_gold_signal_vectors_skips_non_dict_signals(tmp_path):
    import json
    (tmp_path / "OK").mkdir()
    (tmp_path / "OK" / "fixture.json").write_text(
        json.dumps({"signals": {"deliverable": True}}), encoding="utf-8")
    (tmp_path / "BAD").mkdir()
    (tmp_path / "BAD" / "fixture.json").write_text(
        json.dumps({"signals": None}), encoding="utf-8")
    gv = calibration.load_gold_signal_vectors(tmp_path)
    assert set(gv) == {"OK"}                               # signals 非 dict → 跳过


def test_format_report_is_pure_string():
    compat = {"n_rows": 3, "n_errors": 1, "n_ground_truth": 2,
              "by_truth_space": {"editor": 2, "proxy": 1},
              "buckets": {"editor|standard4|legacy|v1": 2, "proxy|other|frozen|r7": 1}}
    fa = {"flagged": [{"slug": "LOW", "title": "甲", "承重": 30, "total": 56.5, "version": "v1",
                       "auto_signals": {}}],
          "n_editor_with_deliverable": 2, "rate": 0.5, "floor": 50}
    prov = {"books": [{"slug": "DIV", "shared_keys": ["seam_detected"],
                       "diffs": {"seam_detected": [29, 25]}, "status": "divergent"}],
            "n_overlap": 1, "n_divergent": 1, "n_inconclusive": 0, "n_provenance_matched": 0}
    out = calibration.format_report(compat, fa, prov)
    assert isinstance(out, str)
    assert "LOW" in out and "承重=30" in out
    assert "divergent" in out and "DIV" in out
    assert "0 条可拟合对齐" in out          # matched==0 → 结论行
