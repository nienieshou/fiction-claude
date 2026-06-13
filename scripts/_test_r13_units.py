"""R13 纯函数单测: _wave_bounds 护栏/退化 + _control_plane 编译 + _settle_facts。零API。"""
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.produce import _wave_bounds, _control_plane, _settle_facts

# 1) act 正常: 5幕
beats = ([{"act": "开篇"}] * 8 + [{"act": "发展"}] * 20 + [{"act": "转折"}] * 14
         + [{"act": "高潮"}] * 12 + [{"act": "结局"}] * 6)
w = _wave_bounds(beats, 60)
assert all(4 <= b - a <= 12 for a, b in w), w          # 护栏: 4-12章/波
assert w[0][0] == 0 and w[-1][1] == 60 and all(w[i][1] == w[i + 1][0] for i in range(len(w) - 1)), w
print("act对齐+护栏 ok:", [(a + 1, b) for a, b in w])

# 2) act 畸形(全同) → 退化固定切口
w2 = _wave_bounds([{"act": "发展"}] * 60, 60)
assert all(4 <= b - a <= 13 for a, b in w2), w2
print("畸形退化 ok:", [(a + 1, b) for a, b in w2])

# 3) act 缺失
w3 = _wave_bounds([{}] * 60, 60)
assert w3[0][0] == 0 and w3[-1][1] == 60, w3
print("act缺失 ok:", [(a + 1, b) for a, b in w3])

# 4) 控制面编译
plan = {"chapters": [
    {"key_events": ["叶离当众揭穿傅礼伪造账册,傅礼被禁足"], "exit_state": "叶离立于大殿中央"},
    {"key_events": ["渡劫成功破入元婴"], "exit_state": "山巅劫云散尽"},
    {"key_events": ["与师父道别"], "exit_state": ""},
]}
settled = {"deaths": {}, "power": {}}
_settle_facts(settled, [{"deaths": [{"who": "傅礼", "clue": "x"}], "power": [["叶离", "元婴初期"]]}], 1)
prev_exit = plan["chapters"][1]["exit_state"]
cp0 = _control_plane(2, 0, plan, settled, prev_exit)        # 章首场景
assert "傅礼(第2章亡" in cp0 and "山巅劫云散尽" in cp0 and "渡劫成功" in cp0, cp0
assert "本章必演" in cp0 and "与师父道别" in cp0, cp0        # 首场景: 命令演出
assert "控制面·铁律" in cp0
print("控制面编译(si=0) ok:\n" + cp0)

# B1-bug回归守卫: 章内后场景(si>0)绝不再命令重演本章已演事件(团宠ch49近逐字复刻根因)
cp1 = _control_plane(2, 1, plan, settled, prev_exit)
assert "本章必演" not in cp1, cp1                           # 后场景: 不得再下"必演"令
assert "已在前序场景演出完毕" in cp1 and "与师父道别" in cp1, cp1   # 改标"已演完,禁重演"
assert "开场前提" not in cp1, cp1                           # 开场前提只属章首场景
assert "傅礼(第2章亡" in cp1, cp1                           # 生死/数值账仍每场景兜底
print("控制面编译(si>0,回归守卫) ok:\n" + cp1)

# 5) R14 账本扩面: 身份账(canon钉死)+物品账(终态禁复出)
plan["chapters"][2]["scenes"] = [{"brief": "傅礼当殿发难"}]   # 让本章文本点到傅礼名
_settle_facts(settled, [{"items": [["雷灵珠", "碎裂成齑粉"], ["茶壶", "使用中"]]}], 49)
id_map = {"傅礼": "青阳宗宗主(青阳宗)", "成器": "太一宗宗主(太一宗)"}
cp2 = _control_plane(2, 0, plan, settled, prev_exit, id_map)
assert "身份账" in cp2 and "傅礼=青阳宗宗主(青阳宗)" in cp2, cp2   # 本章点名→钉身份
assert "成器=" not in cp2, cp2                              # 本章没点名→不注入(防膨胀)
assert "物品账" in cp2 and "雷灵珠(第50章碎裂成齑粉,绝不再完好出现" in cp2, cp2
assert "茶壶" not in cp2, cp2                               # 非终态不入账
print("R14账本扩面(身份+物品) ok:\n" + cp2)

# 6) R13c _power_rank 回归(52处钉反根因)
from hiki.audit import _power_rank, power_order_from_bible
assert _power_rank("练气大圆满（渡劫中）") == 1              # 不再被括号'渡劫'劫持到rank10
assert _power_rank("练气圆满") == 1                          # 绞丝旁识别
assert _power_rank("筑基初期") > _power_rank("练气大圆满（渡劫中）")
assert power_order_from_bible({"escalation_ladder": "练气→筑基→金丹，赌注…"}) == ["练气", "筑基", "金丹"]
assert power_order_from_bible({"escalation_ladder": "瞎写的"}) is None   # 解析不出→退默认梯
print("R13c境界排序回归 ok")
