import asyncio
import httpx
import pytest
from openai import APIStatusError


async def _noop_sleep(*a, **k):
    return None


def _status_error(code: int) -> APIStatusError:
    req = httpx.Request("POST", "https://api.deepseek.com")
    return APIStatusError(f"err {code}", response=httpx.Response(code, request=req), body=None)


def _client_raising(monkeypatch, exc, counter):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)        # 免真退避等待
    from hiki.client import Client
    c = Client()

    async def fake_create(**kw):
        counter.append(1)
        raise exc

    monkeypatch.setattr(c._c.chat.completions, "create", fake_create)
    return c


def test_fatal_402_no_retry(monkeypatch):
    calls = []
    c = _client_raising(monkeypatch, _status_error(402), calls)
    with pytest.raises(RuntimeError, match="致命"):
        asyncio.run(c.complete("draft", "sys", "user"))
    assert len(calls) == 1                                    # 0 重试,只调 1 次


def test_fatal_401_no_retry(monkeypatch):
    calls = []
    c = _client_raising(monkeypatch, _status_error(401), calls)
    with pytest.raises(RuntimeError, match="致命"):
        asyncio.run(c.complete("draft", "sys", "user"))
    assert len(calls) == 1


def test_fatal_403_no_retry(monkeypatch):
    calls = []
    c = _client_raising(monkeypatch, _status_error(403), calls)
    with pytest.raises(RuntimeError, match="致命"):
        asyncio.run(c.complete("draft", "sys", "user"))
    assert len(calls) == 1


def test_nonfatal_500_retries_then_raises(monkeypatch):
    calls = []
    c = _client_raising(monkeypatch, _status_error(500), calls)
    with pytest.raises(APIStatusError):                       # 非致命:重试耗尽后抛原异常
        asyncio.run(c.complete("draft", "sys", "user"))
    assert len(calls) == 6                                    # range(6),6 次尝试
