"""一次性: HFL 追加 R8 轮 Fable 四维评分(4本,含锚本新旧双版配对)。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
recs = [
    {"date": "2026-06-11", "scorer": "fable", "round": 8, "title": "星际厨神：美食学院",
     "source": "ZYGWJ02935大佬她美飒全星际", "dims": {"拉力": 79, "笔力": 74, "人": 72, "承重": 56},
     "total": 71.4,
     "comments": "拉力:钩子爽点足但同爽点连打两遍;笔力:对话画面在线,模板句+章内复写段;人:主动有弧,配角工具化;承重:糖心收养重置/夜徒南双身份/封独变恩人/KEVIN死而复现(真)/预告跳空",
     "auto_signals": {"final_consistent": False, "交付门": "预告跳空+fc", "plan握手": "17/17", "章缝": 18, "事实表生死": 1},
     "version": "R8(握手+事实表+残句)"},
    {"date": "2026-06-11", "scorer": "fable", "round": 8, "title": "大佬她美飒全星际(tier1旧版基线)",
     "source": "ZYGWJ02935大佬她美飒全星际", "dims": {"拉力": 78, "笔力": 73, "人": 70, "承重": 60},
     "total": 71.2,
     "comments": "配对锚基线:前中期打脸干净,尾部三章设定连环崩(母亲死因三版本/蒋紫砚双身份/钥匙A三态漂移/第59章人称漏我)。人工历史分73严/79.8宽→Fable≈严尺-2",
     "auto_signals": {"era": "tier1"}, "version": "tier1旧版"},
    {"date": "2026-06-11", "scorer": "fable", "round": 8, "title": "重生八零：我携全家平反了",
     "source": "ZYGXY02032重生在高考：带着糙汉发家致富", "dims": {"拉力": 70, "笔力": 77, "人": 66, "承重": 40},
     "total": 64.8,
     "comments": "笔力全批最高(方言骂战鲜活);承重40:父亲三易其人(榆成波/宋长丰)/子女年龄姓氏漂移/1984年出现手机聊天群(新类:时代锚错位)/源标题泄漏(残句检出)/跨章钩子断头。门拦正确但所引advisory半噪声(郑金花=龙套噪声,二哥=真残留)",
     "auto_signals": {"final_consistent": False, "交付门": "fc", "plan握手": "20/20", "章缝": 24, "残句": 1},
     "version": "R8(握手+事实表+残句)"},
    {"date": "2026-06-11", "scorer": "fable", "round": 8, "title": "拒绝飞升后我守护华夏",
     "source": "DPBXN00507狂医战神", "dims": {"拉力": 78, "笔力": 72, "人": 63, "承重": 46},
     "total": 66.4,
     "comments": "拉力:棺材贺寿有记忆度但高潮跳切;人:全知全胜无代价,弧靠结尾宣言;承重:白珑/杜门双死人复活(评审实证,事实表3/3真阳性)/同章自相矛盾(43口全灭vs没死人)/境界倒退元婴→化气/谱系三易/地名混用",
     "auto_signals": {"final_consistent": True, "交付门": "维14死人复活", "plan握手": "14/14", "章缝": 15, "事实表生死": 2},
     "version": "R8(握手+事实表+残句)"},
]
with open("assets/hfl.jsonl", "a", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
lines = [json.loads(ln) for ln in open("assets/hfl.jsonl", encoding="utf-8") if ln.strip()]
print(f"ok 共{len(lines)}行")
