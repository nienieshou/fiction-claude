"""LLM 输出契约校验包装(A3)。cli.complete → _safe_json → schemas.validate; 重试; 终败 None。
返回 dict(有效) | None(retries 次后仍无效)——fail 动作由调用方显式处理(不藏 callback)。"""
from __future__ import annotations
from .gate import _safe_json
from .schemas import validate


async def complete_validated(cli, stage, sys_p, usr, *, schema, retries: int = 3, **complete_kw):
    base_t = complete_kw.pop("temperature", 0.2)
    for t in range(retries):
        raw = await cli.complete(stage, sys_p, usr, temperature=base_t + 0.1 * t, **complete_kw)
        r = _safe_json(raw)
        if (schema(r) if callable(schema) else validate(r, **schema)):
            return r
    return None
