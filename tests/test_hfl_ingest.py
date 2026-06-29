"""E3 Slice1b: hfl_ingest CLI 往返 + 幂等(合成 eval_dir, 不碰真 assets/hfl.jsonl)。"""
import json
import subprocess
import sys
from pathlib import Path

from hiki import calibration

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hfl_ingest.py"


def _setup_eval(tmp_path):
    d = tmp_path / "evalX"
    (d / "S1").mkdir(parents=True)
    (d / "S1" / "report.json").write_text(json.dumps({
        "title": "甲书", "source": "SRC001", "engine_commit": "cafef00d",
        "signals": {"schema_version": 1, "deliverable": True, "seam_detected": 25,
                    "grade": "A", "opening_immersion": 80},
    }, ensure_ascii=False), encoding="utf-8")
    (d / "scorecard_ed.yaml").write_text(
        "rater: 网文编辑\ndate: 2026-06-29\nscores:\n"
        "  S1: {拉力: 60, 笔力: 70, 人: 60, 承重: 30, 追读: 高, 最致命: 衔接, 点评: ok}\n",
        encoding="utf-8")
    return d


def _run(eval_dir, hfl, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(eval_dir), "--hfl", str(hfl), *extra],
                          capture_output=True, text=True, encoding="utf-8")


def test_ingest_write_then_idempotent(tmp_path):
    d = _setup_eval(tmp_path)
    hfl = tmp_path / "hfl.jsonl"
    r1 = _run(d, hfl, "--round", "test-round", "--write")
    assert r1.returncode == 0, r1.stderr
    rows, errs = calibration.load_hfl(hfl)
    assert errs == [] and len(rows) == 1
    assert rows[0].signal_compat == "frozen" and rows[0].truth_space == "editor"
    assert rows[0].total == 56.5 and rows[0].slug == "S1"
    # 再跑同输入 → 幂等跳过, 不增行
    r2 = _run(d, hfl, "--round", "test-round", "--write")
    assert r2.returncode == 0
    rows2, _ = calibration.load_hfl(hfl)
    assert len(rows2) == 1, "幂等失败: 重复 append"


def test_ingest_preview_does_not_write(tmp_path):
    d = _setup_eval(tmp_path)
    hfl = tmp_path / "hfl.jsonl"
    r = _run(d, hfl, "--round", "test-round")   # 无 --write
    assert r.returncode == 0
    assert not hfl.exists() or hfl.read_text(encoding="utf-8").strip() == ""
