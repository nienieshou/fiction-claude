"""交付门纯函数 gate.evaluate_ship_gate 单测(D1 后门可测)。零 API。
用法: PYTHONPATH=src python scripts/_test_gate.py"""
import sys
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki import gate

D = gate.SHIP_GATE_DEFAULTS

# 1) 全干净 → 空(可交付)
assert gate.evaluate_ship_gate({}, D) == [], "空信号应可交付"
assert gate.evaluate_ship_gate({"final_consistent": True}, D) == []

# 2) 各阈值边界(默认: too_short>=3, dark>0.25, seam>8, reenact>=1, spine>=2)
assert gate.evaluate_ship_gate({"过短章数": 2}, D) == []                 # 2<3 不拦
assert len(gate.evaluate_ship_gate({"过短章数": 3}, D)) == 1            # 3>=3 拦
assert gate.evaluate_ship_gate({"暗黑比": 0.25}, D) == []               # =0.25 不拦(>)
assert len(gate.evaluate_ship_gate({"暗黑比": 0.26}, D)) == 1
assert gate.evaluate_ship_gate({"残缝": 8}, D) == []                    # =8 不拦(>)
assert len(gate.evaluate_ship_gate({"残缝": 9}, D)) == 1
assert len(gate.evaluate_ship_gate({"事件重演": 1}, D)) == 1            # >=1 拦
assert gate.evaluate_ship_gate({"数值真矛盾": 1, "身份真矛盾": 0}, D) == []   # 1<2 不拦(防单条噪声)
assert len(gate.evaluate_ship_gate({"数值真矛盾": 1, "身份真矛盾": 1}, D)) == 1  # 合计2 拦

# 3) 生死: 事实表跑过 → plan维14 只 advisory(不进门); 没跑过 → 兜底进门
assert gate.evaluate_ship_gate({"plan维14复活": 2, "事实表跑过": True}, D) == []
assert len(gate.evaluate_ship_gate({"plan维14复活": 2, "事实表跑过": False}, D)) == 1

# 4) final_consistent 缺省视为 True(不拦); False 拦
assert gate.evaluate_ship_gate({}, D) == []
assert len(gate.evaluate_ship_gate({"final_consistent": False}, D)) == 1

# 5) 崩溃审计 → 拦(A2)
assert len(gate.evaluate_ship_gate({"承重审计崩溃": True}, D)) == 1

# 6) config 阈值可覆盖默认(D1 配置驱动)
loose = {**D, "spine_net_min": 5}
assert gate.evaluate_ship_gate({"数值真矛盾": 2, "身份真矛盾": 2}, loose) == []  # 4<5 放行
strict = {**D, "reenact_min": 1, "seam_residual_max": 0}
assert len(gate.evaluate_ship_gate({"残缝": 1}, strict)) == 1                  # 收紧后 1>0 拦

# 7) 多信号累计
multi = gate.evaluate_ship_gate(
    {"过短章数": 3, "残缝": 9, "事件重演": 2, "数值真矛盾": 2, "承重审计崩溃": True}, D)
assert len(multi) == 5, multi

print("gate.evaluate_ship_gate 单测 ok")
