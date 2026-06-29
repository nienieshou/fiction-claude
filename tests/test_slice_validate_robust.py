"""C6 残留: slice_validate dev 工具纪律拉齐 —— EXTRACT 失软 + craft_audit 门控。
零 API; fake cli 按固定串回应。"""
import asyncio
import json
import pytest
from hiki import slice_validate


class _Cli:
    """每次 complete 返回同一固定串; 记调用次数。"""
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def complete(self, *a, **k):
        self.calls += 1
        return self.reply


def test_extract_valid_returns_dna():
    cli = _Cli(json.dumps({"scenes": [{"i": 0}], "voice": "网文白话", "bible": {}}))
    dna = asyncio.run(slice_validate._extract_dna(cli, "切片源文本"))
    assert dna["scenes"] == [{"i": 0}]
    assert dna["voice"] == "网文白话"
    assert cli.calls == 1                       # 首试通过即返回


def test_extract_malformed_raises_after_retry():
    cli = _Cli("这不是json <<<")
    with pytest.raises(RuntimeError, match="EXTRACT 失败"):
        asyncio.run(slice_validate._extract_dna(cli, "切片源文本"))
    assert cli.calls == 2                       # retries=2 耗尽


def test_extract_partial_no_scenes_raises():
    cli = _Cli(json.dumps({"voice": "x"}))      # 解析成功但无 scenes
    with pytest.raises(RuntimeError, match="EXTRACT 失败"):
        asyncio.run(slice_validate._extract_dna(cli, "切片源文本"))
    assert cli.calls == 2                       # schema 拒 → 重试耗尽
