"""成本预算（NFR-Cost / A7）。从 models.yaml 计价，估单本/各环节成本，盯 ¥50 上限。"""
from __future__ import annotations
from . import config

CNY_PER_USD = 7.2
_MODELS = (config.load("models") or {}).get("models", {})
_CAP = (config.load("pipeline") or {}).get("budget", {}).get("per_book_cny_cap", 50.0)

# 无 yaml 时的内置兜底价（USD/M tokens）
_FALLBACK = {
    "v4-pro": {"price_in": 0.435, "price_out": 0.870, "cache_in": 0.003625},
    "v4-flash": {"price_in": 0.140, "price_out": 0.280, "cache_in": 0.002800},
}


def _price(model: str) -> dict:
    return _MODELS.get(model) or _FALLBACK[model]


def call_cost_usd(model: str, tok_in: int, tok_out: int, cached_in: int = 0) -> float:
    """单次调用成本(USD)。cached_in 走缓存价（近免费）。"""
    p = _price(model)
    fresh_in = max(0, tok_in - cached_in)
    return (fresh_in * p["price_in"] + cached_in * p["cache_in"]
            + tok_out * p["price_out"]) / 1_000_000


def usd_to_cny(usd: float) -> float:
    return round(usd * CNY_PER_USD, 2)


def within_cap(spent_usd: float) -> bool:
    return usd_to_cny(spent_usd) <= _CAP


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # 粗估单本（缓存源场景）：见 final spec §10
    src_in = 1_000_000
    draft_out = 300_000          # 60ch×3500字≈300k tokens 一份草稿
    extract = call_cost_usd("v4-flash", src_in, 100_000)
    draft = call_cost_usd("v4-pro", 30_000, draft_out, cached_in=28_000)
    print(f"extract≈¥{usd_to_cny(extract)}  draft1≈¥{usd_to_cny(draft)}  cap=¥{_CAP}")
