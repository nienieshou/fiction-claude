"""一次性: HFL 追加 R9 轮 Fable 四维评分(3本;末世囤物资崩溃重跑中)。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
recs = [
    {"date": "2026-06-11", "scorer": "fable", "round": 9, "title": "飞升后我成了仙二代",
     "source": "ZYGGY03733团宠小师妹靠摆烂带飞全宗门", "dims": {"拉力": 64, "笔力": 69, "人": 71, "承重": 40},
     "total": 62.2,
     "comments": "锚差分-4.2(r7=66.4):r7三类缺陷全复发且更重;渡劫写4遍(ch57/58x2/60,macro排重实证=plan.json里ch58引天劫+ch60又引动天劫)/飞升两版/宗主三版并存/修为乱序;点修3轮不收敛(傅礼确死但ch47-48持续在场=该修死亡处)",
     "auto_signals": {"final_consistent": False, "交付门": "事实表死人复活3+fc", "plan握手": "20/20", "章缝": 23},
     "version": "R9(章内顺序+生死verify门)"},
    {"date": "2026-06-11", "scorer": "fable", "round": 9, "title": "七零：我在末世前建了个桃花源",
     "source": "ZYGXN01882穿越七零，闪婚糙汉甜蜜蜜", "dims": {"拉力": 62, "笔力": 70, "人": 64, "承重": 36},
     "total": 59.3,
     "comments": "**点修通道误放实证**(曾交付后撤回):母亲三版(死葬/被囚/敌方棋子)/原身死法三版/顾祁川四身份/古代源残片渗入(县衙捕快)/空间设定两版——fc浅复检(前60k+随机)看不见ch18+;同章双版本3处(R9-1未达标)",
     "auto_signals": {"final_consistent": False, "交付门": "评审撤回59.3", "plan握手": "20/20", "章缝": 16},
     "version": "R9(章内顺序+生死verify门)"},
    {"date": "2026-06-11", "scorer": "fable", "round": 9, "title": "兽世粮荒：空间养崽守城",
     "source": "ZYGGX02148带三只废柴崽崽，携空间称霸兽世！", "dims": {"拉力": 71, "笔力": 69, "人": 70, "承重": 56},
     "total": 67.9,
     "comments": "开篇达准签约,爽点引擎在线;承重:骥川确死后28/30/52章活跃(死亡线被丢弃=该修死亡处)/单容双姓串台/币制漂移(铜板银币两银票混用,点修只修了ch2没修ch3=多章issue只解析首个章号bug)/体系三套(淬体锻体灵徒);同章双版本2处",
     "auto_signals": {"final_consistent": False, "交付门": "事实表死人复活1+fc", "plan握手": "20/20", "章缝": 27},
     "version": "R9(章内顺序+生死verify门)"},
]
with open("assets/hfl.jsonl", "a", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("ok", sum(1 for _ in open("assets/hfl.jsonl", encoding="utf-8")), "行")
