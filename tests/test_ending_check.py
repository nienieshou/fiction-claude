"""gate.ending_check 共享尾门检测(C7.1)。零真实 API(mock cli)。"""
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


def test_ending_check_valid_returns_ec():
    cli = _FakeCli([json.dumps({"ok": True})])
    ec = asyncio.run(gate.ending_check(cli, "prev", "tail"))
    assert ec == {"ok": True}
    assert len(cli.calls) == 1


def test_ending_check_retries_then_valid():
    cli = _FakeCli(["garbage", json.dumps({"ok": False, "problem": "断尾"})])
    ec = asyncio.run(gate.ending_check(cli, "p", "t"))
    assert ec.get("ok") is False and ec.get("problem") == "断尾"
    assert len(cli.calls) == 2


def test_ending_check_all_invalid_returns_empty():
    cli = _FakeCli(["x", "y", "z"])
    assert asyncio.run(gate.ending_check(cli, "p", "t")) == {}
    assert len(cli.calls) == 3


def test_ending_check_skipped_passthrough():
    cli = _FakeCli([json.dumps({"ok": True, "skipped": True, "skipped_what": "决战"})])
    ec = asyncio.run(gate.ending_check(cli, "p", "t"))
    assert ec.get("skipped") is True and ec.get("skipped_what") == "决战"


def test_ending_check_temperature_ramps():
    cli = _FakeCli(["bad", "bad", json.dumps({"ok": True})])
    asyncio.run(gate.ending_check(cli, "p", "t"))
    assert [round(c["temperature"], 2) for c in cli.calls] == [0.1, 0.2, 0.3]
    assert cli.calls[0]["json_mode"] is True and cli.calls[0]["max_tokens"] == 400


def test_ending_check_all_invalid_surfaces(capsys):
    cli = _FakeCli(["x", "y", "z"])
    assert asyncio.run(gate.ending_check(cli, "p", "t")) == {}
    assert "ENDING_CHECK" in capsys.readouterr().err     # 收编后修其同款静默 bug
