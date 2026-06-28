"""gate.detect_retry 共享 LLM 检测环(A3 wave3)。零真实 API(mock cli)。"""
import asyncio
import json
from hiki import gate


class _FakeCli:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def complete(self, stage, sys_p, usr, **kw):
        self.calls.append(kw)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def test_detect_retry_valid_dict_with_key():
    cli = _FakeCli([json.dumps({"ok": True})])
    r = asyncio.run(gate.detect_retry(cli, "sys", "usr", "ok", max_tokens=400, label="X"))
    assert r == {"ok": True}
    assert len(cli.calls) == 1


def test_detect_retry_retries_then_valid():
    cli = _FakeCli(["garbage", json.dumps({"dup": True})])
    r = asyncio.run(gate.detect_retry(cli, "s", "u", "dup", max_tokens=300, label="X"))
    assert r == {"dup": True}
    assert len(cli.calls) == 2


def test_detect_retry_all_invalid_surfaces_and_empty(capsys):
    cli = _FakeCli(["x", "y", "z"])
    r = asyncio.run(gate.detect_retry(cli, "s", "u", "ok", max_tokens=400, label="SEAM 第3章"))
    assert r == {}
    assert len(cli.calls) == 3
    assert "SEAM 第3章" in capsys.readouterr().err      # 浮现(不静默)


def test_detect_retry_passthrough_and_ramp():
    cli = _FakeCli(["bad", "bad", json.dumps({"ok": True})])
    asyncio.run(gate.detect_retry(cli, "s", "u", "ok", max_tokens=300, label="X"))
    assert [round(c["temperature"], 2) for c in cli.calls] == [0.1, 0.2, 0.3]
    assert all(c["max_tokens"] == 300 and c["json_mode"] is True for c in cli.calls)


def test_detect_retry_isinstance_guard_list_retries():
    cli = _FakeCli([json.dumps(["ok"]), json.dumps(["ok"]), json.dumps(["ok"])])  # list 含 "ok" 成员
    r = asyncio.run(gate.detect_retry(cli, "s", "u", "ok", max_tokens=400, label="L"))
    assert r == {}                                       # 非 dict → 不误返
    assert len(cli.calls) == 3
