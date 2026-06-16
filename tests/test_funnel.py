"""漏斗纯函数(零 API): _slug/select/build_tasks/_write_report。"""
import json
from pathlib import Path
from hiki import funnel


def test_slug_sanitize_and_dedup():
    seen = set()
    assert funnel._slug("ZTGXY01837退婚后，她被娇养了", seen) == "ZTGXY01837退婚后_她被娇养了"
    a = funnel._slug("同名", seen)
    b = funnel._slug("同名", seen)               # 同 stem → 自动加后缀防撞目录
    assert a == "同名" and b == "同名_2" and a != b


def _rows():
    return [
        (Path("src/S书.txt"), {"ok": True, "grade": "S", "wan_zi": 50}),
        (Path("src/A高.txt"), {"ok": True, "grade": "A", "wan_zi": 80}),
        (Path("src/A低.txt"), {"ok": True, "grade": "A", "wan_zi": 30}),
        (Path("src/B书.txt"), {"ok": True, "grade": "B", "wan_zi": 99}),
        (Path("src/坏.txt"), {"ok": False, "error": "REDUCE失败"}),
    ]


def test_select_filter_sort_cap():
    surv = funnel.select(_rows(), {"S", "A"}, None)        # 只 S/A,B 和失败淘汰
    assert [p.stem for p, _ in surv] == ["S书", "A高", "A低"]   # S 先,A 内按字数降序
    assert funnel.select(_rows(), {"S", "A"}, 2) == surv[:2]   # --max 截顶
    assert funnel.select(_rows(), {"S"}, None)[0][0].stem == "S书" and len(funnel.select(_rows(), {"S"}, None)) == 1


def test_build_tasks_unique_slug_and_outdir():
    surv = funnel.select(_rows(), {"S", "A"}, None)
    tasks = funnel.build_tasks(surv, Path("output/funnel"),
                               {"chapters": 60, "chunks": 12, "candidates": 3, "refine_rounds": 5, "force": False})
    slugs = [t.slug for t in tasks]
    assert len(set(slugs)) == len(slugs)                  # slug 唯一(决定输出子目录)
    assert tasks[0].out_dir == Path("output/funnel") / tasks[0].slug
    assert all(t.min_grade is None for t in tasks)        # filter 已做,run 不再二次拒


def test_write_report_dry_run(tmp_path):
    summary = {"入池": 5, "pregrade成功": 4, "pregrade失败": 1,
               "pregrade分布": {"S": 1, "A": 2, "B": 1}, "keep档": ["S", "A"],
               "存活": 3, "改写": 2, "pregrade成本_cny": 1.9, "dry_run": True,
               "存活源": ["S书.txt", "A高.txt", "A低.txt"],
               "改写成本估算_cny": 13.4, "总成本估算_cny": 15.3, "墙钟_秒": 12.0}
    funnel._write_report(tmp_path, summary)
    rep = json.loads((tmp_path / "funnel_report.json").read_text(encoding="utf-8"))
    assert rep["改写"] == 2
    md = (tmp_path / "funnel_report.md").read_text(encoding="utf-8")
    assert "DRY-RUN" in md and "改写估算 ¥13.4" in md and "可交付" not in md   # dry 不含交付行
