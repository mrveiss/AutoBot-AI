# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for LLM response caching via cache_response decorator (Issue #3273).

Verifies that:
- JSONResponse objects are correctly serialised into Redis-storable dicts.
- Cache hits reconstruct a valid JSONResponse with the original body/status.
- Error-status JSONResponse objects (4xx/5xx) are not cached.
- Plain-dict responses continue to be cached as before.
- _record_cache_hit / _record_cache_miss helpers do not raise when Prometheus
  is unavailable.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import JSONResponse

from utils.advanced_cache_manager import (
    _JSON_RESPONSE_ENVELOPE,
    SimpleCacheManager,
    _deserialise_cached_entry,
    _record_cache_hit,
    _record_cache_miss,
    _serialise_response,
)

# ---------------------------------------------------------------------------
# _serialise_response
# ---------------------------------------------------------------------------


class TestSerialiseResponse:
    def test_json_response_200_is_serialised(self):
        resp = JSONResponse(content={"model": "llama3"}, status_code=200)
        result = _serialise_response(resp)
        assert result is not None
        assert result[_JSON_RESPONSE_ENVELOPE] is True
        assert result["status_code"] == 200
        assert json.loads(result["body"]) == {"model": "llama3"}

    def test_json_response_4xx_returns_none(self):
        resp = JSONResponse(content={"detail": "not found"}, status_code=404)
        assert _serialise_response(resp) is None

    def test_json_response_5xx_returns_none(self):
        resp = JSONResponse(content={"error": "oops"}, status_code=500)
        assert _serialise_response(resp) is None

    def test_dict_response_is_passed_through(self):
        data = {"models": ["llama3"], "total_count": 1}
        result = _serialise_response(data)
        assert result == data

    def test_dict_with_error_key_returns_none(self):
        assert _serialise_response({"error": "bad"}) is None

    def test_dict_with_status_error_returns_none(self):
        assert _serialise_response({"status": "error"}) is None

    def test_empty_dict_returns_none(self):
        assert _serialise_response({}) is None

    def test_non_dict_non_response_returns_none(self):
        assert _serialise_response("plain string") is None
        assert _serialise_response(42) is None
        assert _serialise_response(None) is None


# ---------------------------------------------------------------------------
# _deserialise_cached_entry
# ---------------------------------------------------------------------------


class TestDeserialiseResponse:
    def test_envelope_dict_reconstructs_json_response(self):
        envelope = {
            _JSON_RESPONSE_ENVELOPE: True,
            "status_code": 200,
            "body": json.dumps({"status": "connected", "model": "llama3"}),
        }
        result = _deserialise_cached_entry(envelope)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 200
        body = json.loads(result.body.decode("utf-8"))
        assert body == {"status": "connected", "model": "llama3"}

    def test_plain_dict_returned_unchanged(self):
        data = {"models": ["llama3"], "total_count": 1}
        assert _deserialise_cached_entry(data) == data

    def test_malformed_envelope_body_returns_none(self):
        bad_envelope = {
            _JSON_RESPONSE_ENVELOPE: True,
            "status_code": 200,
            "body": "not-valid-json{{",
        }
        result = _deserialise_cached_entry(bad_envelope)
        assert result is None


# ---------------------------------------------------------------------------
# SimpleCacheManager._is_cacheable_response
# ---------------------------------------------------------------------------


class TestIsCacheableResponse:
    def test_json_response_2xx_is_cacheable(self):
        resp = JSONResponse(content={"ok": True}, status_code=200)
        assert SimpleCacheManager._is_cacheable_response(resp) is True

    def test_json_response_4xx_is_not_cacheable(self):
        resp = JSONResponse(content={"detail": "err"}, status_code=400)
        assert SimpleCacheManager._is_cacheable_response(resp) is False

    def test_dict_ok_is_cacheable(self):
        assert SimpleCacheManager._is_cacheable_response({"key": "val"}) is True

    def test_dict_error_is_not_cacheable(self):
        assert SimpleCacheManager._is_cacheable_response({"error": "x"}) is False

    def test_string_is_not_cacheable(self):
        assert SimpleCacheManager._is_cacheable_response("text") is False


# ---------------------------------------------------------------------------
# cache_response decorator — integration with SimpleCacheManager
# ---------------------------------------------------------------------------


class TestCacheResponseDecorator:
    @pytest.mark.asyncio
    async def test_cache_miss_then_hit_for_json_response(self):
        """Second call returns cached JSONResponse without calling the function."""
        manager = SimpleCacheManager()

        stored: dict = {}

        async def fake_get(key):
            return stored.get(key)

        async def fake_set(key, value, ttl=None):
            stored[key] = value

        manager.get = fake_get
        manager.set = fake_set

        call_count = 0

        @manager.cache_response(cache_key="test_endpoint", ttl=60)
        async def endpoint():
            nonlocal call_count
            call_count += 1
            return JSONResponse(content={"model": "llama3"}, status_code=200)

        first = await endpoint()
        assert call_count == 1
        assert isinstance(first, JSONResponse)
        assert json.loads(first.body) == {"model": "llama3"}

        second = await endpoint()
        # Function body must NOT be called again
        assert call_count == 1
        assert isinstance(second, JSONResponse)
        assert json.loads(second.body) == {"model": "llama3"}

    @pytest.mark.asyncio
    async def test_error_response_not_cached(self):
        """JSONResponse with 4xx status must never be stored."""
        manager = SimpleCacheManager()
        set_called = False

        async def fake_get(key):
            return None

        async def fake_set(key, value, ttl=None):
            nonlocal set_called
            set_called = True

        manager.get = fake_get
        manager.set = fake_set

        @manager.cache_response(cache_key="test_error", ttl=60)
        async def error_endpoint():
            return JSONResponse(content={"detail": "not found"}, status_code=404)

        result = await error_endpoint()
        assert result.status_code == 404
        assert set_called is False


# ---------------------------------------------------------------------------
# Prometheus helpers — must be silent when metrics manager is unavailable
# ---------------------------------------------------------------------------


class TestPrometheusHelpers:
    def test_record_cache_hit_does_not_raise_when_import_fails(self):
        with patch(
            "monitoring.prometheus_metrics.get_metrics_manager",
            side_effect=ImportError("no prometheus"),
        ):
            # Should silently pass because _record_cache_hit catches all exceptions
            _record_cache_hit("some_key")

    def test_record_cache_miss_does_not_raise_when_import_fails(self):
        with patch(
            "monitoring.prometheus_metrics.get_metrics_manager",
            side_effect=ImportError("no prometheus"),
        ):
            _record_cache_miss("some_key")

    def test_record_cache_hit_calls_metrics_manager(self):
        mock_mgr = MagicMock()
        with patch(
            "monitoring.prometheus_metrics.get_metrics_manager",
            return_value=mock_mgr,
        ):
            _record_cache_hit("llm_models")
            mock_mgr.record_llm_response_cache_hit.assert_called_once_with(endpoint="llm_models")

    def test_record_cache_miss_calls_metrics_manager(self):
        mock_mgr = MagicMock()
        with patch(
            "monitoring.prometheus_metrics.get_metrics_manager",
            return_value=mock_mgr,
        ):
            _record_cache_miss("llm_models")
            mock_mgr.record_llm_response_cache_miss.assert_called_once_with(endpoint="llm_models")
