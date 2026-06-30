"""Slice1c: 任务时间戳 —— Book 契约 + dir_to_book + runner JOBS。零 API。"""
from web.backend.contract import Book


def test_book_declares_timestamp_and_bestof_fields():
    b = Book(id="x_full", title="t", src="s", slug="x", genre="g", grade="A", comp="—",
             stage=5, status="certified", mode=0,
             started=1000.0, finished=1060.0, queued=999.0, bestof={"throws": 1})
    d = b.model_dump()
    for k in ("started", "finished", "queued", "bestof"):
        assert k in d, f"Book 未声明 {k} → response_model 会静默过滤"
    assert d["started"] == 1000.0 and d["finished"] == 1060.0
    assert d["queued"] == 999.0 and d["bestof"] == {"throws": 1}
