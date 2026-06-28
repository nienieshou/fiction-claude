"""A3 wave3: 三检 pass 重试耗尽 → stderr 浮现(不静默当干净)。零真实 API(mock cli)。"""
import asyncio
from hiki import produce


class _FakeCli:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def complete(self, stage, sys_p, usr, **kw):
        self.calls.append(kw)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def test_seam_pass_surfaces_on_all_invalid(capsys):
    cli = _FakeCli(["garbage", "garbage", "garbage"])     # 2章→1对,_check 最多3调用全畸形
    ch = ["第一章正文。", "第二章正文。"]
    out, fixed, found, unresolved = asyncio.run(produce._seam_pass(cli, ch))
    assert out == ch and fixed == [] and found == 0 and unresolved == []   # 不误修
    assert "SEAM 第2章" in capsys.readouterr().err          # 浮现该对(可能漏检)


def test_adj_dup_pass_surfaces_on_all_invalid(capsys):
    cli = _FakeCli(["garbage", "garbage", "garbage"])
    ch = ["第一章正文。", "第二章正文。"]
    out, fixed, found, unresolved = asyncio.run(produce._adj_dup_pass(cli, ch))
    assert out == ch and fixed == [] and found == 0 and unresolved == []
    assert "ADJ_DUP 第2章" in capsys.readouterr().err
