# tests/test_predraft_gate.py
from hiki.predraft import predraft_gate_check, PREDRAFT_MAX_PLAN_REGEN


def _plan(chapter_idxs):
    # chapter_idxs: 每章的 source_scene_index 列表
    return {"chapters": [{"scenes": [{"source_scene_index": i} for i in idxs]} for idxs in chapter_idxs]}


SCENES = [{"t": i} for i in range(20)]   # len=20


def test_gate_block_on_shared_source():
    g = predraft_gate_check(_plan([[5, 6], [6, 7]]), SCENES)   # ch0∩ch1={6}
    assert g["blocked"] is True
    assert any(f["severity"] == "hard" and f["category"] == "章节复制/注水" for f in g["findings"])
    assert "6" in str(g["evidence"]["dup_pairs"])


def test_gate_no_block_no_share():
    g = predraft_gate_check(_plan([[1, 2], [3, 4]]), SCENES)
    assert g["blocked"] is False


def test_gate_unsourced_warn_not_block():
    # 某章全 -1/越界 → unsourced 100% > 阈 → warn, 不 blocked
    g = predraft_gate_check(_plan([[-1, 99], [3, 4]]), SCENES)
    assert g["blocked"] is False
    assert any(f["severity"] == "warn" for f in g["findings"])
    assert 0 in [c for c in g["evidence"]["unsourced_chapters"]]


def test_gate_missing_fields_safe():
    assert predraft_gate_check({}, SCENES)["blocked"] is False
    assert predraft_gate_check({"chapters": [{"scenes": [{}]}]}, SCENES)["blocked"] is False   # 无 source_scene_index
    assert PREDRAFT_MAX_PLAN_REGEN == 2

import asyncio
from hiki.predraft import predraft_gate_loop


def _mk_planner(block_seq):
    """plan_fn 桩: 依次返回 block_seq[i] 对应的 plan(True=blocked plan). 记录调用次数/force."""
    calls = []
    async def plan_fn(cli, bible, scenes, out_dir, n_ch, force):
        i = len(calls); calls.append({"force": force})
        blocked = block_seq[min(i + 1, len(block_seq) - 1)]   # +1: attempt0 已在外, 这里是 regen
        idxs = [[3], [3]] if blocked else [[1], [2]]          # 共享3=blocked / 不共享=ok
        return {"plan": {"chapters": [{"scenes": [{"source_scene_index": j} for j in c]} for c in idxs]},
                "beats": [], "ordered": [], "n_scenes": 2, "macro": {}, "stats": {}}
    plan_fn.calls = calls
    return plan_fn


def _pl(blocked):
    idxs = [[3], [3]] if blocked else [[1], [2]]
    return {"plan": {"chapters": [{"scenes": [{"source_scene_index": j} for j in c]} for c in idxs]},
            "beats": [], "ordered": [], "n_scenes": 2, "macro": {}, "stats": {}}


SC = [{"t": i} for i in range(10)]


def test_loop_no_block_no_regen():
    pf = _mk_planner([False])
    bible, pl, regens, blocked = asyncio.run(predraft_gate_loop(
        None, {"b": 0}, {"b": 0}, SC, None, 60, _pl(False), pf))
    assert regens == 0 and blocked is False and len(pf.calls) == 0   # 未 regen


def test_loop_block_then_pass():
    # attempt0 blocked → regen1 pass
    pf = _mk_planner([True, False])
    bible, pl, regens, blocked = asyncio.run(predraft_gate_loop(
        None, {"b": 0}, {"b": 0}, SC, None, 60, _pl(True), pf))
    assert regens == 1 and blocked is False and pf.calls[0]["force"] is True


def test_loop_persistent_block_shelve():
    # 始终 blocked → 达 max_regen 仍 blocked
    pf = _mk_planner([True, True, True, True])
    bible, pl, regens, blocked = asyncio.run(predraft_gate_loop(
        None, {"b": 0}, {"b": 0}, SC, None, 60, _pl(True), pf, max_regen=2))
    assert regens == 2 and blocked is True
