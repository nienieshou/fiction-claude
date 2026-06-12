"""一次性: HFL 追加 R11 轮 Fable 评分(5本)。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
recs = [
    {"date": "2026-06-12", "scorer": "fable", "round": 11, "title": "炮灰渡劫：我命由我不由天(交付版)",
     "source": "ZYGGY03733团宠小师妹靠摆烂带飞全宗门", "dims": {"拉力": 64, "笔力": 66, "人": 68, "承重": 74},
     "total": 67.5,
     "comments": "锚:R10 66.7→67.5(+0.8,点修净疗效减半):傅礼线/修为线修净+1.5,殿审ch31/32与茶壶ch57/58两处双版本'采用却没修净'(采用守卫只查长度的教训)+终章她x2性别错代(点修引入)。注:本条四维为重排后口径(评审用了不同维序,总分可比)",
     "auto_signals": {"deliverable": True, "点修轮数": 4}, "version": "R10+点修交付版"},
    {"date": "2026-06-12", "scorer": "fable", "round": 11, "title": "死而复生：我全球直播组队",
     "source": "CPBXN00188开局冰川探墓", "dims": {"拉力": 71, "笔力": 72, "人": 63, "承重": 56},
     "total": 66.3,
     "comments": "裸过门交付但实读判误放:双开局(红色湿土任务两版)/ch31古尸战双版本/ch58-59死法机制互斥(灵魂抽取vs肉身崩解)/邻章重演残留3>申报2;直播融合度七成。advisory=无与实读不符=continuity对版本互斥假阴性",
     "auto_signals": {"deliverable": True, "邻章版本": "9/7", "门": "裸过"}, "version": "R11(邻章检修+修为闭环+灰区判读)"},
    {"date": "2026-06-12", "scorer": "fable", "round": 11, "title": "弈世女帝：赢你生生世世",
     "source": "ZTGGY02021摄政王妃", "dims": {"拉力": 73, "笔力": 77, "人": 62, "承重": 53},
     "total": 67.3,
     "comments": "裸过门交付但实读判误放:ch31/32庆王入场双演+断指换人/ch45女帝五年vs ch46明日登基(时间灾难)/国名三版(连阳/大启/珈蓝)/婚礼三现;笔力77全批最高。大事件禁演x3生效但只覆盖关键词类,战斗/求娶类漏",
     "auto_signals": {"deliverable": True, "大事件禁演": 3, "门": "裸过"}, "version": "R11"},
    {"date": "2026-06-12", "scorer": "fable", "round": 11, "title": "原始种田：异世魂归被全族宠上天",
     "source": "ZYGGY02015穿到原始的我每天都在求生", "dims": {"拉力": 76, "笔力": 76, "人": 65, "承重": 58},
     "total": 69.7,
     "comments": "全批最高,拦截正确:水原灭族伏笔跨38章兑现=长线能力真实;程小虎复活该修死亡处(认尸+哭灵+婚约重戏不可删);ch59末'下游部落被灭'预告跳空;ch31→32同战重演。'章缝9全批最低'=假好:缝平≠接对,版本互斥全数假阴性(评审原话)",
     "auto_signals": {"deliverable": False, "门": "跳空+生死残留"}, "version": "R11"},
    {"date": "2026-06-12", "scorer": "fable", "round": 11, "title": "末世囤货：我建了座希望城",
     "source": "ZYGWM06026末世重生，我疯狂囤物资逆袭大佬", "dims": {"拉力": 64, "笔力": 73, "人": 56, "承重": 42},
     "total": 59.9,
     "comments": "**第二次误放已撤回**(点修通道复检盲区):前世死法5版互斥/ch27-28处决换名重演/ch30-33同战三版本/ch50-57vs58-60双结局世界线/Q类暗黑残留弧(23-28私刑细品当爽点+升级奖励,content_filter dark_ratio 0.05漏检)。复检必须加content扫描",
     "auto_signals": {"deliverable": False, "撤回": True}, "version": "R11(点修后误放)"},
]
with open("assets/hfl.jsonl", "a", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("ok", sum(1 for _ in open("assets/hfl.jsonl", encoding="utf-8")), "行")
