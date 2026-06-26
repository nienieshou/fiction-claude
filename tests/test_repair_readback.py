"""修复回读验证: 章缝/邻章版本 修复后重跑 detect。FakeClient(零真实 API)。"""
import asyncio
import json
from hiki import produce


class FakeClient:
    """按 bucket 分队列返回预置响应。detect 与 recheck 都走 'chunk_extract',
    按调用顺序出队(先 detect 后 recheck);fix 走 'draft'。"""
    def __init__(self, by_bucket: dict):
        self.q = {k: list(v) for k, v in by_bucket.items()}
        self.calls = []

    async def complete(self, bucket, sys, usr, *, json_mode=False, max_tokens=0, temperature=0.0):
        self.calls.append(bucket)
        return self.q[bucket].pop(0)


def _run(coro):
    return asyncio.run(coro)


# ch1 短(<720字, 无 \n\n) → _split_head 的 head = 整章, rest = ""
CH1 = "第二章 牙行买人\n" + "正" * 120


def test_seam_verified_resolved_counts_as_fixed():
    head, _ = produce._split_head(CH1)
    cli = FakeClient({
        "chunk_extract": [
            json.dumps({"ok": False, "issue": "时间倒退"}),  # detect ch idx1 = 断裂
            json.dumps({"ok": True}),                         # recheck → 已净
        ],
        "draft": [head],                                      # 改写=head, 过长度守卫
    })
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert found == 1
    assert len(fixed) == 1 and "第2章" in fixed[0]
    assert unresolved == []
    assert found - len(fixed) == 0          # 残缝=0(诚实)


def test_seam_adopted_but_unresolved_counts_as_residual():
    head, _ = produce._split_head(CH1)
    cli = FakeClient({
        "chunk_extract": [
            json.dumps({"ok": False, "issue": "时间倒退"}),  # detect
            json.dumps({"ok": False, "issue": "仍倒退"}),    # recheck → 仍断裂
        ],
        "draft": [head],
    })
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert found == 1
    assert fixed == []
    assert len(unresolved) == 1 and "第2章" in unresolved[0]
    assert found - len(fixed) == 1          # 残缝=1(过去会错记为0)


def test_seam_fix_rejected_by_guard_no_recheck():
    cli = FakeClient({
        "chunk_extract": [json.dumps({"ok": False, "issue": "x"})],  # 只 detect, 无 recheck
        "draft": ["短"],                                              # 太短, 守卫拒绝采用
    })
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert found == 1
    assert fixed == [] and unresolved == []  # 未采用 → 既非fixed也非unresolved
    assert cli.calls.count("chunk_extract") == 1  # recheck 未被调用(未采用不回读)


def test_seam_no_break_no_fix_no_recheck():
    cli = FakeClient({"chunk_extract": [json.dumps({"ok": True})], "draft": []})
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert found == 0 and fixed == [] and unresolved == []
    assert cli.calls == ["chunk_extract"]    # 只 detect


def test_seam_empty_recheck_treated_as_resolved():
    # 回读 3 次空响应 → _check 返回 {} → 保守判为已净(不误记 residual)
    head, _ = produce._split_head(CH1)
    cli = FakeClient({
        "chunk_extract": [json.dumps({"ok": False, "issue": "x"}), "", "", ""],  # detect + 3空recheck
        "draft": [head],
    })
    out, fixed, found, unresolved = _run(produce._seam_pass(cli, ["第一章正文", CH1]))
    assert len(fixed) == 1 and unresolved == []
