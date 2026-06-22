"""web runner: best-of-N 分类 + 重掷循环。零 API(注入 fake run_fn)。"""
import asyncio
from web.backend import runner


def test_classify_t1_delivered():
    assert runner._classify_bestof([{"deliverable": True}]) == "T1直接交付"


def test_classify_rescued():
    h = [{"deliverable": False}, {"deliverable": True}]
    assert runner._classify_bestof(h) == "重掷救回"


def test_classify_systematic_reject():
    h = [{"deliverable": False}, {"deliverable": False}, {"deliverable": False}]
    assert runner._classify_bestof(h) == "系统性拒(全稿交付门拒)"


def test_classify_source_fatal():
    assert runner._classify_bestof([{"rejected": True, "deliverable": False}]) == "源头致命"


def test_classify_empty():
    assert runner._classify_bestof([]) == "none"
