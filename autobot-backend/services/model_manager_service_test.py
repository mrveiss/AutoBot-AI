# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for ModelManagerService (#3280)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.model_manager_service import (
    _build_model_entry,
    _hints_for_model,
    get_available_models,
    get_model_names,
)

# ---------------------------------------------------------------------------
# _hints_for_model
# ---------------------------------------------------------------------------


def test_hints_for_known_family() -> None:
    hints = _hints_for_model("llama3.2:3b")
    assert "chat" in hints["capabilities"]
    assert hints["context_window"] == 8192


def test_hints_for_openai_gpt4o() -> None:
    hints = _hints_for_model("gpt-4o-mini")
    assert "vision" in hints["capabilities"]
    assert hints["context_window"] == 128000


def test_hints_for_anthropic_claude() -> None:
    hints = _hints_for_model("claude-sonnet-4-6")
    assert hints["context_window"] == 200000


def test_hints_unknown_model_uses_defaults() -> None:
    hints = _hints_for_model("totally-unknown-model:latest")
    assert hints["capabilities"] == ["chat"]
    assert hints["context_window"] == 4096


# ---------------------------------------------------------------------------
# _build_model_entry
# ---------------------------------------------------------------------------


def test_build_model_entry_fields() -> None:
    entry = _build_model_entry("mistral:7b", "ollama", available=True)
    assert entry["name"] == "mistral:7b"
    assert entry["provider"] == "ollama"
    assert entry["available"] is True
    assert "capabilities" in entry
    assert "context_window" in entry


def test_build_model_entry_merges_extra() -> None:
    entry = _build_model_entry("gpt-4o", "openai", available=True, extra={"size": 42})
    assert entry["size"] == 42


# ---------------------------------------------------------------------------
# get_available_models — cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_available_models_cache_hit() -> None:
    cached_payload = {
        "models": [
            {
                "name": "llama3",
                "provider": "ollama",
                "available": True,
                "context_window": 8192,
                "capabilities": ["chat"],
            }
        ],
        "total_count": 1,
        "providers_queried": ["ollama"],
        "providers_errored": [],
    }
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(cached_payload))

    with patch(
        "services.model_manager_service.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        result = await get_available_models()

    assert result["cached"] is True
    assert result["total_count"] == 1
    assert result["models"][0]["name"] == "llama3"


# ---------------------------------------------------------------------------
# get_available_models — cache miss, provider query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_available_models_cache_miss_fetches_providers() -> None:
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()

    mock_provider = MagicMock()
    mock_provider.provider_name = "ollama"
    mock_provider.list_models = AsyncMock(return_value=["llama3.2:3b", "mistral:7b"])
    mock_provider.is_available = AsyncMock(return_value=True)

    mock_registry = MagicMock()
    mock_registry.list_providers.return_value = [{"name": "ollama"}]
    mock_registry._providers = {"ollama": mock_provider}

    with (
        patch(
            "services.model_manager_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ),
        patch(
            "services.model_manager_service._fetch_from_providers",
            new=AsyncMock(
                return_value={
                    "models": [
                        {
                            "name": "llama3.2:3b",
                            "provider": "ollama",
                            "available": True,
                            "context_window": 8192,
                            "capabilities": ["chat"],
                        },
                        {
                            "name": "mistral:7b",
                            "provider": "ollama",
                            "available": True,
                            "context_window": 32768,
                            "capabilities": ["chat", "code"],
                        },
                    ],
                    "total_count": 2,
                    "providers_queried": ["ollama"],
                    "providers_errored": [],
                }
            ),
        ),
    ):
        result = await get_available_models()

    assert result["cached"] is False
    assert result["total_count"] == 2
    mock_redis.setex.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_model_names
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_names_filters_unavailable() -> None:
    cached_payload = {
        "models": [
            {
                "name": "llama3",
                "provider": "ollama",
                "available": True,
                "context_window": 8192,
                "capabilities": ["chat"],
            },
            {
                "name": "gpt-4o",
                "provider": "openai",
                "available": False,
                "context_window": 128000,
                "capabilities": ["chat"],
            },
        ],
        "total_count": 2,
        "providers_queried": ["ollama", "openai"],
        "providers_errored": [],
    }
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(cached_payload))

    with patch(
        "services.model_manager_service.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        names = await get_model_names()

    assert "llama3" in names
    assert "gpt-4o" not in names
