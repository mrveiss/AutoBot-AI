# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Virtual LLM API key service (#6590).

Stores key metadata in Redis MAIN database:
  llm:apikey:{key_id}         → Hash  (key metadata)
  llm:apikeys:all             → Set   (all key_ids)
  llm:apikeys:team:{team_id}  → Set   (per-team index)
  llm:spend:key:{key_id}:{YYYY-MM} → String float counter
  llm:usage:stream            → Redis Stream (audit events)
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# Rotation grace period: after a key is rotated the old hash remains valid for
# this many seconds so in-flight requests finish cleanly.
_ROTATION_GRACE_SECS = int(config.llm_key_rotation_grace_secs or 30)

_KEY_TTL_STREAM_SECS = 7 * 24 * 3600  # usage stream events retained 7 days


@dataclass
class LLMApiKeyRecord:
    key_id: str
    key_hash: str  # SHA-256 hex of the raw bearer token
    team_id: str
    label: str
    monthly_budget_usd: float  # 0.0 = unlimited
    allowed_models: List[str]  # empty list = all models allowed
    created_at: float  # Unix timestamp
    expires_at: float | None  # None = no expiry
    rotated_at: float | None  # set when a rotation is pending
    prev_key_hash: str | None  # old hash kept valid during grace period
    revoked: bool

    def to_redis_hash(self) -> Dict[str, str]:
        return {
            "key_id": self.key_id,
            "key_hash": self.key_hash,
            "team_id": self.team_id,
            "label": self.label,
            "monthly_budget_usd": str(self.monthly_budget_usd),
            "allowed_models": ",".join(self.allowed_models),
            "created_at": str(self.created_at),
            "expires_at": str(self.expires_at) if self.expires_at is not None else "",
            "rotated_at": str(self.rotated_at) if self.rotated_at is not None else "",
            "prev_key_hash": self.prev_key_hash or "",
            "revoked": "1" if self.revoked else "0",
        }

    @classmethod
    def from_redis_hash(cls, data: Dict[str, str]) -> "LLMApiKeyRecord":
        return cls(
            key_id=data["key_id"],
            key_hash=data["key_hash"],
            team_id=data.get("team_id", ""),
            label=data.get("label", ""),
            monthly_budget_usd=float(data.get("monthly_budget_usd", "0")),
            allowed_models=[m for m in data.get("allowed_models", "").split(",") if m],
            created_at=float(data.get("created_at", "0")),
            expires_at=float(data["expires_at"]) if data.get("expires_at") else None,
            rotated_at=float(data["rotated_at"]) if data.get("rotated_at") else None,
            prev_key_hash=data.get("prev_key_hash") or None,
            revoked=data.get("revoked", "0") == "1",
        )


def _generate_raw_key(key_id: str) -> str:
    """Return a new raw bearer token: sk-{key_id[:8]}-{32 hex chars}."""
    return f"sk-{key_id[:8]}-{secrets.token_hex(16)}"


def _hash_raw_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _parse_key_id_from_bearer(bearer: str) -> str | None:
    """Extract the 8-char key_id prefix from sk-XXXXXXXX-... format."""
    if not bearer.startswith("sk-"):
        return None
    parts = bearer.split("-")
    # Format: ["sk", "<8hex>", "<32hex>"]
    if len(parts) != 3 or len(parts[1]) != 8:
        return None
    return parts[1]


def _spend_key(key_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"llm:spend:key:{key_id}:{month}"


class LLMApiKeyService:
    """Manages virtual LLM API keys backed by Redis MAIN database."""

    async def _r(self):
        redis = await get_async_redis_client(database="main")
        if redis is None:
            raise RuntimeError("Redis MAIN unavailable")
        return redis

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def issue_key(
        self,
        team_id: str,
        label: str,
        monthly_budget_usd: float = 0.0,
        allowed_models: List[str] | None = None,
        expires_at: float | None = None,
    ) -> tuple[LLMApiKeyRecord, str]:
        """Create a new key. Returns (record, raw_key). raw_key shown once."""
        key_id = secrets.token_hex(4)  # 8 hex chars
        raw_key = _generate_raw_key(key_id)
        key_hash = _hash_raw_key(raw_key)
        now = time.time()
        record = LLMApiKeyRecord(
            key_id=key_id,
            key_hash=key_hash,
            team_id=team_id,
            label=label,
            monthly_budget_usd=monthly_budget_usd,
            allowed_models=allowed_models or [],
            created_at=now,
            expires_at=expires_at,
            rotated_at=None,
            prev_key_hash=None,
            revoked=False,
        )
        redis = await self._r()
        pipe = redis.pipeline()
        pipe.hset(f"llm:apikey:{key_id}", mapping=record.to_redis_hash())
        pipe.sadd("llm:apikeys:all", key_id)
        pipe.sadd(f"llm:apikeys:team:{team_id}", key_id)
        await pipe.execute()
        logger.info("Issued LLM API key %s for team %s label=%r", key_id, team_id, label)
        return record, raw_key

    async def revoke_key(self, key_id: str) -> bool:
        """Mark a key as revoked. Returns True if found."""
        redis = await self._r()
        redis_key = f"llm:apikey:{key_id}"
        exists = await redis.exists(redis_key)
        if not exists:
            return False
        await redis.hset(redis_key, "revoked", "1")
        logger.info("Revoked LLM API key %s", key_id)
        return True

    async def rotate_key(self, key_id: str) -> tuple[LLMApiKeyRecord, str] | None:
        """Issue a new raw key for key_id, keeping old hash valid for grace period."""
        redis = await self._r()
        redis_key = f"llm:apikey:{key_id}"
        data = await redis.hgetall(redis_key)
        if not data:
            return None
        record = LLMApiKeyRecord.from_redis_hash(data)
        if record.revoked:
            return None

        new_raw = _generate_raw_key(key_id)
        new_hash = _hash_raw_key(new_raw)
        record.prev_key_hash = record.key_hash
        record.key_hash = new_hash
        record.rotated_at = time.time()
        await redis.hset(redis_key, mapping=record.to_redis_hash())
        logger.info("Rotated LLM API key %s", key_id)
        return record, new_raw

    async def list_keys(self, team_id: str | None = None) -> List[Dict[str, Any]]:
        """List keys with current month spend."""
        redis = await self._r()
        if team_id:
            key_ids = list(await redis.smembers(f"llm:apikeys:team:{team_id}"))
        else:
            key_ids = list(await redis.smembers("llm:apikeys:all"))

        kid_strs = [kid if isinstance(kid, str) else kid.decode() for kid in key_ids]
        if not kid_strs:
            return []

        # Batch all hgetall + spend reads in a single pipeline round-trip.
        pipe = redis.pipeline()
        for kid_str in kid_strs:
            pipe.hgetall(f"llm:apikey:{kid_str}")
        for kid_str in kid_strs:
            pipe.get(_spend_key(kid_str))
        responses = await pipe.execute()

        n = len(kid_strs)
        hgetalls = responses[:n]
        spends = responses[n:]

        result = []
        for kid_str, data, spend_raw in zip(kid_strs, hgetalls, spends):
            if not data:
                continue
            record = LLMApiKeyRecord.from_redis_hash(data)
            spend = float(spend_raw) if spend_raw else 0.0
            result.append(
                {
                    "key_id": record.key_id,
                    "key_prefix": f"sk-{record.key_id[:8]}-...",
                    "team_id": record.team_id,
                    "label": record.label,
                    "monthly_budget_usd": record.monthly_budget_usd,
                    "spend_usd_this_month": spend,
                    "allowed_models": record.allowed_models,
                    "created_at": record.created_at,
                    "expires_at": record.expires_at,
                    "revoked": record.revoked,
                }
            )
        return result

    # ------------------------------------------------------------------
    # Authentication & enforcement
    # ------------------------------------------------------------------

    async def authenticate_key(self, raw_key: str) -> LLMApiKeyRecord | None:
        """Validate a raw bearer token. Returns record if valid, else None."""
        key_id = _parse_key_id_from_bearer(raw_key)
        if not key_id:
            return None
        redis = await self._r()
        data = await redis.hgetall(f"llm:apikey:{key_id}")
        if not data:
            return None
        record = LLMApiKeyRecord.from_redis_hash(data)
        if record.revoked:
            return None
        # Constant-time comparison against current hash
        candidate = _hash_raw_key(raw_key)
        if secrets.compare_digest(candidate, record.key_hash):
            return record
        # Also accept old hash during grace period
        if (
            record.prev_key_hash
            and record.rotated_at
            and (time.time() - record.rotated_at) < _ROTATION_GRACE_SECS
            and secrets.compare_digest(candidate, record.prev_key_hash)
        ):
            return record
        return None

    async def check_budget(self, record: LLMApiKeyRecord) -> tuple[bool, float]:
        """Return (allowed, remaining_usd). remaining=-1 means unlimited."""
        if record.monthly_budget_usd <= 0:
            return True, -1.0
        redis = await self._r()
        spend_raw = await redis.get(_spend_key(record.key_id))
        spend = float(spend_raw) if spend_raw else 0.0
        remaining = record.monthly_budget_usd - spend
        return remaining > 0, max(remaining, 0.0)

    async def record_spend(self, record: LLMApiKeyRecord, cost_usd: float) -> None:
        """Increment per-key monthly spend counter."""
        if cost_usd <= 0:
            return
        redis = await self._r()
        await redis.incrbyfloat(_spend_key(record.key_id), cost_usd)

    @staticmethod
    def model_allowed(record: LLMApiKeyRecord, model: str) -> bool:
        """Check if model is permitted by the key's allowlist."""
        if not record.allowed_models:
            return True
        for pattern in record.allowed_models:
            if pattern == "*":
                return True
            if model == pattern:
                return True
            if pattern.endswith("*") and model.startswith(pattern[:-1]):
                return True
        return False

    # ------------------------------------------------------------------
    # Usage events
    # ------------------------------------------------------------------

    async def publish_usage_event(
        self,
        record: LLMApiKeyRecord,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
    ) -> None:
        """Publish a usage event to llm:usage:stream. Errors are swallowed."""
        try:
            redis = await self._r()
            event: Dict[str, str] = {
                "key_id": record.key_id,
                "team_id": record.team_id,
                "model": model,
                "prompt_tokens": str(prompt_tokens),
                "completion_tokens": str(completion_tokens),
                "cost_usd": str(cost_usd),
                "ts": str(time.time()),
            }
            await redis.xadd("llm:usage:stream", event, maxlen=10000, approximate=True)
        except Exception as exc:
            logger.warning("Failed to publish LLM usage event: %s", exc)

    # ------------------------------------------------------------------
    # Rotation job
    # ------------------------------------------------------------------

    async def rotate_expired_keys(self) -> int:
        """Revoke keys whose expires_at has passed. Returns count revoked."""
        redis = await self._r()
        now = time.time()
        key_ids = await redis.smembers("llm:apikeys:all")
        revoked_count = 0
        for kid in key_ids:
            kid_str = kid if isinstance(kid, str) else kid.decode()
            data = await redis.hgetall(f"llm:apikey:{kid_str}")
            if not data:
                continue
            record = LLMApiKeyRecord.from_redis_hash(data)
            if record.revoked:
                continue
            if record.expires_at and record.expires_at < now:
                await redis.hset(f"llm:apikey:{kid_str}", "revoked", "1")
                revoked_count += 1
                logger.info("Auto-revoked expired LLM API key %s", kid_str)
        return revoked_count


get_llm_api_key_service = lazy_singleton(LLMApiKeyService)
