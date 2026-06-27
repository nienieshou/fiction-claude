"""LLM 输出 schema 校验层(A3.1)。零真实 API(mock cli)。"""
import asyncio
import json
from hiki.schemas import validate, REVIVAL_VERIFY, EXTRACT_CHUNK
from hiki.llm_validate import complete_validated


class _FakeCli:
    """mock Client: complete() 按序返回预置响应; 耗尽则返回最后一个。记录每次 kw。"""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def complete(self, stage, sys_p, usr, **kw):
        self.calls.append(kw)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


# ---- validate 谓词 ----
def test_validate_required_present():
    assert validate({"is_revival": True}, **REVIVAL_VERIFY) is True


def test_validate_missing_key():
    assert validate({"foo": 1}, **REVIVAL_VERIFY) is False


def test_validate_wrong_type():
    assert validate({"is_revival": "yes"}, **REVIVAL_VERIFY) is False   # str 非 bool


def test_validate_non_dict():
    assert validate(None, **REVIVAL_VERIFY) is False
    assert validate([1, 2], **REVIVAL_VERIFY) is False


def test_validate_extract_chunk_any_dict_valid_partial_keeps_data():
    assert validate({"scene_cards": []}, **EXTRACT_CHUNK) is True            # 空列表合法
    assert validate({}, **EXTRACT_CHUNK) is True                            # 空 dict = 解析成功(合法, 与旧一致)
    assert validate({"char_observations": [1]}, **EXTRACT_CHUNK) is True    # partial(无scene_cards但有其它类)= 合法, 不丢数据
    assert validate({"scene_cards": None}, **EXTRACT_CHUNK) is False        # scene_cards 在但非list → 无效(防 for sc in None 崩)
    assert validate(None, **EXTRACT_CHUNK) is False                         # 解析失败
    assert validate("garbage", **EXTRACT_CHUNK) is False                    # 非 dict


# ---- complete_validated ----
def test_complete_validated_valid_first_call_uses_base_temperature():
    cli = _FakeCli([json.dumps({"is_revival": True})])
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr",
                                       schema=REVIVAL_VERIFY, retries=2, temperature=0.1, json_mode=True))
    assert r == {"is_revival": True}
    assert len(cli.calls) == 1
    assert round(cli.calls[0]["temperature"], 2) == 0.1                 # 首调用=原温度
    assert cli.calls[0]["json_mode"] is True                            # 其余 kw 透传


def test_complete_validated_retries_then_valid():
    cli = _FakeCli(["garbage{", json.dumps({"is_revival": False})])
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr", schema=REVIVAL_VERIFY, retries=3))
    assert r == {"is_revival": False}
    assert len(cli.calls) == 2


def test_complete_validated_all_invalid_returns_none():
    cli = _FakeCli(["garbage", "{bad", "nope"])
    r = asyncio.run(complete_validated(cli, "s", "sys", "usr", schema=REVIVAL_VERIFY, retries=3))
    assert r is None
    assert len(cli.calls) == 3


def test_complete_validated_temperature_ramps_on_retry():
    cli = _FakeCli(["bad", "bad", json.dumps({"is_revival": True})])
    asyncio.run(complete_validated(cli, "s", "sys", "usr",
                                   schema=REVIVAL_VERIFY, retries=3, temperature=0.1))
    assert [round(c["temperature"], 2) for c in cli.calls] == [0.1, 0.2, 0.3]
