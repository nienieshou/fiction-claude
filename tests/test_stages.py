"""B1 阶段函数 resume 路径(零 API:resume 分支不调 cli)。"""
import asyncio
import json
from hiki.produce import _stage_plan, _stage_mine


def test_stage_plan_resume_loads_without_cli(tmp_path):
    macro = {"chapters": [{"beat": f"b{i}", "act": "x"} for i in range(60)], "central_conflict": "c"}
    plan = {"chapters": [{"scenes": [{"brief": "s"}], "title": f"第{i}章"} for i in range(60)]}
    (tmp_path / "macro.json").write_text(json.dumps(macro), encoding="utf-8")
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    out = asyncio.run(_stage_plan(cli=None, bible={}, scenes=[], out_dir=tmp_path, n_ch=60))
    assert len(out["plan"]["chapters"]) == 60
    assert out["n_scenes"] == 60 and len(out["ordered"]) == 60
    assert len(out["beats"]) == 60                    # cli=None 未被触碰=resume 不调 LLM


def test_stage_mine_resume_loads_without_cli(tmp_path):
    # 备齐 source + mine 产物 → resume 分支 load,不调 mine_book
    (tmp_path / "source").mkdir()
    src = tmp_path / "src.txt"
    src.write_text("第1章 开始\n这是一段正文内容,足够长来通过清洗。" * 3, encoding="utf-8")
    for n, obj in (("bible", {"protagonist": {"name": "甲"}}), ("scenes", [{"summary": "s"}]),
                   ("grade", {"grade": "A"}), ("mine", {"all_scene_count": 5, "chunks": 12})):
        (tmp_path / f"{n}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    out = asyncio.run(_stage_mine(cli=None, src=src, out_dir=tmp_path, n_ch=60, n_chunks=12,
                                  min_grade=None, prod={}, force=False))
    assert not out.get("rejected")
    assert out["bible"]["protagonist"]["name"] == "甲"
    assert out["all_scene_count"] == 5 and out["chunks"] == 12


def test_stage_mine_force_ignores_resume(tmp_path):
    # force=True 时即便产物在,也不走 resume(会去调 cli=None → 触发,证明绕过了 load)
    (tmp_path / "source").mkdir()
    src = tmp_path / "src.txt"
    src.write_text("第1章 开始\n正文内容正文内容正文内容。" * 5, encoding="utf-8")
    for n in ("bible", "scenes", "grade", "mine"):
        (tmp_path / f"{n}.json").write_text("{}", encoding="utf-8")
    try:
        asyncio.run(_stage_mine(cli=None, src=src, out_dir=tmp_path, n_ch=60, n_chunks=12,
                                min_grade=None, prod={}, force=True))
        raised = False
    except Exception:
        raised = True                                  # cli=None 被调用→证明 force 绕过了 resume load
    assert raised
