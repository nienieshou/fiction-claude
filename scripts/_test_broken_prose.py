"""broken_prose 验证: 合成用例 + 灵气已知病例(ch31/32 文本损伤)实测。零API。"""
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from hiki.audit import broken_prose
from hiki.prose_facts import split_chapters

# 合成用例
chs = ["他抬起手,正要说话,却发现整个广场都安静了下来,所有人的目光都集中在那道身影上,",
       "狼首异/咔嚓!巨响震彻全场。\n正常段落在这里结束。",
       "正常的一章。对话也正常。"]
hits = broken_prose(chs)
assert any("段尾残句" in h and "第1章" in h for h in hits), hits
assert any("斜杠拼接" in h and "第2章" in h for h in hits), hits
assert not any("第3章" in h for h in hits), hits
print("合成用例 ok:", hits)

# 灵气已知病例
final = Path("output/CPBGX00192灵气复苏：开局无限合成_full/final.md").read_text(encoding="utf-8")
real = broken_prose(split_chapters(final))
print(f"灵气实测检出 {len(real)} 条:")
for h in real[:10]:
    print(" ", h)
