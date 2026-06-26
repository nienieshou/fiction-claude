"""early_repeat 检测器：LLM-judge 控制流（FakeClient mock，零真实 API）。"""
import asyncio
import json
from hiki import audit


class FakeClient:
    """最小桩：complete 返回预置字符串，记录调用。"""
    def __init__(self, reply: str):
        self._reply = reply
        self.calls = 0

    async def complete(self, bucket, sys, usr, *, json_mode=False, max_tokens=0, temperature=0.0):
        self.calls += 1
        return self._reply


def _run(coro):
    return asyncio.run(coro)


def test_detects_repeat_pair():
    cli = FakeClient(json.dumps({"repeat": True, "count": 1,
                                 "pairs": ["第1章vs第2章:许安初遇被重述"]}, ensure_ascii=False))
    r = _run(audit.early_repeat_audit(cli, ["第一章 ...许安来访...", "第二章 ...许安又初次来访..."]))
    assert r["count"] == 1
    assert r["pairs"] == ["第1章vs第2章:许安初遇被重述"]
    assert cli.calls == 1


def test_clean_opening_no_repeat():
    cli = FakeClient(json.dumps({"repeat": False, "count": 0, "pairs": []}))
    r = _run(audit.early_repeat_audit(cli, ["第一章 开局", "第二章 推进", "第三章 冲突"]))
    assert r["count"] == 0 and r["pairs"] == []


def test_count_falls_back_to_pairs_len():
    # 模型给了 pairs 但漏填 count → 用 len(pairs) 兜底
    cli = FakeClient(json.dumps({"repeat": True, "pairs": ["a", "b"]}))
    r = _run(audit.early_repeat_audit(cli, ["c1", "c2"]))
    assert r["count"] == 2


def test_under_two_chapters_skips_llm():
    cli = FakeClient("should-not-be-called")
    r = _run(audit.early_repeat_audit(cli, ["only one chapter"]))
    assert r == {"count": 0, "pairs": []} and cli.calls == 0


def test_garbage_json_is_safe():
    cli = FakeClient("not json at all <<<")
    r = _run(audit.early_repeat_audit(cli, ["c1", "c2"]))
    assert r == {"count": 0, "pairs": []}


def test_complete_raises_is_safe():
    class Boom:
        calls = 0
        async def complete(self, *a, **k):
            raise RuntimeError("api down")
    r = _run(audit.early_repeat_audit(Boom(), ["c1", "c2"]))
    assert r == {"count": 0, "pairs": []}
