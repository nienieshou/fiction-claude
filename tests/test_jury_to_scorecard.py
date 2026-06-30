# tests/test_jury_to_scorecard.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jury_to_scorecard as j2s


def test_build_scorecard_maps_fields():
    jury = {"book1": {"故事性": 60, "笔力": 55, "人": 50, "承重": 30,
                      "deliver": "no", "reject_reason": "境界乱序", "comments": "套路化"}}
    sc = j2s.build_scorecard(jury, rater="opus", date="2026-06-30")
    assert sc["rater"] == "opus"
    s = sc["scores"]["book1"]
    assert s["故事性"] == 60 and s["承重"] == 30
    assert s["最致命"] == "境界乱序" and s["点评"] == "套路化"


def test_build_scorecard_roundtrips_to_extract_dims():
    # 产出的 scores 须含 story4 四维(hfl_ingest._extract_dims 可识别)
    jury = {"b": {"故事性": 1, "笔力": 2, "人": 3, "承重": 4, "deliver": "yes",
                  "reject_reason": "", "comments": ""}}
    sc = j2s.build_scorecard(jury, rater="gpt55")
    for k in ("故事性", "笔力", "人", "承重"):
        assert k in sc["scores"]["b"]
    assert "date" not in sc      # date=None 省略键(防 hfl_ingest 读成 "None")
