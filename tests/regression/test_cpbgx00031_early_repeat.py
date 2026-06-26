"""校准集种子用例:CPBGX00031 ch1/ch2 是同一'许安初访'事件的两个版本(逐句通读 2026-06-26 确认)。
内核(零API):early_repeat>0 时 opening_immersion=90 也必须被门拦。
golden(需API):真实检测器对 ch1/ch2 应判 count>=1。"""
import asyncio
from pathlib import Path
import pytest
from hiki import gate, audit

D = gate.SHIP_GATE_DEFAULTS
FIXTURE = Path(__file__).parent / "fixtures" / "cpbgx00031_ch1_ch2.txt"


def test_early_repeat_forces_block_even_with_high_immersion():
    # 系统当时:opening_immersion=90 放行(假高分)。期望:early_repeat 存在 → 必拦。
    sig_bug = {"开篇代入感": 90}                       # 旧行为:漏过
    assert gate.evaluate_ship_gate(sig_bug, D) == []
    sig_fixed = {"开篇代入感": 90, "早段重复": 1}        # 新行为:封顶30→拦
    issues = gate.evaluate_ship_gate(sig_fixed, D)
    assert len(issues) == 1 and "开篇代入感" in issues[0]


def test_deliverable_false_when_early_repeat_present():
    # 端到端语义:有早段重复且无其它问题时,ship_issues 非空 → deliverable=false
    assert gate.evaluate_ship_gate({"开篇代入感": 90, "早段重复": 2}, D) != []


@pytest.mark.api
def test_real_detector_flags_cpbgx_ch1_ch2():
    # 默认 skip(需真实 API)。CI/手动带 -m api 时跑,验证检测器对真实病灶不漏。
    from hiki.client import Client          # 既有客户端入口
    text = FIXTURE.read_text(encoding="utf-8")
    # 以 "# 第2章" 为界切两章
    parts = text.split("# 第2章")
    ch1, ch2 = parts[0], "# 第2章" + parts[1]
    cli = Client()
    r = asyncio.run(audit.early_repeat_audit(cli, [ch1, ch2]))
    assert r["count"] >= 1, f"应检出早段重复,实得 {r}"
