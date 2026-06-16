"""audit.py 纯函数:broken_prose 合成用例 + _power_rank/power_order_from_bible。零 API。
(原 scripts/_test_broken_prose.py + _test_r13_units #6 迁入;file-dependent 部分略去保持可移植)"""
from hiki.audit import broken_prose, _power_rank, power_order_from_bible


def test_broken_prose_synthetic():
    chs = ["他抬起手,正要说话,却发现整个广场都安静了下来,所有人的目光都集中在那道身影上,",
           "狼首异/咔嚓!巨响震彻全场。\n正常段落在这里结束。",
           "正常的一章。对话也正常。"]
    hits = broken_prose(chs)
    assert any("段尾残句" in h and "第1章" in h for h in hits), hits
    assert any("斜杠拼接" in h and "第2章" in h for h in hits), hits
    assert not any("第3章" in h for h in hits), hits


def test_power_rank_paren_not_hijacked():
    # R13c 52处钉反根因: 括号内'渡劫'不得把'练气'劫持到 rank10
    assert _power_rank("练气大圆满（渡劫中）") == 1
    assert _power_rank("练气圆满") == 1                # 绞丝旁识别
    assert _power_rank("筑基初期") > _power_rank("练气大圆满（渡劫中）")


def test_power_order_from_bible():
    assert power_order_from_bible({"escalation_ladder": "练气→筑基→金丹，赌注…"}) == ["练气", "筑基", "金丹"]
    assert power_order_from_bible({"escalation_ladder": "瞎写的"}) is None   # 解析不出→退默认梯
