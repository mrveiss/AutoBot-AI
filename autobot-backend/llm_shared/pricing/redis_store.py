# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Redis-backed pricing cache and override store (GH#6480).

Key format:
  model_pricing:{provider}:{model_id}  →  JSON ModelPricing dict
  model_pricing:refresh_status          →  JSON {provider: {last_refresh_at, success, model_count}}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from llm_shared.pricing.sources import ModelPricing

logger = get_logger(__name__)

_KEY_PREFIX = "model_pricing"
_STATUS_KEY = f"{_KEY_PREFIX}:refresh_status"
_TTL_SECONDS = 60 * 60 * 25  # 25 hours — outlasts the 24-hour refresh cadence


def _model_key(provider: str, model_id: str) -> str:
    return f"{_KEY_PREFIX}:{provider}:{model_id}"


class PricingRedisStore:
    """Async thin wrapper around Redis for pricing data."""

    def __init__(self, database: str = "analytics") -> None:
        self._database = database

    async def _redis(self):
        return await get_async_redis_client(database=self._database)

    async def get(self, provider: str, model_id: str) -> ModelPricing | None:
        try:
            redis = await self._redis()
            if redis is None:
                return None
            raw = await redis.get(_model_key(provider, model_id))
            if raw is None:
                return None
            return ModelPricing.from_dict(json.loads(raw))
        except Exception as exc:
            logger.warning("PricingRedisStore.get failed for %s/%s: %s", provider, model_id, exc)
            return None

    async def get_all_for_provider(self, provider: str) -> dict[str, ModelPricing]:
        try:
            redis = await self._redis()
            if redis is None:
                return {}
            pattern = f"{_KEY_PREFIX}:{provider}:*"
            keys = [k async for k in redis.scan_iter(pattern)]
            if not keys:
                return {}
            values = await redis.mget(*keys)
            result: dict[str, ModelPricing] = {}
            for key, raw in zip(keys, values):
                if raw is None:
                    continue
                try:
                    pricing = ModelPricing.from_dict(json.loads(raw))
                    result[pricing.model_id] = pricing
                except Exception:
                    pass
            return result
        except Exception as exc:
            logger.warning("PricingRedisStore.get_all_for_provider failed for %s: %s", provider, exc)
            return {}

    async def set(self, pricing: ModelPricing) -> bool:
        try:
            redis = await self._redis()
            if redis is None:
                return False
            key = _model_key(pricing.provider, pricing.model_id)
            await redis.setex(key, _TTL_SECONDS, json.dumps(pricing.to_dict()))
            return True
        except Exception as exc:
            logger.warning("PricingRedisStore.set failed for %s/%s: %s", pricing.provider, pricing.model_id, exc)
            return False

    async def set_many(self, pricings: dict[str, ModelPricing]) -> int:
        """Write multiple ModelPricing entries; return count of successful writes."""
        count = 0
        try:
            redis = await self._redis()
            if redis is None:
                return 0
            async with redis.pipeline() as pipe:
                for pricing in pricings.values():
                    key = _model_key(pricing.provider, pricing.model_id)
                    pipe.setex(key, _TTL_SECONDS, json.dumps(pricing.to_dict()))
                # raise_on_error=False collects per-command exceptions in the results list
                # rather than short-circuiting on the first failure. We then count only
                # genuine successes (True / b'OK') — Exception objects in the list are
                # not counted and are logged individually.
                results = await pipe.execute(raise_on_error=False)
            for r in results:
                if isinstance(r, Exception):
                    logger.warning("PricingRedisStore.set_many: pipeline command failed: %s", r)
                elif r is True or r == b"OK":
                    count += 1
        except Exception as exc:
            logger.warning("PricingRedisStore.set_many failed: %s", exc)
        return count

    async def delete(self, provider: str, model_id: str) -> bool:
        try:
            redis = await self._redis()
            if redis is None:
                return False
            deleted = await redis.delete(_model_key(provider, model_id))
            return deleted > 0
        except Exception as exc:
            logger.warning("PricingRedisStore.delete failed for %s/%s: %s", provider, model_id, exc)
            return False

    async def get_refresh_status(self) -> dict:
        try:
            redis = await self._redis()
            if redis is None:
                return {}
            raw = await redis.get(_STATUS_KEY)
            return json.loads(raw) if raw else {}
        except Exception as exc:
            logger.warning("PricingRedisStore.get_refresh_status failed: %s", exc)
            return {}

    async def set_refresh_status(self, provider: str, success: bool, model_count: int) -> None:
        try:
            redis = await self._redis()
            if redis is None:
                return
            raw = await redis.get(_STATUS_KEY)
            status = json.loads(raw) if raw else {}
            status[provider] = {
                "last_refresh_at": datetime.now(tz=timezone.utc).isoformat(),
                "success": success,
                "model_count": model_count,
            }
            await redis.setex(_STATUS_KEY, _TTL_SECONDS, json.dumps(status))
        except Exception as exc:
            logger.warning("PricingRedisStore.set_refresh_status failed: %s", exc)
