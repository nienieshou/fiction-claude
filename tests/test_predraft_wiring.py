# tests/test_predraft_wiring.py
import asyncio
import json
from pathlib import Path
from hiki import produce


def test_run_shelves_on_persistent_block(tmp_path, monkeypatch):
    scenes = [{"t": i} for i in range(5)]
    blocked_pl = {"plan": {"chapters": [{"scenes": [{"source_scene_index": 3}]},
                                        {"scenes": [{"source_scene_index": 3}]}]},
                  "beats": [], "ordered": [], "n_scenes": 2, "macro": {}, "stats": {}}

    async def fake_mine(*a, **k):
        return {"rejected": False, "bible": {"protagonist": {}}, "scenes": scenes,
                "grade": {"grade": "B"}, "meta": {}, "clean": "", "all_scene_count": 5, "chunks": []}

    async def fake_plan(cli, bible, scenes_, out_dir, n_ch, force):
        return blocked_pl

    async def fake_draft(*a, **k):
        raise AssertionError("draft 不应在搁置时被调")

    class FakeClient:
        cost_cny = 0.0
    monkeypatch.setattr(produce, "Client", FakeClient)
    monkeypatch.setattr(produce, "_stage_mine", fake_mine)
    monkeypatch.setattr(produce, "_stage_plan", fake_plan)
    monkeypatch.setattr(produce, "_stage_draft", fake_draft)

    rep = asyncio.run(produce.run(Path("x.txt"), out_dir=tmp_path))
    assert rep["rejected"] is True and rep["deliverable"] is False
    assert rep["predraft_shelved"] is True and rep["predraft_regens"] == produce.predraft.PREDRAFT_MAX_PLAN_REGEN
    assert not (tmp_path / "final.md").exists()
    assert (tmp_path / "report.json").exists()


class _StopRun(Exception):
    pass


def _pl_dict(blocked):
    idxs = [[3], [3]] if blocked else [[1], [2]]
    return {"plan": {"chapters": [{"scenes": [{"source_scene_index": j} for j in c]} for c in idxs]},
            "beats": [], "ordered": [], "n_scenes": 2, "macro": {}, "stats": {}}


def _wire_common(monkeypatch, plan_seq, recorded):
    scenes = [{"t": i} for i in range(5)]

    async def fake_mine(*a, **k):
        return {"rejected": False, "bible": {"protagonist": {}}, "scenes": scenes,
                "grade": {"grade": "B"}, "meta": {}, "clean": "", "all_scene_count": 5, "chunks": []}

    calls = {"n": 0}
    async def fake_plan(cli, bible, scenes_, out_dir, n_ch, force):
        blocked = plan_seq[min(calls["n"], len(plan_seq) - 1)]; calls["n"] += 1
        return _pl_dict(blocked)

    async def fake_draft(cli, bible, scenes_, p, plan, ordered, beats, n_scenes, n_cand,
                         rr, tc, prod, od, force):
        recorded["force"] = force; recorded["plan"] = plan
        raise _StopRun()

    class FakeClient:
        cost_cny = 0.0
    monkeypatch.setattr(produce, "Client", FakeClient)
    monkeypatch.setattr(produce, "_stage_mine", fake_mine)
    monkeypatch.setattr(produce, "_stage_plan", fake_plan)
    monkeypatch.setattr(produce, "_stage_draft", fake_draft)


def test_run_happy_path_draft_force_unchanged(tmp_path, monkeypatch):
    import pytest
    rec = {}
    _wire_common(monkeypatch, [False], rec)
    with pytest.raises(_StopRun):
        asyncio.run(produce.run(Path("x.txt"), out_dir=tmp_path, force=False))
    assert rec["force"] is False


def test_run_regen_pass_draft_force_true(tmp_path, monkeypatch):
    import pytest
    rec = {}
    _wire_common(monkeypatch, [True, False], rec)
    with pytest.raises(_StopRun):
        asyncio.run(produce.run(Path("x.txt"), out_dir=tmp_path, force=False))
    assert rec["force"] is True
    chs = rec["plan"]["chapters"]
    assert chs[0]["scenes"][0]["source_scene_index"] != chs[1]["scenes"][0]["source_scene_index"]
