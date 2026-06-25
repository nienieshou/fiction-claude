"""DeepSeek 余额代理: 服务器带 key 调 /user/balance,归一后吐前端。key 不进浏览器。
优雅降级——任何失败都返回带 source 标记的 dict,绝不抛(不 500 仪表盘)。"""
from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

from . import paths

load_dotenv(paths.ROOT / ".env")          # 确保 DEEPSEEK_API_KEY 可读(与 hiki.client 一致)

_URL = "https://api.deepseek.com/user/balance"


def normalize_balance(raw: dict) -> dict:
    """DeepSeek 原始 JSON → 前端契约。取首币种 balance_infos[0];结构异常→source:error。"""
    try:
        info = raw["balance_infos"][0]
        return {"available": bool(raw.get("is_available")),
                "currency": info["currency"], "total": info["total_balance"], "source": "live"}
    except (KeyError, IndexError, TypeError):
        return {"available": None, "currency": None, "total": None,
                "source": "error", "detail": "意外的余额响应结构"}


async def fetch_balance() -> dict:
    """取余额: 无 key→no-key(不调外网); 失败/超时/非2xx→error。绝不抛。"""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return {"available": None, "currency": None, "total": None, "source": "no-key"}
    try:
        async with httpx.AsyncClient(timeout=5) as cli:
            r = await cli.get(_URL, headers={"Authorization": f"Bearer {key}"})
        if r.status_code // 100 != 2:
            return {"available": None, "currency": None, "total": None,
                    "source": "error", "detail": f"HTTP {r.status_code}"}
        return normalize_balance(r.json())
    except Exception as e:
        return {"available": None, "currency": None, "total": None,
                "source": "error", "detail": type(e).__name__}
