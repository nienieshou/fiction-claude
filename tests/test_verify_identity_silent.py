# -*- coding: utf-8 -*-
"""A3 wave4: verify_identity 静默失败硬化 —— infra真失败(LLM解析耗尽)与判定假分离。
零 API; fake cli 按固定串回应。"""
import asyncio
from hiki import prose_facts


class _Cli:
    """每次 complete 返回同一固定串; 记调用次数。"""
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def complete(self, *a, **k):
        self.calls += 1
        return self.reply


def _id_finding() -> dict:
    return {"cat": "身份", "who": "张三", "va": "圣子", "vb": "圣帝", "ch_a": 1, "ch_b": 2}


_CHS = ["首章 张三 自称圣子 行走江湖", "次章 张三 被尊圣帝 君临天下"]


def test_parse_exhaustion_flags_verify_failed_and_warns(capsys):
    cli = _Cli("这不是json")
    f = _id_finding()
    asyncio.run(prose_facts.verify_identity(cli, [f], _CHS))
    assert f["real"] is False                 # 保『存疑不报』
    assert f.get("verify_failed") is True      # infra真失败被标
    assert cli.calls == 2                       # retries=2
    assert "身份验证LLM重试耗尽" in capsys.readouterr().err


def test_parse_success_real_true_no_flag():
    cli = _Cli('{"real": true, "reason": "圣子与圣帝同维互斥"}')
    f = _id_finding()
    asyncio.run(prose_facts.verify_identity(cli, [f], _CHS))
    assert f["real"] is True
    assert f["reason"] == "圣子与圣帝同维互斥"
    assert "verify_failed" not in f
    assert cli.calls == 1                       # 首试成功即 break


def test_judged_false_is_not_infra_failure():
    cli = _Cli('{"real": false}')
    f = _id_finding()
    asyncio.run(prose_facts.verify_identity(cli, [f], _CHS))
    assert f["real"] is False
    assert "verify_failed" not in f            # 判定假 ≠ infra失败
    assert cli.calls == 1


def test_empty_values_short_circuit_no_llm():
    cli = _Cli("不该被调用")
    f = {"cat": "身份", "who": "张三", "va": "", "vb": "", "ch_a": 1, "ch_b": 2}
    asyncio.run(prose_facts.verify_identity(cli, [f], _CHS))
    assert f["real"] is True
    assert "verify_failed" not in f
    assert cli.calls == 0                       # va/vb 空 → 早返, 无 LLM 调用


def test_verify_failed_does_not_leak_into_gate_count():
    """门等价钉死: verify_failed 标记不改 spine_id_contra(只数 real)。"""
    findings = [
        {"cat": "身份", "real": True},
        {"cat": "身份", "real": False, "verify_failed": True},
    ]
    counts = prose_facts.signal_counts_from_fact_table({"findings": findings})
    assert counts["spine_id_contra"] == 1
