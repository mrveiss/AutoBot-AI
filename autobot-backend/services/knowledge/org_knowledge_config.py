# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Per-org knowledge model configuration (Issue #4451).

Allows each organization to persist its preferred LLM provider, LLM model,
and embedding model so the preference survives session restarts and applies
automatically to all members.

Persistence: Redis (knowledge DB), key ``org_llm_config:{org_id}``.

Single-org deployments: callers that omit ``org_id`` use the sentinel
``__default__`` so the service remains a drop-in for both modes.

Fallback chain (``get_effective``):
    org config → SSOT default (``autobot_shared.ssot_config``)

Downstream consumers (ProviderRegistry fallback chain, LlamaIndex embedding
provider selection) remain unchanged — they see a concrete ``LLMModelConfig``
and apply their own provider-level fallbacks when the named provider is
unavailable.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin

logger = get_logger(__name__)

# Sentinel used for single-org deployments where no explicit org_id is passed.
DEFAULT_ORG_ID = "__default__"

# Redis key prefix for per-org config records.
_KEY_PREFIX = "org_llm_config:"


class OrgKnowledgeConfig(BaseModel):
    """Per-org LLM + embedding model selection.

    All fields are optional — any unset field falls back to the SSOT default
    when resolved via ``OrgKnowledgeConfigService.get_effective()``.
    """

    llm_provider: str | None = Field(
        default=None,
        description="LLM provider name (ollama, openai, anthropic, ...).",
    )
    llm_model: str | None = Field(
        default=None,
        description="LLM model identifier (e.g. 'qwen2.5:7b', 'gpt-4o-mini').",
    )
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model identifier (e.g. 'nomic-embed-text').",
    )
    embedding_dimension: int | None = Field(
        default=None,
        ge=1,
        description="Optional embedding vector dimension override.",
    )


def _key(org_id: str | None) -> str:
    return f"{_KEY_PREFIX}{org_id or DEFAULT_ORG_ID}"


class OrgKnowledgeConfigService(AsyncRedisClientMixin):
    """Persisted per-org knowledge model config with SSOT fallback."""

    _redis_database = "knowledge"

    def __init__(self, redis_client=None) -> None:
        # Injected client (for tests) or lazy-fetched from the knowledge DB via mixin.
        self._redis = redis_client

    async def get(self, org_id: str | None = None) -> OrgKnowledgeConfig | None:
        """Return the persisted config for ``org_id`` or None if unset."""
        redis = await self._get_redis()
        if redis is None:
            logger.warning("Redis unavailable — returning None for org_id=%s", org_id)
            return None
        raw = await redis.get(_key(org_id))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            logger.error(
                "Corrupt org_llm_config for org_id=%s (%s) — ignoring",
                org_id,
                exc,
            )
            return None
        return OrgKnowledgeConfig(**payload)

    async def set(self, org_id: str | None, config: OrgKnowledgeConfig) -> OrgKnowledgeConfig:
        """Persist ``config`` for ``org_id`` and return what was stored."""
        redis = await self._get_redis()
        if redis is None:
            raise RuntimeError("Redis unavailable — cannot persist org model config")
        payload = config.model_dump(exclude_none=False)
        await redis.set(_key(org_id), json.dumps(payload))
        logger.info(
            "Persisted org_llm_config org_id=%s provider=%s llm=%s embed=%s",
            org_id or DEFAULT_ORG_ID,
            config.llm_provider,
            config.llm_model,
            config.embedding_model,
        )
        return config

    async def delete(self, org_id: str | None) -> bool:
        """Remove any persisted config for ``org_id``; return True if deleted."""
        redis = await self._get_redis()
        if redis is None:
            return False
        deleted = await redis.delete(_key(org_id))
        return bool(deleted)

    async def get_effective(self, org_id: str | None = None) -> OrgKnowledgeConfig:
        """Resolve org config, filling missing fields from SSOT defaults.

        The returned model always has every field populated (or at least
        defaulted from SSOT) so callers can treat it as the authoritative
        source for the request.
        """
        org_cfg = await self.get(org_id)

        # Lazy import to avoid circulars at package load time.
        from autobot_shared.ssot_config import get_config as get_ssot_config

        ssot = get_ssot_config()
        default_provider = getattr(ssot.llm, "llamaindex_embedding_provider", None) or getattr(
            ssot.llm, "provider", "ollama"
        )
        default_llm_model = getattr(ssot.llm, "default_model", None) or getattr(ssot.llm, "llamaindex_llm_model", "")
        default_embed_model = getattr(ssot.llm, "embedding_model", "")

        if org_cfg is None:
            return OrgKnowledgeConfig(
                llm_provider=default_provider,
                llm_model=default_llm_model,
                embedding_model=default_embed_model,
                embedding_dimension=None,
            )

        return OrgKnowledgeConfig(
            llm_provider=org_cfg.llm_provider or default_provider,
            llm_model=org_cfg.llm_model or default_llm_model,
            embedding_model=org_cfg.embedding_model or default_embed_model,
            embedding_dimension=org_cfg.embedding_dimension,
        )


# ---------------------------------------------------------------------------
# Process-level singleton accessor
# ---------------------------------------------------------------------------

_singleton: OrgKnowledgeConfigService | None = None


def get_org_knowledge_config_service() -> OrgKnowledgeConfigService:
    """Return the process-level singleton service."""
    global _singleton
    if _singleton is None:
        _singleton = OrgKnowledgeConfigService()
    return _singleton


__all__ = [
    "DEFAULT_ORG_ID",
    "OrgKnowledgeConfig",
    "OrgKnowledgeConfigService",
    "get_org_knowledge_config_service",
]
