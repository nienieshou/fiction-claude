import asyncio


def test_normalize_balance_live():
    from web.backend.balance import normalize_balance
    raw = {"is_available": True, "balance_infos": [
        {"currency": "CNY", "total_balance": "110.00",
         "granted_balance": "10.00", "topped_up_balance": "100.00"}]}
    assert normalize_balance(raw) == {
        "available": True, "currency": "CNY", "total": "110.00", "source": "live"}


def test_normalize_balance_bad_shape():
    from web.backend.balance import normalize_balance
    assert normalize_balance({})["source"] == "error"
    assert normalize_balance({"is_available": True, "balance_infos": []})["source"] == "error"


def test_fetch_balance_no_key(monkeypatch):
    from web.backend import balance
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    res = asyncio.run(balance.fetch_balance())
    assert res["source"] == "no-key" and res["total"] is None


def test_fetch_balance_live(monkeypatch):
    from web.backend import balance
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")

    class FakeResp:
        status_code = 200
        def json(self):
            return {"is_available": True, "balance_infos": [
                {"currency": "CNY", "total_balance": "42.50",
                 "granted_balance": "0", "topped_up_balance": "42.50"}]}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return FakeResp()

    monkeypatch.setattr(balance.httpx, "AsyncClient", FakeClient)
    res = asyncio.run(balance.fetch_balance())
    assert res["source"] == "live" and res["total"] == "42.50" and res["available"] is True


def test_fetch_balance_error_no_throw(monkeypatch):
    from web.backend import balance
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")

    class BoomClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise RuntimeError("boom")

    monkeypatch.setattr(balance.httpx, "AsyncClient", BoomClient)
    res = asyncio.run(balance.fetch_balance())          # 不抛
    assert res["source"] == "error"
