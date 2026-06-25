"""DeepSeek async 客户端（A1/A6/A7）。

并发=信号量（pro/flash 分档，对应 API 上限 500/2500）；429 指数退避；
按 config 路由阶段→模型；累计成本。源 prefix 稳定 → DeepSeek 自动 prefix 缓存。
"""
from __future__ import annotations
import asyncio
import os
import random
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError, APIStatusError
from . import config, budget

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

_ROUTING = (config.load("models") or {}).get("routing", {})
_API = {"v4-pro": "deepseek-v4-pro", "v4-flash": "deepseek-v4-flash"}


_warned_stages: set[str] = set()

_FATAL_HINT = {401: "API key 无效", 402: "余额不足,充值后重试", 403: "权限不足"}


def _model_for(stage: str) -> str:
    if stage not in _ROUTING and stage not in _warned_stages:   # D5: typo'd stage 静默降级 flash → 显式告警
        _warned_stages.add(stage)
        import sys
        print(f"⚠ 路由未知阶段 '{stage}' → 默认 v4-flash(检查 config/models.yaml routing 是否拼错)",
              file=sys.stderr)
    return _API[_ROUTING.get(stage, "v4-flash")]


class Client:
    def __init__(self, flash_concurrency: int = 384, pro_concurrency: int = 110):
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY 未设置（检查 .env）")
        self._c = AsyncOpenAI(api_key=key, base_url="https://api.deepseek.com")
        self._sem = {
            "deepseek-v4-pro": asyncio.Semaphore(pro_concurrency),
            "deepseek-v4-flash": asyncio.Semaphore(flash_concurrency),
        }
        self.cost_usd = 0.0
        self.calls = 0

    async def complete(self, stage: str, system: str, user: str, *,
                       json_mode: bool = False, max_tokens: int = 4096,
                       temperature: float = 1.0) -> str:
        model = _model_for(stage)
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                        "messages": [{"role": "system", "content": system},
                                     {"role": "user", "content": user}]}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        async with self._sem[model]:
            for attempt in range(6):
                try:
                    r = await self._c.chat.completions.create(**kwargs)
                    u = r.usage
                    if u is not None:                               # 偶发响应无 usage → 跳过计费，绝不崩整本
                        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
                        self.cost_usd += budget.call_cost_usd(
                            _ROUTING.get(stage, "v4-flash"), u.prompt_tokens, u.completion_tokens, cached)
                    self.calls += 1
                    content = (r.choices[0].message.content or "") if r.choices else ""
                    # A4: 空响应(flash 偶发抽风)当可重试,不静默返回 "" 误导调用方"修好了/无问题"
                    if content.strip() or attempt == 5:
                        return content
                    await asyncio.sleep(min(2 ** attempt, 10) * (0.5 + random.random()))
                except RateLimitError:
                    await asyncio.sleep(min(2 ** attempt, 30) * (0.5 + random.random()))   # 429 指数退避+jitter 防同步重撞
                except APIStatusError as e:                    # 有响应的状态错误(4xx/5xx)
                    if e.status_code in (401, 402, 403):       # 永久性:认证/余额/权限,重试无用→立即致命
                        raise RuntimeError(
                            f"{stage}: API 致命 {e.status_code}（{_FATAL_HINT.get(e.status_code, '不可重试')}）") from e
                    if attempt == 5:                           # 其余(5xx 等)照旧重试
                        raise
                    await asyncio.sleep(min(2 ** attempt, 15) * (0.5 + random.random()))
                except (APIError, APIConnectionError, APITimeoutError):  # 无响应:连接/超时,否则单次闪断 abort 整跑
                    if attempt == 5:
                        raise
                    await asyncio.sleep(min(2 ** attempt, 15) * (0.5 + random.random()))
            raise RuntimeError(f"{stage}: 重试耗尽")

    @property
    def cost_cny(self) -> float:
        return budget.usd_to_cny(self.cost_usd)
