# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis-backed pricing cache and override store (GH#6480).

Key format:
  model_pricing:{provider}:{model_id}  →  JSON ModelPricing dict
  model_pricing:by_model:{model_id}     →  JSON ModelPricing dict, bare model names only (#16229)
  model_pricing:refresh_status          →  JSON {source: {last_refresh_at, last_attempt_at, success, model_count}}
  model_pricing:crosscheck              →  JSON CrossCheckReport of the last refresh (#16229)

``last_refresh_at`` is the last SUCCESSFUL refresh. A failed attempt keeps it, so a failing
source ages into "stale" instead of being re-stamped fresh (#16229).
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
_BY_MODEL_PREFIX = f"{_KEY_PREFIX}:by_model"
_CROSSCHECK_KEY = f"{_KEY_PREFIX}:crosscheck"


def _model_key(provider: str, model_id: str) -> str:
    return f"{_KEY_PREFIX}:{provider}:{model_id}"


def _by_model_key(model_id: str) -> str:
    return f"{_BY_MODEL_PREFIX}:{model_id.lower()}"


def _previous_success(previous: object) -> str | None:
    """The last successful refresh time in a stored status record, if any."""
    if not isinstance(previous, dict):
        return None
    if "last_attempt_at" in previous:  # already in the #16229 shape
        return previous.get("last_refresh_at")
    # Pre-#16229 records stamped every attempt; only a successful one carried a real time.
    return previous.get("last_refresh_at") if previous.get("success") else None


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

    async def get_by_model(self, model_id: str) -> ModelPricing | None:
        """A price by bare model name, whichever catalogue it came from (#16229)."""
        try:
            redis = await self._redis()
            if redis is None:
                return None
            raw = await redis.get(_by_model_key(model_id))
            return ModelPricing.from_dict(json.loads(raw)) if raw else None
        except Exception as exc:
            logger.warning("PricingRedisStore.get_by_model failed for %s: %s", model_id, exc)
            return None

    async def set_many(self, pricings: dict[str, ModelPricing]) -> int:
        """Write multiple ModelPricing entries; return count of successful writes."""
        return await self._setex_many([(_model_key(p.provider, p.model_id), p.to_dict()) for p in pricings.values()])

    async def set_model_index(self, pricings: dict[str, ModelPricing]) -> int:
        """Index prices by bare model name so a lookup needs no provider key (#16229).

        Reseller routes ("bedrock/...") and variants (":free") carry their own
        prices and must not shadow the direct one, so only bare names are
        indexed. The first entry for a name wins; the refresh passes the
        primary catalogue first.
        """
        index: dict[str, dict] = {}
        for pricing in pricings.values():
            name = pricing.model_id.lower()
            if "/" not in name and ":" not in name:
                index.setdefault(name, pricing.to_dict())
        return await self._setex_many([(_by_model_key(name), value) for name, value in index.items()])

    async def _setex_many(self, items: list[tuple[str, dict]]) -> int:
        """Pipeline SETEX of (key, JSON-able value) pairs; return count of successful writes."""
        count = 0
        try:
            redis = await self._redis()
            if redis is None:
                return 0
            async with redis.pipeline() as pipe:
                for key, value in items:
                    pipe.setex(key, _TTL_SECONDS, json.dumps(value))
                # raise_on_error=False collects per-command exceptions in the results list
                # rather than short-circuiting on the first failure. We then count only
                # genuine successes (True / b'OK') — Exception objects in the list are
                # not counted and are logged individually.
                results = await pipe.execute(raise_on_error=False)
            for r in results:
                if isinstance(r, Exception):
                    logger.warning("PricingRedisStore write: pipeline command failed: %s", r)
                elif r is True or r == b"OK":
                    count += 1
        except Exception as exc:
            logger.warning("PricingRedisStore write failed: %s", exc)
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
            now = datetime.now(tz=timezone.utc).isoformat()
            status[provider] = {
                "last_attempt_at": now,
                "last_refresh_at": now if success else _previous_success(status.get(provider)),
                "success": success,
                "model_count": model_count,
            }
            await redis.setex(_STATUS_KEY, _TTL_SECONDS, json.dumps(status))
        except Exception as exc:
            logger.warning("PricingRedisStore.set_refresh_status failed: %s", exc)

    async def retain_refresh_status(self, sources: set[str]) -> None:
        """Drop status records for sources no longer refreshed.

        A retired source's record would otherwise age into "stale" and hold the
        health probe at degraded forever (#16229 retired the baselines).
        """
        try:
            redis = await self._redis()
            if redis is None:
                return
            raw = await redis.get(_STATUS_KEY)
            status = json.loads(raw) if raw else {}
            kept = {name: record for name, record in status.items() if name in sources}
            if kept != status:
                await redis.setex(_STATUS_KEY, _TTL_SECONDS, json.dumps(kept))
        except Exception as exc:
            logger.warning("PricingRedisStore.retain_refresh_status failed: %s", exc)

    async def set_crosscheck(self, report: dict) -> None:
        """Store the last refresh's cross-check report for the admin status view (#16229)."""
        try:
            redis = await self._redis()
            if redis is not None:
                await redis.setex(_CROSSCHECK_KEY, _TTL_SECONDS, json.dumps(report))
        except Exception as exc:
            logger.warning("PricingRedisStore.set_crosscheck failed: %s", exc)

    async def get_crosscheck(self) -> dict:
        try:
            redis = await self._redis()
            if redis is None:
                return {}
            raw = await redis.get(_CROSSCHECK_KEY)
            return json.loads(raw) if raw else {}
        except Exception as exc:
            logger.warning("PricingRedisStore.get_crosscheck failed: %s", exc)
            return {}
