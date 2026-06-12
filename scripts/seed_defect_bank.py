"""飞轮①: defect_bank.jsonl 种子——R8-R12 评审证实的缺陷,落到仍存在该缺陷的冻结版本上。
detector 字段=该类该由哪个仪器抓(none=已知检测缺口,回归重放时作缺口清单);
baseline_hit 由首次回归重放回填。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

B = [
    # --- 生死类(fact_table_deaths 应抓) ---
    dict(book="冷战", path="output/ZYGXY01847冷战三年，离婚当日纪总哭红了眼_full", ch=47, cat="生死",
         issue="纪老夫人15章死亡火化,47章复活后二次死亡", quote="纪老夫人", detector="fact_table_deaths"),
    dict(book="狂医", path="output/DPBXN00507狂医战神_full", ch=31, cat="生死",
         issue="白珑15章'全部解决'31章宴席夹菜", quote="白珑", detector="fact_table_deaths"),
    dict(book="狂医", path="output/DPBXN00507狂医战神_full", ch=43, cat="生死",
         issue="杜门35章眉心血洞43章持圣旨", quote="杜门", detector="fact_table_deaths"),
    dict(book="团宠r9", path="output/ZYGGY03733团宠小师妹靠摆烂带飞全宗门_full_r9", ch=47, cat="生死",
         issue="傅礼21章化飞灰23章火化,47章同桌议事", quote="傅礼", detector="fact_table_deaths"),
    # --- 版本互斥类(邻章头部=ADJ_DUP;深处/同章=none 检测缺口) ---
    dict(book="团宠r9", path="output/ZYGGY03733团宠小师妹靠摆烂带飞全宗门_full_r9", ch=58, cat="邻章互斥",
         issue="渡劫ch57→58重演", quote="渡劫", detector="adj_dup"),
    dict(book="白月光", path="output/ZTGGX02751听说我死后成了反派白月光_full", ch=1, cat="同章双版本",
         issue="ch1双开场:系统绑定两版初遇", quote="攻略系统激活成功", detector="none"),
    dict(book="大罗金仙", path="output/CPBGX00031我真不是大罗金仙(带房穿越修仙世界)73W_full", ch=13, cat="同章双版本",
         issue="栾一笑残魂同章双结局(遁走又被捏碎)", quote="残魂", detector="none"),
    dict(book="大罗金仙", path="output/CPBGX00031我真不是大罗金仙(带房穿越修仙世界)73W_full", ch=56, cat="邻章互斥",
         issue="ch55守清羽抗皇帝→ch56皇帝受降,阵营反转", quote="清羽", detector="adj_dup"),
    dict(book="军旅", path="output/ZYGXY02151对照组女配在军旅综艺爆红了_full", ch=2, cat="邻章互斥",
         issue="ch1已开录'信任大挑战'vs ch2集合日选拔,前提两开", quote="极限突击", detector="adj_dup"),
    dict(book="星际tier1", path="output/ZYGWJ02935大佬她美飒全星际_full_tier1", ch=59, cat="跨章互斥",
         issue="母亲死因三版本(58/59/60)", quote="克隆体", detector="none"),
    # --- 数值/体系类 ---
    dict(book="灵气", path="output/CPBGX00192灵气复苏：开局无限合成_full", ch=6, cat="数值",
         issue="陆景气血27.35→25.36倒退", quote="25.36", detector="fact_table_power"),
    dict(book="兽世", path="output/ZYGGX02148带三只废柴崽崽，携空间称霸兽世！_full", ch=3, cat="数值",
         issue="赔偿币种ch2百铜板vs ch3二十银币", quote="二十枚银币", detector="advisory_verify"),
    # --- 时代锚 ---
    dict(book="重生八零", path="output/ZYGXY02032重生在高考：带着糙汉发家致富_full", ch=20, cat="时代锚",
         issue="1984出现手机/聊天群", quote="聊天群", detector="era_anachronism"),
    # --- 残句/损伤 ---
    dict(book="灵气", path="output/CPBGX00192灵气复苏：开局无限合成_full", ch=31, cat="残句",
         issue="孤行截断「狼首异」", quote="狼首异", detector="broken_prose"),
    dict(book="重生八零", path="output/ZYGXY02032重生在高考：带着糙汉发家致富_full", ch=26, cat="残句",
         issue="源标题泄漏「第一百零七章 选料」", quote="第一百零七章", detector="broken_prose"),
    # --- 谱系/身份(检测缺口) ---
    dict(book="重生八零", path="output/ZYGXY02032重生在高考：带着糙汉发家致富_full", ch=60, cat="身份谱系",
         issue="父亲三易其人(榆成波/宋长丰)", quote="宋长丰", detector="none"),
    dict(book="七零", path="output/ZYGXN01882穿越七零，闪婚糙汉甜蜜蜜_full", ch=18, cat="身份谱系",
         issue="母亲三版(死葬/被囚/敌方棋子)", quote="李雪", detector="none"),
    # --- 内容 ---
    dict(book="末世", path="output/ZYGWM06026末世重生，我疯狂囤物资逆袭大佬_full", ch=27, cat="内容暗黑",
         issue="处决私刑当爽点细品+异能奖励(23-28弧)", quote="生来就只配当垃圾", detector="content_filter"),
    # --- 跳空 ---
    dict(book="原始", path="output/ZYGGY02015穿到原始的我每天都在求生_full", ch=60, cat="预告跳空",
         issue="ch59末'下游部落被灭'ch60零回应(点修前)", quote="下游", detector="ending_check"),
]
with open("assets/defect_bank.jsonl", "w", encoding="utf-8") as f:
    for i, e in enumerate(B):
        e.update({"id": f"D{i+1:03d}", "verified_by": "fable_review+grep", "date": "2026-06-12",
                  "baseline_hit": None})
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
print(f"defect_bank 种子 {len(B)} 条;检测缺口(detector=none): "
      f"{sum(1 for e in B if e['detector'] == 'none')} 条")
