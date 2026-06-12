"""prose_facts 纯函数自测(零API)。"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")
from hiki.prose_facts import split_chapters, verify_finding

chs = split_chapters("# 《书》\n\n# 第1章 x\n纪老夫人喝了参汤。\n\n# 第2章 y\n纪老夫人已经下葬三年。")
assert len(chs) == 2, chs
f = {"cat": "生死", "ch_a": 1, "quote_a": "纪老夫人喝了参汤", "ch_b": 2, "quote_b": "纪老夫人已经下葬三年"}
assert verify_finding(f, chs)
f2 = dict(f, quote_b="没出现过的引文内容啊")
assert not verify_finding(f2, chs)
f3 = dict(f, ch_b=99)
assert not verify_finding(f3, chs)
f4 = dict(f, quote_a="参汤")            # 归一后<6字 → 不足为证
assert not verify_finding(f4, chs)
print("prose_facts 纯函数自测 ok")
