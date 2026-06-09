# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for per-org knowledge model config (Issue #4451)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.knowledge.org_knowledge_config import (
    DEFAULT_ORG_ID,
    OrgKnowledgeConfig,
    OrgKnowledgeConfigService,
)
from tests.helpers.fake_redis import AsyncSimpleFakeRedis


def _ssot_stub():
    """Return a stub SSOT config exposing the attributes we read."""
    return SimpleNamespace(
        llm=SimpleNamespace(
            default_model="ssot-llm-model",
            embedding_model="ssot-embed-model",
            llamaindex_embedding_provider="ollama",
            llamaindex_llm_model="ssot-llamaindex-model",
            provider="ollama",
        )
    )


@pytest.mark.asyncio
async def test_set_then_get_returns_persisted_config() -> None:
    """A config set via ``set()`` round-trips via ``get()``."""
    svc = OrgKnowledgeConfigService(redis_client=AsyncSimpleFakeRedis())
    cfg = OrgKnowledgeConfig(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        embedding_model="text-embedding-3-small",
        embedding_dimension=1536,
    )
    await svc.set("org-42", cfg)
    loaded = await svc.get("org-42")
    assert loaded is not None
    assert loaded.llm_provider == "openai"
    assert loaded.llm_model == "gpt-4o-mini"
    assert loaded.embedding_model == "text-embedding-3-small"
    assert loaded.embedding_dimension == 1536


@pytest.mark.asyncio
async def test_get_effective_returns_ssot_defaults_when_unset() -> None:
    """With no persisted config, ``get_effective()`` returns SSOT defaults."""
    svc = OrgKnowledgeConfigService(redis_client=AsyncSimpleFakeRedis())
    with patch(
        "autobot_shared.ssot_config.get_config",
        return_value=_ssot_stub(),
    ):
        effective = await svc.get_effective("org-no-config")
    assert effective.llm_provider == "ollama"
    assert effective.llm_model == "ssot-llm-model"
    assert effective.embedding_model == "ssot-embed-model"
    assert effective.embedding_dimension is None


@pytest.mark.asyncio
async def test_get_effective_merges_partial_org_config_over_ssot() -> None:
    """Partial org config fills in SSOT defaults for unset fields only."""
    redis = AsyncSimpleFakeRedis()
    svc = OrgKnowledgeConfigService(redis_client=redis)
    await svc.set(
        "org-partial",
        OrgKnowledgeConfig(embedding_model="custom-embed"),
    )
    with patch(
        "autobot_shared.ssot_config.get_config",
        return_value=_ssot_stub(),
    ):
        effective = await svc.get_effective("org-partial")
    # Set field wins; unset fields fall back to SSOT.
    assert effective.embedding_model == "custom-embed"
    assert effective.llm_model == "ssot-llm-model"
    assert effective.llm_provider == "ollama"


@pytest.mark.asyncio
async def test_default_org_sentinel_used_when_org_id_none() -> None:
    """Calls with org_id=None use the __default__ sentinel key."""
    redis = AsyncSimpleFakeRedis()
    svc = OrgKnowledgeConfigService(redis_client=redis)
    await svc.set(None, OrgKnowledgeConfig(llm_model="default-llm"))
    # Key must exist under the sentinel.
    assert f"org_llm_config:{DEFAULT_ORG_ID}" in redis._store
    loaded = await svc.get(None)
    assert loaded is not None
    assert loaded.llm_model == "default-llm"


@pytest.mark.asyncio
async def test_delete_removes_persisted_config() -> None:
    """``delete()`` clears the key and subsequent ``get()`` returns None."""
    redis = AsyncSimpleFakeRedis()
    svc = OrgKnowledgeConfigService(redis_client=redis)
    await svc.set("org-gone", OrgKnowledgeConfig(llm_model="m"))
    assert await svc.delete("org-gone") is True
    assert await svc.get("org-gone") is None


@pytest.mark.asyncio
async def test_corrupt_payload_returns_none_and_logs() -> None:
    """Non-JSON persisted payloads are ignored rather than raising."""
    redis = AsyncSimpleFakeRedis()
    redis._store["org_llm_config:broken"] = "not-json"
    svc = OrgKnowledgeConfigService(redis_client=redis)
    assert await svc.get("broken") is None


@pytest.mark.asyncio
async def test_set_persists_json_payload_shape() -> None:
    """Persisted blob is valid JSON with the known key set."""
    redis = AsyncSimpleFakeRedis()
    svc = OrgKnowledgeConfigService(redis_client=redis)
    await svc.set(
        "org-1",
        OrgKnowledgeConfig(llm_provider="anthropic", llm_model="claude-3"),
    )
    raw = redis._store["org_llm_config:org-1"]
    payload = json.loads(raw)
    assert set(payload.keys()) == {
        "llm_provider",
        "llm_model",
        "embedding_model",
        "embedding_dimension",
    }
    assert payload["llm_provider"] == "anthropic"
    assert payload["llm_model"] == "claude-3"
