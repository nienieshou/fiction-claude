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


# ===== A3 标杆2: _extract_one fail-closed =====
from hiki.mining import _extract_one


def test_extract_one_malformed_surfaces_loss_and_returns_empty(capsys):
    cli = _FakeCli(["garbage", "still bad"])               # retries=2
    r = asyncio.run(_extract_one(cli, "某章正文" * 10, idx=3))
    assert r == {}                                         # 不静默崩, 返空
    assert "chunk 3" in capsys.readouterr().err            # stderr 浮现丢失(不再静默)


def test_extract_one_valid_marks_chunk():
    cli = _FakeCli([json.dumps({"scene_cards": [{"summary": "x"}]})])
    r = asyncio.run(_extract_one(cli, "正文", idx=5))
    assert r["scene_cards"][0]["_chunk"] == 5              # happy: 标 _chunk 不变


def test_extract_one_partial_response_keeps_other_categories():
    # 解析成功但缺 scene_cards、有 char_observations → 不丢数据(返回 r, 非 {})
    cli = _FakeCli([json.dumps({"char_observations": [{"name": "甲"}], "places": ["山"]})])
    r = asyncio.run(_extract_one(cli, "正文", idx=7))
    assert r.get("char_observations") == [{"name": "甲"}]       # 其它类保留
    assert r.get("places") == ["山"]
    assert r != {}                                              # 未被当失败丢弃
