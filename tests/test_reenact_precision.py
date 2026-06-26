"""重演精度: PLANE_CHECK 高召回 + 裁决器滣除视角转述。FakeClient(零真实 API)。"""
import asyncio
import json
from hiki import produce


class FakeClient:
    """按 bucket 分队列返回预置响应。detect 与 裁决 都走 'chunk_extract',
    按调用顺序出队(detect 先于裁决, ci 升序)。complete 无内部 await →
    gather 下按列表顺序跑完, 出队确定。"""
    def __init__(self, by_bucket: dict):
        self.q = {k: list(v) for k, v in by_bucket.items()}
        self.calls = []

    async def complete(self, bucket, sys, usr, *, json_mode=False, max_tokens=0, temperature=0.0):
        self.calls.append(bucket)
        return self.q[bucket].pop(0)


def _run(coro):
    return asyncio.run(coro)


# 2章: ci=0 exclusion 空(不调用 detect), ci=1 exclusion=ch0 的 key_events → 1 次 detect
PLAN2 = {"chapters": [{"key_events": ["甲事件"]}, {"key_events": []}]}
CH2 = ["第一章正文", "第二章正文" * 50]


def test_adjudicate_true_keeps_as_reenact():
    cli = FakeClient({"chunk_extract": [
        json.dumps({"reenacted": ["第1章:甲事件"]}),       # detect → 1 hit
        json.dumps({"reenact": True, "why": "镜头重搭"}),  # 裁决 → 真重演
    ]})
    kept, filtered = _run(produce._plane_check(cli, CH2, PLAN2))
    assert kept == ["第2章重演[第1章:甲事件]"]
    assert filtered == []


def test_adjudicate_false_drops_as_relay():
    cli = FakeClient({"chunk_extract": [
        json.dumps({"reenacted": ["第1章:甲事件"]}),
        json.dumps({"reenact": False, "why": "对话转述"}),  # 裁决 → 视角转述
    ]})
    kept, filtered = _run(produce._plane_check(cli, CH2, PLAN2))
    assert kept == []
    assert filtered == ["第2章重演[第1章:甲事件]"]


def test_adjudicate_empty_conservative_keeps():
    # 裁决空响应 → {} → r.get("reenact") is not False == True → 存疑保留(判真重演)
    cli = FakeClient({"chunk_extract": [
        json.dumps({"reenacted": ["第1章:甲事件"]}),
        "",                                                  # 裁决空
    ]})
    kept, filtered = _run(produce._plane_check(cli, CH2, PLAN2))
    assert kept == ["第2章重演[第1章:甲事件]"]
    assert filtered == []


def test_no_raw_hits_skips_adjudication():
    cli = FakeClient({"chunk_extract": [json.dumps({"reenacted": []})]})  # detect 无 hit
    kept, filtered = _run(produce._plane_check(cli, CH2, PLAN2))
    assert kept == [] and filtered == []
    assert cli.calls == ["chunk_extract"]                    # 只 detect, 无裁决调用


def test_multi_hit_classified_no_crosstalk():
    # 3章: ci=1, ci=2 各产 1 hit; 裁决 A=keep, B=drop, 归类不串位
    plan = {"chapters": [{"key_events": ["甲"]}, {"key_events": ["乙"]}, {"key_events": []}]}
    ch = ["第一章", "第二章" * 50, "第三章" * 50]
    cli = FakeClient({"chunk_extract": [
        json.dumps({"reenacted": ["第1章:甲"]}),   # detect ci=1 → hit A
        json.dumps({"reenacted": ["第2章:乙"]}),   # detect ci=2 → hit B
        json.dumps({"reenact": True}),              # 裁决 A → keep
        json.dumps({"reenact": False}),             # 裁决 B → drop
    ]})
    kept, filtered = _run(produce._plane_check(cli, ch, plan))
    assert kept == ["第2章重演[第1章:甲]"]
    assert filtered == ["第3章重演[第2章:乙]"]
