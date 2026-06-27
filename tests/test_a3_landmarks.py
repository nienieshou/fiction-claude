"""A3 标杆契约 fail-closed 行为(A3.1)。零真实 API(mock cli)。"""
import asyncio
import json
from hiki.prose_continuity import verify_revivals


class _FakeCli:
    """mock Client(本地复定义, 避免跨测试 import 脆弱)。"""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def complete(self, stage, sys_p, usr, **kw):
        self.calls.append(kw)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def test_verify_revivals_malformed_keeps_candidate_failclosed():
    # LLM 全畸形 → 候选保留为存疑(fail-closed), 不静默丢
    cli = _FakeCli(["garbage", "still bad"])                # retries=2
    revivals = [{"who": "纪老夫人", "clue": "火化", "revive_ch": 0}]
    out = asyncio.run(verify_revivals(cli, ["纪老夫人又出现了"], revivals))
    assert out == revivals


def test_verify_revivals_valid_false_drops():
    cli = _FakeCli([json.dumps({"is_revival": False})])
    revivals = [{"who": "张三", "clue": "", "revive_ch": 0}]
    out = asyncio.run(verify_revivals(cli, ["张三在场"], revivals))
    assert out == []


def test_verify_revivals_valid_true_keeps():
    cli = _FakeCli([json.dumps({"is_revival": True})])
    revivals = [{"who": "李四", "clue": "坠崖", "revive_ch": 0}]
    out = asyncio.run(verify_revivals(cli, ["李四复活"], revivals))
    assert out == revivals
