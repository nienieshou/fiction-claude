"""C6②: _stage_finalize 的 craft_advisory 门控(开→调craft, 关→跳过+占位)。零真实 API。"""
import asyncio
from hiki import produce, audit


def _patch(monkeypatch, craft_tracker):
    async def _fake_title(cli, bible, ending=""):
        return {"title": "T", "tagline": "标语", "alts": []}
    async def _fake_craft(cli, text):
        craft_tracker.append(True)
        return ["craft发现X"]
    monkeypatch.setattr(produce, "gen_title", _fake_title)
    monkeypatch.setattr(audit, "craft_audit", _fake_craft)


def _finalize(out, craft_advisory):
    return asyncio.run(produce._stage_finalize(
        object(), out / "src.txt", out, {"protagonist": {}}, "正文内容",
        True, [], {}, open_premise="", immersion={}, craft_advisory=craft_advisory))


def test_craft_off_skips_and_placeholder(tmp_path, monkeypatch):
    tracker = []
    _patch(monkeypatch, tracker)
    out = tmp_path / "bk"; out.mkdir()
    report = _finalize(out, craft_advisory=False)
    assert tracker == []                                          # craft 未被调用(省 token)
    assert "已关" in report["audit_人+故事性_craft(advisory)"][0]   # 报告占位浮现


def test_craft_on_calls_and_records(tmp_path, monkeypatch):
    tracker = []
    _patch(monkeypatch, tracker)
    out = tmp_path / "bk"; out.mkdir()
    report = _finalize(out, craft_advisory=True)
    assert tracker == [True]                                      # craft 被调用
    assert report["audit_人+故事性_craft(advisory)"] == ["craft发现X"]
