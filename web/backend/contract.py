"""响应契约（pydantic）。详情/闸门等动态结构用 dict 直返，这里只约束稳定的摘要类。"""
from __future__ import annotations

from pydantic import BaseModel


class Book(BaseModel):
    id: str
    title: str
    src: str
    slug: str
    genre: str
    grade: str
    comp: str
    stage: int
    status: str          # certified | running | rejected
    mode: int
    human: float | None = None
    cost: float = 0
    uploaded: bool = False
    real: bool = False
    reject_reason: str | None = None
    seconds: float | None = None
    calls: int | None = None


class Stats(BaseModel):
    total: int
    certified: int
    rejectRate: str
    avgCost: float
    budgetCap: float
    funnel: dict | None = None
    batch: dict | None = None


class Stage(BaseModel):
    name: str
    cn: str
    sub: str
    model: str
