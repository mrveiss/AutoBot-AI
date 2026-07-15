# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for get_fallback_status pipeline batching — issue #10808.

Verifies that the N+1 fix in api/llm_providers.py correctly batches all Redis
GETs into a single pipeline.execute() instead of one redis_client.get() per key.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from api.llm_providers import get_fallback_status

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_redis_scan(scan_pages, pipeline_values):
    """Return (redis_mock, pipe_mock) configured for scan + pipeline tests.

    Args:
        scan_pages: list of (cursor, [keys]) tuples — scan().side_effect.
        pipeline_values: list returned by pipe.execute().
    """
    redis = MagicMock()
    redis.scan.side_effect = scan_pages

    pipe = MagicMock()
    pipe.get = MagicMock()
    pipe.execute = MagicMock(return_value=pipeline_values)
    redis.pipeline.return_value = pipe

    return redis, pipe


def _body(result) -> dict:
    """Decode JSONResponse.body bytes to a dict."""
    return json.loads(result.body)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_status_pipeline_batches_gets():
    """One pipeline.execute() for N keys — not N separate get() calls (#10808).

    The old code called redis_client.get(key) inside the scan loop (one round-trip
    per key). The fixed code collects all keys first, then issues a single
    pipeline.execute() for all GETs.
    """
    events = [
        {"model": "gpt-4", "fallback": "claude-3"},
        {"model": "llama3", "fallback": "gpt-4o"},
        {"model": "claude-3", "fallback": "gpt-4"},
    ]
    raw = [json.dumps(e).encode() for e in events]

    # Two-page scan: cursor=5 after the first call, cursor=0 (exhausted) after second
    keys_p1 = [b"llm:fallback:active:a", b"llm:fallback:active:b"]
    keys_p2 = [b"llm:fallback:active:c"]
    scan_pages = [(5, keys_p1), (0, keys_p2)]

    fake_redis, fake_pipe = _make_sync_redis_scan(scan_pages, raw)
    mock_manager = MagicMock()
    mock_manager.list_chains.return_value = {}

    with (
        patch("api.llm_providers.get_redis_client", return_value=fake_redis),
        patch("api.llm_providers.get_fallback_chain_manager", return_value=mock_manager),
    ):
        result = await get_fallback_status(
            current_user={"user_id": "admin"},
            admin_check=True,
        )

    # Pipeline created exactly once for all collected keys
    fake_redis.pipeline.assert_called_once()
    # Exactly one execute() for all 3 keys (not 3 separate round-trips)
    assert fake_pipe.execute.call_count == 1, f"Expected 1 pipeline.execute() call, got {fake_pipe.execute.call_count}"
    # pipe.get queued once per key
    assert fake_pipe.get.call_count == 3
    # redis.get never called directly (confirms old N+1 pattern is gone)
    fake_redis.get.assert_not_called()

    body = _body(result)
    assert len(body["active_fallbacks"]) == 3


@pytest.mark.asyncio
async def test_fallback_status_empty_scan_skips_pipeline():
    """Zero keys: no pipeline created, empty active_fallbacks returned (#10808)."""
    fake_redis, fake_pipe = _make_sync_redis_scan([(0, [])], [])
    mock_manager = MagicMock()
    mock_manager.list_chains.return_value = {}

    with (
        patch("api.llm_providers.get_redis_client", return_value=fake_redis),
        patch("api.llm_providers.get_fallback_chain_manager", return_value=mock_manager),
    ):
        result = await get_fallback_status(
            current_user={"user_id": "admin"},
            admin_check=True,
        )

    fake_redis.pipeline.assert_not_called()
    body = _body(result)
    assert body["active_fallbacks"] == []


@pytest.mark.asyncio
async def test_fallback_status_malformed_json_skips_key():
    """Malformed JSON for one key logs a warning but other events still returned (#10808)."""
    raw = [b"not-json", json.dumps({"model": "gpt-4", "fallback": "claude"}).encode()]
    fake_redis, fake_pipe = _make_sync_redis_scan(
        [(0, [b"llm:fallback:active:bad", b"llm:fallback:active:good"])],
        raw,
    )
    mock_manager = MagicMock()
    mock_manager.list_chains.return_value = {}

    with (
        patch("api.llm_providers.get_redis_client", return_value=fake_redis),
        patch("api.llm_providers.get_fallback_chain_manager", return_value=mock_manager),
    ):
        result = await get_fallback_status(
            current_user={"user_id": "admin"},
            admin_check=True,
        )

    body = _body(result)
    # Only the valid event survives; malformed key is skipped
    assert len(body["active_fallbacks"]) == 1
    assert body["active_fallbacks"][0]["model"] == "gpt-4"
    # Pipeline still ran once (batching not affected by per-key parse errors)
    assert fake_pipe.execute.call_count == 1
