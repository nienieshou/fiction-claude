"""A3 wave5: score_scenes 静默单发硬化 —— 唯一 0 重试站点换 complete_validated。
零 API; fake cli 按固定串回应。LLM分驱动选择 vs 耗尽可见回退 importance 启发式。"""
import asyncio
import json
from hiki import mining


class _Cli:
    """每次 complete 返回同一固定串; 记调用次数。"""
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def complete(self, *a, **k):
        self.calls += 1
        return self.reply


def _scenes() -> list[dict]:
    # scene0=高(启发式宠儿), scene1/2=低; LLM 给 scene2 最高分(与启发式分歧)
    return [
        {"summary": "S0", "scene_type": "战斗", "importance": "高"},
        {"summary": "S1", "scene_type": "日常", "importance": "低"},
        {"summary": "S2", "scene_type": "转折", "importance": "低"},
    ]


def test_valid_scores_drive_selection():
    cli = _Cli(json.dumps({"scores": [{"i": 0, "score": 10},
                                      {"i": 1, "score": 20},
                                      {"i": 2, "score": 99}]}))
    out = asyncio.run(mining.score_scenes(cli, _scenes(), 1))
    assert [s["summary"] for s in out] == ["S2"]      # LLM 选最高分 scene2
    assert cli.calls == 1                              # 首试通过即 break


def test_exhaustion_warns_and_falls_back_to_heuristic(capsys):
    cli = _Cli("这不是json <<<")
    out = asyncio.run(mining.score_scenes(cli, _scenes(), 1))
    assert [s["summary"] for s in out] == ["S0"]      # 回退: importance=高 的 scene0
    assert cli.calls == 2                              # retries=2 耗尽
    assert "场景打分LLM重试耗尽" in capsys.readouterr().err


def test_small_pool_short_circuits_no_llm():
    cli = _Cli("should-not-be-called")
    scenes = _scenes()
    out = asyncio.run(mining.score_scenes(cli, scenes, 5))   # keep_n >= len → 早返
    assert out == scenes
    assert cli.calls == 0
