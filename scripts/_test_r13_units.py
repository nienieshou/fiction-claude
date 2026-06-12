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
cp = _control_plane(2, plan, settled, plan["chapters"][1]["exit_state"])
assert "傅礼(第2章亡" in cp and "山巅劫云散尽" in cp and "与师父道别" in cp and "渡劫成功" in cp, cp
assert "控制面·铁律" in cp
print("控制面编译 ok:\n" + cp)
