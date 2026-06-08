# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for LLMApiKeyService (#6590)."""

from __future__ import annotations

import hashlib
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.llm_api_key_service import (
    LLMApiKeyRecord,
    LLMApiKeyService,
    _hash_raw_key,
    _parse_key_id_from_bearer,
)
from tests.fixtures import make_async_redis


def _make_record(**kwargs) -> LLMApiKeyRecord:
    defaults = {
        "key_id": "abcd1234",
        "key_hash": "deadbeef" * 8,
        "team_id": "team-a",
        "label": "test",
        "monthly_budget_usd": 10.0,
        "allowed_models": [],
        "created_at": time.time(),
        "expires_at": None,
        "rotated_at": None,
        "prev_key_hash": None,
        "revoked": False,
    }
    defaults.update(kwargs)
    return LLMApiKeyRecord(**defaults)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_parse_key_id_from_bearer_valid():
    assert _parse_key_id_from_bearer("sk-abcd1234-" + "a" * 32) == "abcd1234"


def test_parse_key_id_from_bearer_invalid():
    assert _parse_key_id_from_bearer("Bearer not-a-key") is None
    assert _parse_key_id_from_bearer("sk-short") is None
    assert _parse_key_id_from_bearer("sk-toolong12-rest") is None


def test_hash_determinism():
    raw = "sk-abcd1234-" + "b" * 32
    assert _hash_raw_key(raw) == _hash_raw_key(raw)
    assert _hash_raw_key(raw) == hashlib.sha256(raw.encode()).hexdigest()


def test_key_format():
    from services.llm_api_key_service import _generate_raw_key

    key = _generate_raw_key("abcd1234")
    assert key.startswith("sk-abcd1234-")
    assert len(key) == len("sk-abcd1234-") + 32


# ---------------------------------------------------------------------------
# model_allowed
# ---------------------------------------------------------------------------


def test_model_allowed_empty_list():
    rec = _make_record(allowed_models=[])
    assert LLMApiKeyService.model_allowed(rec, "gpt-4") is True


def test_model_allowed_exact():
    rec = _make_record(allowed_models=["gpt-4"])
    assert LLMApiKeyService.model_allowed(rec, "gpt-4") is True
    assert LLMApiKeyService.model_allowed(rec, "gpt-3.5") is False


def test_model_allowed_wildcard():
    rec = _make_record(allowed_models=["*"])
    assert LLMApiKeyService.model_allowed(rec, "anything") is True


def test_model_allowed_prefix():
    rec = _make_record(allowed_models=["gpt-4*"])
    assert LLMApiKeyService.model_allowed(rec, "gpt-4-turbo") is True
    assert LLMApiKeyService.model_allowed(rec, "gpt-3") is False


# ---------------------------------------------------------------------------
# issue_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_key():
    mock_redis = AsyncMock()
    mock_pipe = AsyncMock()
    mock_redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_redis.pipeline.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pipe.execute = AsyncMock(return_value=[True, True, True])

    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    svc._redis = mock_redis

    # pipeline() is used as a context manager in issue_key — but actually it's
    # called synchronously; use the non-context-manager approach
    mock_pipe2 = MagicMock()
    mock_pipe2.execute = AsyncMock(return_value=[1, 1, 1])
    mock_redis.pipeline.return_value = mock_pipe2

    record, raw_key = await svc.issue_key(team_id="t1", label="test", monthly_budget_usd=5.0, allowed_models=["gpt-4"])
    assert raw_key.startswith("sk-")
    assert record.team_id == "t1"
    assert record.monthly_budget_usd == 5.0
    assert not record.revoked


# ---------------------------------------------------------------------------
# revoke_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_key_found():
    mock_redis = make_async_redis(exists_returns=1)
    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    svc._redis = mock_redis

    result = await svc.revoke_key("abcd1234")
    assert result is True
    mock_redis.hset.assert_called_once()


@pytest.mark.asyncio
async def test_revoke_key_not_found():
    mock_redis = make_async_redis(exists_returns=0)
    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    svc._redis = mock_redis

    result = await svc.revoke_key("missing")
    assert result is False


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_budget_unlimited():
    rec = _make_record(monthly_budget_usd=0.0)
    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    svc._redis = AsyncMock()

    allowed, remaining = await svc.check_budget(rec)
    assert allowed is True
    assert remaining == -1.0


@pytest.mark.asyncio
async def test_check_budget_within():
    rec = _make_record(monthly_budget_usd=10.0)
    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    svc._redis = make_async_redis(get_returns="3.0")

    allowed, remaining = await svc.check_budget(rec)
    assert allowed is True
    assert abs(remaining - 7.0) < 0.001


@pytest.mark.asyncio
async def test_check_budget_exceeded():
    rec = _make_record(monthly_budget_usd=5.0)
    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    svc._redis = make_async_redis(get_returns="6.0")

    allowed, remaining = await svc.check_budget(rec)
    assert allowed is False
    assert remaining == 0.0


# ---------------------------------------------------------------------------
# authenticate_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_key_valid():
    from services.llm_api_key_service import _generate_raw_key

    raw = _generate_raw_key("abcd1234")
    key_hash = _hash_raw_key(raw)
    rec = _make_record(key_id="abcd1234", key_hash=key_hash)

    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    svc._redis = make_async_redis(hgetall_returns=rec.to_redis_hash())

    result = await svc.authenticate_key(raw)
    assert result is not None
    assert result.key_id == "abcd1234"


@pytest.mark.asyncio
async def test_authenticate_key_wrong_hash():
    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    rec = _make_record(key_id="abcd1234", key_hash="wronghash" * 7 + "wronghas")
    svc._redis = make_async_redis(hgetall_returns=rec.to_redis_hash())

    result = await svc.authenticate_key("sk-abcd1234-" + "z" * 32)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_key_revoked():
    from services.llm_api_key_service import _generate_raw_key

    raw = _generate_raw_key("abcd1234")
    key_hash = _hash_raw_key(raw)
    rec = _make_record(key_id="abcd1234", key_hash=key_hash, revoked=True)

    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    svc._redis = make_async_redis(hgetall_returns=rec.to_redis_hash())

    result = await svc.authenticate_key(raw)
    assert result is None


# ---------------------------------------------------------------------------
# publish_usage_event — Redis error swallowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_usage_event_swallows_error():
    svc = LLMApiKeyService.__new__(LLMApiKeyService)
    mock_redis = make_async_redis()
    mock_redis.xadd = AsyncMock(side_effect=Exception("Redis down"))
    svc._redis = mock_redis

    rec = _make_record()
    # Should not raise
    await svc.publish_usage_event(rec, "gpt-4", 100, 50, 0.01)
