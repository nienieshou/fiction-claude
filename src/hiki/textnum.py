"""中文数字解析 + 章节/卷正则的单一来源(C4)。

背景: 中文数字转换与章节正则曾在多个模块各自实现且分叉——config 的源章正则含「卷」,
mining/slice_validate 复制时漏了「卷」→ 卷分隔的源书被误分块。此模块收口为单源。
纯模块,只依赖 re。

冻结纪律: 改这里的正则会同时影响 ingest/mining/slice/prose_facts/point_repair/prose_continuity,
且交付门信号(章缝/事实表)依赖章节切分 → 改动须跑金标回归网 + 全量。
"""
from __future__ import annotations
import re

NUM = re.compile(r"(\d+(?:\.\d+)?)")
CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
UNIT_MUL = {"万": 1e4, "亿": 1e8, "千": 1e3, "百": 1e2}


def cn_to_num(s: str) -> float | None:
    """中文数字解析(治'四十'被读成4、'二十三'读成2的实测误报)。
    支持 十/百/千/万/亿 复合(四十=40、一万八千=18000、三十万=300000)。"""
    total = 0
    section = 0
    num = 0
    found = False
    for c in s:
        if c in CN_DIGIT:
            num = CN_DIGIT[c]
            found = True
        elif c in CN_UNIT:
            found = True
            unit = CN_UNIT[c]
            if unit >= 10000:
                section = (section + num) * unit
                total += section
                section = 0
            else:
                section += (num or 1) * unit
            num = 0
    return float(total + section + num) if found else None


def num_of(s: str) -> float | None:
    """阿拉伯数字(带万/亿/千/百量纲)优先,回退中文数字。'30万'→300000 与'三十万'一致。"""
    m = NUM.search(s)
    if m:
        v = float(m.group(1))
        tail = s[m.end():m.end() + 1]
        return v * UNIT_MUL.get(tail, 1.0)
    return cn_to_num(s)


# 源文本(.txt 原书)章节头: 阿拉伯+中文数字, 终止符含「卷」(治 mining/slice 漏卷的分叉)。
SOURCE_CH_PATTERN = r"^\s*第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章节卷回]"
SOURCE_CH_RE = re.compile(SOURCE_CH_PATTERN, re.M)
# 多书拼接检测: 只认「第一章/第1章」类首章标记。
FIRST_CH_RE = re.compile(r"第\s*[一1]\s*[章回]")
# 生成 final.md 章头(# 第N章 ...): 切分用。
MD_CH_RE = re.compile(r"^# 第\d+章.*$", re.M)
# 从带 # 的章头抽章号(允许空格)。
CH_NUM_RE = re.compile(r"#\s*第\s*([0-9]+)\s*章")
# 从行内文本(advisory 串如"第3章:...")抽章号, 无 #。
INLINE_CH_NUM_RE = re.compile(r"第(\d+)章")
# 仅检测章头存在。
MD_CH_PREFIX_RE = re.compile(r"^# 第", re.M)
