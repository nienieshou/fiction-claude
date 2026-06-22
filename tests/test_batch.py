"""batch.py 纯函数 + best-of-N 重掷循环。零 API(用 fake run_fn)。"""
import asyncio
from hiki import batch


def test_should_retry_gate_reject():
    # 交付门拒(deliverable False, 非源头致命) → 重掷
    assert batch._should_retry({"deliverable": False}) is True


def test_should_retry_delivered():
    # 已交付 → 不重
    assert batch._should_retry({"deliverable": True}) is False


def test_should_retry_source_fatal():
    # 源头致命(Q/暗黑/min-grade: rejected=True) → 重掷无用,不重
    assert batch._should_retry({"rejected": True}) is False
    assert batch._should_retry({"deliverable": False, "rejected": True}) is False


def test_should_retry_no_signal():
    # 既非 deliverable False 也非 rejected(异常/缺字段) → 不重(保守)
    assert batch._should_retry({}) is False


def test_task_best_of_default():
    t = batch.Task(slug="x", source=__import__("pathlib").Path("a"), out_dir=__import__("pathlib").Path("o"))
    assert t.best_of == 1
