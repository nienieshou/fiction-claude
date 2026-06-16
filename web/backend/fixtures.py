"""原型 mock 数据（从 prototype/_unpacked/component.js 移植）= 适配器的 fixture 兜底源。

真实产物缺失某本/某字段时回退到这里，保证 UI 永远有数据。
数据形状 = §1 契约（见 docs/design/web_console.md）。
"""
from __future__ import annotations

# 6 段流水线定义（与前端共享，前端也内置一份兜底）
STAGES = [
    {"name": "Ingest", "cn": "清洗", "sub": "去脏·拼接", "model": "flash"},
    {"name": "Extract", "cn": "DNA", "sub": "脊柱·钩子", "model": "pro"},
    {"name": "Plan", "cn": "规划", "sub": "outline60", "model": "pro"},
    {"name": "Draft", "cn": "草稿", "sub": "场景·提纯", "model": "flash"},
    {"name": "Evaluate", "cn": "闸门", "sub": "对照 PK", "model": "pro·flash"},
    {"name": "Assemble", "cn": "拼装", "sub": "验收报告", "model": "—"},
]

MODE = {0: "—", 1: "模式1 · 保真压缩", 2: "模式2 · 强化改写",
        3: "模式3 · 类型化重构", 4: "模式4 · 概念级重启"}
MODE_NOTE = {0: "未进入质量环", 1: "强源主路径 · 只需 +5", 2: "补强弱钩子 + 关键章 BoN",
             3: "按题材范式重排 beat", 4: "最高风险 · 仅保概念"}

BOOKS = [
    {"id": "hunyin", "title": "隐婚·偏偏宠我", "src": "霸总隐婚之偏偏宠我",
     "slug": "霸总隐婚_隐婚偏偏宠我_20260601", "genre": "现代言情", "grade": "A",
     "comp": "高", "stage": 5, "status": "certified", "mode": 1, "human": 75, "cost": 31},
    {"id": "tuihun", "title": "退婚·首富千金", "src": "重生之首富归来",
     "slug": "首富归来_退婚首富千金_20260603", "genre": "都市爽文", "grade": "B",
     "comp": "高", "stage": 5, "status": "certified", "mode": 2, "human": 76, "cost": 38},
    {"id": "zhaidou", "title": "宅斗·庶女谋嫁", "src": "庶女当自强",
     "slug": "庶女当自强_宅斗庶女谋嫁_20260605", "genre": "古代言情", "grade": "A",
     "comp": "中", "stage": 5, "status": "certified", "mode": 1, "human": 68, "cost": 34},
    {"id": "chuanyue", "title": "重生·穿回那年", "src": "重回十八岁",
     "slug": "重回十八岁_重生穿回那年_20260612", "genre": "穿越重生", "grade": "C",
     "comp": "中", "stage": 3, "status": "running", "mode": 2, "human": 63, "cost": 22},
    {"id": "aoshi", "title": "傲世·苍穹诀", "src": "苍穹至尊诀",
     "slug": "苍穹至尊_傲世苍穹诀_20260608", "genre": "玄幻", "grade": "S",
     "comp": "低", "stage": 4, "status": "rejected", "mode": 3, "human": 54, "cost": 47},
    {"id": "wendao", "title": "问道·仙途", "src": "凡人问道录",
     "slug": "凡人问道_问道仙途_20260615", "genre": "仙侠", "grade": "B",
     "comp": "中", "stage": 1, "status": "running", "mode": 0, "human": None, "cost": 4},
    {"id": "xingji", "title": "星际·机甲纪元", "src": "机甲狂潮",
     "slug": "机甲狂潮_星际机甲纪元_20260614", "genre": "科幻", "grade": "D",
     "comp": "低", "stage": 2, "status": "running", "mode": 3, "human": None, "cost": 15},
    {"id": "qiandao", "title": "签到·从今天暴富", "src": "签到系统流",
     "slug": "签到系统_从今天暴富_20260616", "genre": "都市系统", "grade": "Q",
     "comp": "Q", "stage": 0, "status": "rejected", "mode": 0, "human": None, "cost": 1},
]

CALIB = {
    "note": "承重门微观信号（重演/spine/final）与人类承重判分 零相关；同文承重自评 ±40 抖动 → 已降 advisory（A）。",
    "points": [
        {"label": "隐婚", "auto": 71, "human": 62, "c": "#3fb950"},
        {"label": "退婚", "auto": 55, "human": 65, "c": "#3fb950"},
        {"label": "宅斗", "auto": 78, "human": 58, "c": "#3fb950"},
        {"label": "穿越", "auto": 60, "human": 55, "c": "#58a6ff"},
        {"label": "傲世", "auto": 82, "human": 38, "c": "#f85149"},
    ],
}

# 每本详情（dna/scenes/gate/cost/dims/review/spine）。完整移植自 component.js DETAILS()。
DETAILS: dict[str, dict] = {
    "hunyin": {
        "dna": [
            {"label": "脊柱 spine", "v": "豪门隐婚→误会→揭身份→双向救赎", "note": "5 卷主弧"},
            {"label": "钩子账 hooks", "v": "12 强钩 · 章均 0.9", "note": "保源已验证钩子"},
            {"label": "情感曲线 emotion", "v": "虐30% · 甜55% · 燃15%", "note": ""},
            {"label": "人物弧 arcs", "v": "女主 隐忍→觉醒 · 男主 偏执→信任", "note": ""},
            {"label": "伏笔 foreshadow", "v": "7 处 · 全回收", "note": ""},
            {"label": "爽点 payoffs", "v": "打脸9 · 撒糖21 · 逆袭4", "note": ""},
            {"label": "人名词典 names", "v": "37 实体冻结", "note": "→ Fact Spine"},
            {"label": "语域指纹 voice", "v": "轻快口语 + 内心独白", "note": "cosine 基线"},
            {"label": "题材 genre", "v": "现代言情 · 隐婚 · 甜宠", "note": ""},
        ],
        "scenes": {"total": 60, "drafted": 60, "peaks": [12, 28, 44, 57], "list": [
            {"n": 1, "type": "DRAMATIZE", "beat": "婚礼现场认错人", "status": "pass", "cand": 5, "pk": "胜源 · 明显"},
            {"n": 12, "type": "DRAMATIZE", "beat": "身份揭穿 · 第一高点", "status": "pass", "cand": 8, "pk": "达金标"},
            {"n": 28, "type": "DRAMATIZE", "beat": "误会爆发 · 分离", "status": "pass", "cand": 8, "pk": "达金标"},
            {"n": 33, "type": "SUMMARIZE", "beat": "三个月后 · 过渡", "status": "pass", "cand": 2, "pk": "胜源"},
            {"n": 57, "type": "DRAMATIZE", "beat": "机场挽回 · 终章高点", "status": "pass", "cand": 8, "pk": "达金标"},
        ]},
        "gate": {"mech": [
            {"k": "AI腔密度", "v": "0.7%", "pass": True, "note": "阈 <3%"},
            {"k": "风格 cosine vs 源", "v": "0.86", "pass": True, "note": "换皮 0.6–0.9"},
            {"k": "注水残留", "v": "1.2%", "pass": True, "note": "五类注水"},
            {"k": "语病/人名一致", "v": "100%", "pass": True, "note": "37 实体"},
            {"k": "结构合规", "v": "60章 · 均3480字 · 4-beat", "pass": True, "note": "首章交代 ✓"},
            {"k": "逐字重合", "v": "4.1%", "pass": True, "note": "原创下限 <8%"},
        ], "pk": [
            {"vs": "本书源（下锚）", "verdict": "明显胜", "score": "82% 胜率", "pass": True},
            {"vs": "金标 95（上锚）", "verdict": "临界达标", "score": "48% 持平", "pass": True},
            {"vs": "标杆 90（近目标）", "verdict": "略低", "score": "43%", "pass": True},
        ], "book": [
            {"k": "弧光收束", "pass": True, "note": ""}, {"k": "节奏曲线", "pass": True, "note": ""},
            {"k": "主题统一", "pass": True, "note": ""}, {"k": "结尾落点", "pass": True, "note": ""},
            {"k": "全书连续性审计", "pass": True, "note": "状态机·伏笔账·时间线 ✓"},
        ]},
        "cost": [
            {"k": "Extract", "usd": 0.20, "note": "flash 首读 · 缓存"},
            {"k": "Plan", "usd": 0.30, "note": "pro 分层"},
            {"k": "Draft", "usd": 0.26, "note": "flash 主力"},
            {"k": "锦标赛+精修", "usd": 0.90, "note": "4 高点大 N"},
            {"k": "闸门 PK", "usd": 2.60, "note": "评估大头"},
        ],
        "dims": [{"k": "承重", "v": 62}, {"k": "笔力", "v": 90}, {"k": "开篇代入", "v": 78},
                 {"k": "钩子爽点", "v": 80}, {"k": "节奏", "v": 76}, {"k": "人物", "v": 74}],
        "review": {"total": 75, "version": "gate@v5.1 · spine@on", "mode": "M1 深度长评",
                   "text": "甜宠节奏到位，撒糖密度够；去套话重写后笔力跃至 90。承重尚可但中段两处人物动机断层。达出货线 75，当前最佳。",
                   "snapshot": [{"k": "承重门信号", "v": "0.71（虚高）"}, {"k": "笔力自评", "v": "82"}, {"k": "PK 金标", "v": "48%"}]},
        "spine": [
            {"group": "人物登记", "items": [
                {"name": "苏挽", "attr": "女主 · 设计师 · 真千金", "lock": True},
                {"name": "霍司珩", "attr": "男主 · 霍氏总裁", "lock": True},
                {"name": "苏曼", "attr": "伪千金 · 反派", "lock": True}]},
            {"group": "关键物品", "items": [{"name": "翡翠镯", "attr": "母亲遗物 · 认亲信物", "lock": True}]},
            {"group": "时间线", "items": [{"name": "隐婚→揭穿", "attr": "第 3 年 · 第 12 章", "lock": True}]},
        ],
    },
    "tuihun": {
        "dna": [
            {"label": "脊柱 spine", "v": "被退婚→打脸逆袭→真身份揭晓", "note": "5 卷主弧"},
            {"label": "钩子账 hooks", "v": "15 强钩 · 章均 1.1", "note": ""},
            {"label": "情感曲线 emotion", "v": "憋屈25% · 爽65% · 暖10%", "note": ""},
            {"label": "人物弧 arcs", "v": "男主 隐忍→张扬 · 反派 步步崩", "note": ""},
            {"label": "伏笔 foreshadow", "v": "9 处 · 全回收", "note": ""},
            {"label": "爽点 payoffs", "v": "打脸17 · 逆袭8 · 升咖6", "note": "爽文密度高"},
            {"label": "人名词典 names", "v": "41 实体冻结", "note": ""},
            {"label": "语域指纹 voice", "v": "快节奏 · 短句 · 金句", "note": ""},
            {"label": "题材 genre", "v": "都市爽文 · 退婚流", "note": ""},
        ],
        "scenes": {"total": 60, "drafted": 60, "peaks": [8, 25, 41, 55], "list": [
            {"n": 8, "type": "DRAMATIZE", "beat": "宴会当众打脸", "status": "pass", "cand": 8, "pk": "达金标"},
            {"n": 18, "type": "SUMMARIZE", "beat": "创业三月速写", "status": "pass", "cand": 2, "pk": "胜源"},
            {"n": 25, "type": "DRAMATIZE", "beat": "收购前东家 · 高点", "status": "pass", "cand": 8, "pk": "达金标"},
            {"n": 41, "type": "DRAMATIZE", "beat": "身份反转", "status": "pass", "cand": 8, "pk": "达金标"},
            {"n": 55, "type": "DRAMATIZE", "beat": "终局清算", "status": "pass", "cand": 6, "pk": "胜源 · 明显"},
        ]},
        "gate": {"mech": [
            {"k": "AI腔密度", "v": "0.9%", "pass": True, "note": "阈 <3%"},
            {"k": "风格 cosine vs 源", "v": "0.82", "pass": True, "note": ""},
            {"k": "注水残留", "v": "1.6%", "pass": True, "note": ""},
            {"k": "语病/人名一致", "v": "100%", "pass": True, "note": "41 实体"},
            {"k": "结构合规", "v": "60章 · 均3520字", "pass": True, "note": "首章交代 ✓"},
            {"k": "逐字重合", "v": "5.3%", "pass": True, "note": "<8%"},
        ], "pk": [
            {"vs": "本书源（下锚）", "verdict": "明显胜", "score": "88% 胜率", "pass": True},
            {"vs": "金标 95（上锚）", "verdict": "达标", "score": "51% 持平", "pass": True},
            {"vs": "标杆 90（近目标）", "verdict": "持平", "score": "49%", "pass": True},
        ], "book": [
            {"k": "弧光收束", "pass": True, "note": ""}, {"k": "节奏曲线", "pass": True, "note": "爽点节拍稳"},
            {"k": "主题统一", "pass": True, "note": ""}, {"k": "结尾落点", "pass": True, "note": ""},
            {"k": "全书连续性审计", "pass": True, "note": "✓"},
        ]},
        "cost": [
            {"k": "Extract", "usd": 0.20, "note": ""}, {"k": "Plan", "usd": 0.35, "note": ""},
            {"k": "Draft", "usd": 0.30, "note": "模式2"}, {"k": "锦标赛+精修", "usd": 1.40, "note": "弱钩补强"},
            {"k": "闸门 PK", "usd": 3.05, "note": "评估大头"},
        ],
        "dims": [{"k": "承重", "v": 65}, {"k": "笔力", "v": 86}, {"k": "开篇代入", "v": 80},
                 {"k": "钩子爽点", "v": 82}, {"k": "节奏", "v": 78}, {"k": "人物", "v": 76}],
        "review": {"total": 76, "version": "gate@v5.1 · spine@on", "mode": "M1 深度长评",
                   "text": "B 源经强化改写反成全批最高分。爽点密度与节奏是强项，打脸节拍干净。承重略优于隐婚。证伪「选强源即选质量」——源档≠成品分。",
                   "snapshot": [{"k": "承重门信号", "v": "0.55"}, {"k": "笔力自评", "v": "80"}, {"k": "PK 金标", "v": "51%"}]},
        "spine": [
            {"group": "人物登记", "items": [
                {"name": "陆沉", "attr": "男主 · 被退婚 · 隐藏富豪", "lock": True},
                {"name": "林氏", "attr": "前未婚妻家 · 反派阵营", "lock": True}]},
            {"group": "关键物品", "items": [{"name": "退婚书", "attr": "开篇导火索", "lock": True}]},
            {"group": "时间线", "items": [{"name": "退婚→收购", "attr": "跨 8 个月", "lock": True}]},
        ],
    },
    "zhaidou": {
        "dna": [
            {"label": "脊柱 spine", "v": "庶女觉醒→宅斗上位→谋得良缘", "note": "5 卷主弧"},
            {"label": "钩子账 hooks", "v": "10 强钩 · 章均 0.8", "note": ""},
            {"label": "情感曲线 emotion", "v": "隐忍40% · 反击45% · 团圆15%", "note": ""},
            {"label": "人物弧 arcs", "v": "女主 怯懦→城府 · 嫡母 由盛转衰", "note": ""},
            {"label": "伏笔 foreshadow", "v": "8 处 · 回收 7", "note": "1 处弱"},
            {"label": "爽点 payoffs", "v": "打脸11 · 智斗9", "note": ""},
            {"label": "人名词典 names", "v": "52 实体冻结", "note": "人物密集"},
            {"label": "语域指纹 voice", "v": "半文半白 · 含蓄", "note": ""},
            {"label": "题材 genre", "v": "古代言情 · 宅斗", "note": ""},
        ],
        "scenes": {"total": 60, "drafted": 60, "peaks": [10, 27, 43, 58], "list": [
            {"n": 10, "type": "DRAMATIZE", "beat": "祠堂对质", "status": "pass", "cand": 6, "pk": "胜源"},
            {"n": 27, "type": "DRAMATIZE", "beat": "识破毒计 · 高点", "status": "pass", "cand": 8, "pk": "临界达标"},
            {"n": 43, "type": "DRAMATIZE", "beat": "扳倒嫡母", "status": "pass", "cand": 8, "pk": "胜源 · 明显"},
            {"n": 50, "type": "SUMMARIZE", "beat": "议亲过场", "status": "pass", "cand": 2, "pk": "胜源"},
            {"n": 58, "type": "DRAMATIZE", "beat": "凤冠加身", "status": "pass", "cand": 6, "pk": "临界"},
        ]},
        "gate": {"mech": [
            {"k": "AI腔密度", "v": "1.1%", "pass": True, "note": "阈 <3%"},
            {"k": "风格 cosine vs 源", "v": "0.79", "pass": True, "note": ""},
            {"k": "注水残留", "v": "2.2%", "pass": True, "note": ""},
            {"k": "语病/人名一致", "v": "98%", "pass": True, "note": "52 实体 · 1 处歧义"},
            {"k": "结构合规", "v": "60章 · 均3460字", "pass": True, "note": "✓"},
            {"k": "逐字重合", "v": "6.0%", "pass": True, "note": "<8%"},
        ], "pk": [
            {"vs": "本书源（下锚）", "verdict": "胜", "score": "74% 胜率", "pass": True},
            {"vs": "金标 95（上锚）", "verdict": "临界", "score": "41%", "pass": True},
            {"vs": "标杆 90（近目标）", "verdict": "偏低", "score": "38%", "pass": True},
        ], "book": [
            {"k": "弧光收束", "pass": True, "note": ""}, {"k": "节奏曲线", "pass": True, "note": "中段稍缓"},
            {"k": "主题统一", "pass": True, "note": ""}, {"k": "结尾落点", "pass": True, "note": ""},
            {"k": "全书连续性审计", "pass": True, "note": "52 实体 · 时间线 ✓"},
        ]},
        "cost": [
            {"k": "Extract", "usd": 0.22, "note": ""}, {"k": "Plan", "usd": 0.32, "note": ""},
            {"k": "Draft", "usd": 0.27, "note": ""}, {"k": "锦标赛+精修", "usd": 0.85, "note": ""},
            {"k": "闸门 PK", "usd": 2.70, "note": ""},
        ],
        "dims": [{"k": "承重", "v": 58}, {"k": "笔力", "v": 82}, {"k": "开篇代入", "v": 70},
                 {"k": "钩子爽点", "v": 72}, {"k": "节奏", "v": 70}, {"k": "人物", "v": 68}],
        "review": {"total": 68, "version": "gate@v5.1 · spine@on", "mode": "M1 深度长评",
                   "text": "低空认证。宅斗智斗线扎实，但人物过多导致中段承重吃紧，承重 58 偏低拖总分。笔力达标。",
                   "snapshot": [{"k": "承重门信号", "v": "0.78（明显虚高）"}, {"k": "笔力自评", "v": "78"}, {"k": "PK 金标", "v": "41%"}]},
        "spine": [
            {"group": "人物登记", "items": [
                {"name": "沈微", "attr": "女主 · 庶女", "lock": True},
                {"name": "沈夫人", "attr": "嫡母 · 反派", "lock": True},
                {"name": "裴砚", "attr": "男主 · 世子", "lock": True}]},
            {"group": "世界观设定", "items": [{"name": "沈府嫡庶制", "attr": "核心冲突场域", "lock": True}]},
            {"group": "时间线", "items": [{"name": "觉醒→议亲", "attr": "跨 2 年", "lock": True}]},
        ],
    },
    "chuanyue": {
        "dna": [
            {"label": "脊柱 spine", "v": "重生回高考年→改命复仇→守护所爱", "note": "5 卷主弧"},
            {"label": "钩子账 hooks", "v": "11 强钩 · 章均 0.85", "note": ""},
            {"label": "情感曲线 emotion", "v": "遗憾30% · 逆转50% · 圆满20%", "note": ""},
            {"label": "人物弧 arcs", "v": "主角 悔恨→笃定", "note": ""},
            {"label": "伏笔 foreshadow", "v": "6 处 · 规划中", "note": ""},
            {"label": "爽点 payoffs", "v": "先知8 · 打脸6", "note": ""},
            {"label": "人名词典 names", "v": "33 实体冻结", "note": ""},
            {"label": "语域指纹 voice", "v": "第一人称 · 回忆体", "note": "代入感关键"},
            {"label": "题材 genre", "v": "穿越重生 · 都市", "note": ""},
        ],
        "scenes": {"total": 60, "drafted": 34, "peaks": [9, 26, 42, 56], "list": [
            {"n": 1, "type": "DRAMATIZE", "beat": "重生睁眼 · 开篇代入", "status": "pass", "cand": 8, "pk": "胜源（铁律B 复核）"},
            {"n": 9, "type": "DRAMATIZE", "beat": "阻止那场车祸 · 高点", "status": "pass", "cand": 8, "pk": "临界达标"},
            {"n": 26, "type": "DRAMATIZE", "beat": "高考逆袭", "status": "running", "cand": 6, "pk": "评估中"},
            {"n": 34, "type": "SUMMARIZE", "beat": "大学过渡", "status": "pending", "cand": 0, "pk": "排队"},
            {"n": 42, "type": "DRAMATIZE", "beat": "商战先手", "status": "pending", "cand": 0, "pk": "排队"},
        ]},
        "gate": {"mech": [
            {"k": "AI腔密度", "v": "1.4%", "pass": True, "note": "已草稿章"},
            {"k": "风格 cosine vs 源", "v": "0.81", "pass": True, "note": ""},
            {"k": "注水残留", "v": "2.8%", "pass": True, "note": ""},
            {"k": "语病/人名一致", "v": "99%", "pass": True, "note": "33 实体"},
            {"k": "结构合规", "v": "34/60 章草稿", "pass": None, "note": "进行中"},
            {"k": "逐字重合", "v": "5.7%", "pass": True, "note": "<8%"},
        ], "pk": [
            {"vs": "本书源（下锚）", "verdict": "胜", "score": "70%（已评章）", "pass": True},
            {"vs": "金标 95（上锚）", "verdict": "未达", "score": "34%", "pass": False},
            {"vs": "标杆 90（近目标）", "verdict": "未评", "score": "—", "pass": None},
        ], "book": [
            {"k": "整本级审计", "pass": None, "note": "待全本草稿完成"},
        ]},
        "cost": [
            {"k": "Extract", "usd": 0.21, "note": ""}, {"k": "Plan", "usd": 0.33, "note": ""},
            {"k": "Draft", "usd": 0.16, "note": "34/60 进行中"},
            {"k": "锦标赛+精修", "usd": 0.42, "note": "部分高点"}, {"k": "闸门 PK", "usd": 0.0, "note": "整本闸门未起"},
        ],
        "dims": [{"k": "承重", "v": 55}, {"k": "笔力", "v": 75}, {"k": "开篇代入", "v": 48},
                 {"k": "钩子爽点", "v": 68}, {"k": "节奏", "v": 64}, {"k": "人物", "v": 62}],
        "review": {"total": 63, "version": "gate@v5.1 · 试评", "mode": "M2 试评（盲）",
                   "text": "human-eval-5 命中铁律 B：穿越·重生开篇代入感弱（48）是主短板，第 1 章已按「重生开篇铁律」复写复核。中段笔力尚可，承重待全本审计。",
                   "snapshot": [{"k": "承重门信号", "v": "0.60"}, {"k": "笔力自评", "v": "72"}, {"k": "PK 金标", "v": "34%"}]},
        "spine": [
            {"group": "人物登记", "items": [
                {"name": "江野", "attr": "主角 · 重生者", "lock": True},
                {"name": "苏念", "attr": "女主 · 待救者", "lock": True}]},
            {"group": "时间线", "items": [
                {"name": "重生锚点", "attr": "高考前 90 天 · 硬约束", "lock": True},
                {"name": "车祸事件", "attr": "第 9 章 · 不可早于", "lock": True}]},
        ],
    },
    "aoshi": {
        "dna": [
            {"label": "脊柱 spine", "v": "废材觉醒→宗门崛起→证道苍穹", "note": "7 卷 · 体量大"},
            {"label": "钩子账 hooks", "v": "14 钩 · 章均 1.0", "note": "源钩偏套路"},
            {"label": "情感曲线 emotion", "v": "热血70% · 悲壮20% · 暧昧10%", "note": ""},
            {"label": "人物弧 arcs", "v": "主角 弱→强（线性 · 缺转折）", "note": "弧光单薄"},
            {"label": "伏笔 foreshadow", "v": "12 处 · 多处断裂", "note": "承重隐患"},
            {"label": "爽点 payoffs", "v": "升级22 · 打脸15", "note": "数值刷屏"},
            {"label": "人名词典 names", "v": "88 实体 · 冲突 6", "note": "设定打架"},
            {"label": "语域指纹 voice", "v": "夸张 · 套话密", "note": "去套话压力大"},
            {"label": "题材 genre", "v": "玄幻 · 升级流", "note": ""},
        ],
        "scenes": {"total": 60, "drafted": 60, "peaks": [14, 30, 46, 59], "list": [
            {"n": 14, "type": "DRAMATIZE", "beat": "宗门大比", "status": "pass", "cand": 8, "pk": "胜源"},
            {"n": 30, "type": "DRAMATIZE", "beat": "灭门复仇 · 高点", "status": "fail", "cand": 8, "pk": "未达金标 · 承重断"},
            {"n": 46, "type": "DRAMATIZE", "beat": "秘境夺宝", "status": "fail", "cand": 8, "pk": "设定冲突"},
            {"n": 52, "type": "SUMMARIZE", "beat": "闭关三年", "status": "pass", "cand": 2, "pk": "胜源"},
            {"n": 59, "type": "DRAMATIZE", "beat": "证道终战", "status": "fail", "cand": 8, "pk": "弧光未收束"},
        ]},
        "gate": {"mech": [
            {"k": "AI腔密度", "v": "2.1%", "pass": True, "note": "阈 <3%"},
            {"k": "风格 cosine vs 源", "v": "0.74", "pass": True, "note": ""},
            {"k": "注水残留", "v": "3.6%", "pass": False, "note": "超阈 · 数值流难压"},
            {"k": "语病/人名一致", "v": "91%", "pass": False, "note": "88 实体 · 6 冲突"},
            {"k": "结构合规", "v": "60章 · 体量压缩损钩", "pass": True, "note": "勉强"},
            {"k": "逐字重合", "v": "7.6%", "pass": True, "note": "临界 <8%"},
        ], "pk": [
            {"vs": "本书源（下锚）", "verdict": "胜", "score": "66% 胜率", "pass": True},
            {"vs": "金标 95（上锚）", "verdict": "明显未达", "score": "22%", "pass": False},
            {"vs": "标杆 90（近目标）", "verdict": "差距大", "score": "19%", "pass": False},
        ], "book": [
            {"k": "弧光收束", "pass": False, "note": "终战未收束"}, {"k": "节奏曲线", "pass": True, "note": ""},
            {"k": "主题统一", "pass": True, "note": ""}, {"k": "结尾落点", "pass": False, "note": "仓促"},
            {"k": "全书连续性审计", "pass": False, "note": "设定冲突6 · 伏笔断裂 · 承重崩"},
        ]},
        "cost": [
            {"k": "Extract", "usd": 0.28, "note": "体量大"}, {"k": "Plan", "usd": 0.45, "note": "7卷压60章"},
            {"k": "Draft", "usd": 0.40, "note": ""}, {"k": "锦标赛+精修", "usd": 2.10, "note": "反复救场"},
            {"k": "闸门 PK", "usd": 3.40, "note": "多轮重评"},
        ],
        "dims": [{"k": "承重", "v": 38}, {"k": "笔力", "v": 70}, {"k": "开篇代入", "v": 52},
                 {"k": "钩子爽点", "v": 60}, {"k": "节奏", "v": 55}, {"k": "人物", "v": 50}],
        "review": {"total": 54, "version": "gate@v5.1 · spine@on", "mode": "M1 深度长评",
                   "text": "全批最低。S 源（pregrade 高）≠ 人类成品分——升级流大体量压成 60 章后伏笔断裂、设定冲突，承重崩至 38，是质量瓶颈的极端样本。模式3 重构仍救不动 → 拒收。",
                   "snapshot": [{"k": "承重门信号", "v": "0.82（严重虚高）"}, {"k": "笔力自评", "v": "76"}, {"k": "PK 金标", "v": "22%"}]},
        "spine": [
            {"group": "人物登记", "items": [
                {"name": "萧战", "attr": "主角 · 废材→帝", "lock": True},
                {"name": "药尘", "attr": "师尊 · 设定冲突", "lock": False}]},
            {"group": "世界观设定", "items": [
                {"name": "境界体系", "attr": "9 大境 · 跨卷数值打架", "lock": False},
                {"name": "秘境规则", "attr": "第30/46章 自相矛盾", "lock": False}]},
            {"group": "时间线", "items": [{"name": "闭关跨度", "attr": "与年龄线冲突", "lock": False}]},
        ],
    },
    "wendao": {
        "dna": [
            {"label": "脊柱 spine", "v": "凡人问道 → 抽取中…", "note": "Extract 进行"},
            {"label": "钩子账 hooks", "v": "识别中", "note": ""},
            {"label": "人名词典 names", "v": "29 实体 · 登记中", "note": ""},
            {"label": "题材 genre", "v": "仙侠 · 修真", "note": "已定档"},
        ],
        "scenes": None, "gate": None, "dims": None, "review": None,
        "cost": [{"k": "Extract", "usd": 0.14, "note": "flash 首读进行"}],
        "spine": [{"group": "人物登记", "items": [{"name": "秦渊", "attr": "主角 · 登记中", "lock": False}]}],
    },
    "xingji": {
        "dna": [
            {"label": "脊柱 spine", "v": "机甲少年→星海征途→守护文明", "note": "弱源 · 钩子稀"},
            {"label": "钩子账 hooks", "v": "6 钩 · 章均 0.4", "note": "偏少 · 需补强"},
            {"label": "情感曲线 emotion", "v": "识别中", "note": ""},
            {"label": "人物弧 arcs", "v": "规划中", "note": ""},
            {"label": "人名词典 names", "v": "45 实体冻结", "note": ""},
            {"label": "语域指纹 voice", "v": "硬科幻 · 术语密", "note": ""},
            {"label": "题材 genre", "v": "科幻 · 机甲", "note": ""},
        ],
        "scenes": {"total": 60, "drafted": 0, "peaks": [], "list": [
            {"n": 1, "type": "DRAMATIZE", "beat": "机甲启动 · 规划中", "status": "pending", "cand": 0, "pk": "未起"},
            {"n": "…", "type": "—", "beat": "outline_60 生成中（pro）", "status": "pending", "cand": 0, "pk": "—"},
        ]},
        "gate": None, "dims": None, "review": None,
        "cost": [{"k": "Extract", "usd": 0.30, "note": "D 弱源 · 多块"}, {"k": "Plan", "usd": 0.18, "note": "规划进行"}],
        "spine": [
            {"group": "人物登记", "items": [{"name": "凌霄", "attr": "主角 · 机师", "lock": True}]},
            {"group": "世界观设定", "items": [{"name": "星历纪元", "attr": "设定登记中", "lock": False}]},
        ],
    },
    "qiandao": {
        "dna": None, "scenes": None, "gate": None, "dims": None, "review": None,
        "cost": [{"k": "Ingest", "usd": 0.14, "note": "flash 清洗 · 唯一开销"}],
        "spine": None,
    },
}


def empty_detail() -> dict:
    """未知本的空详情骨架（全字段 None）。"""
    return {"dna": None, "scenes": None, "gate": None, "dims": None, "review": None,
            "cost": [], "spine": None}
