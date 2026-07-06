# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for issue #10849: AnthropicProvider routes outbound sends through
AutoBotClaudeAPIAdapter's pre-send optimization pipeline.

Tests are split into two tiers:
  - Tier 1 (always run): adapter-level methods (optimize_for_send,
    record_send_result) and rate-limit dict-truthiness fix — no runtime deps
    beyond the autobot-backend package.
  - Tier 2 (skipped unless anthropic SDK installed): AnthropicProvider
    integration — imported via pytest.importorskip so the suite still green
    when anthropic is absent.

Verifies:
  - optimize_for_send is called when adapter is present and initialized
  - record_send_result is called after a successful send
  - record_send_result is called with success=False after an error
  - everything is skipped (fail-safe) when adapter is absent or not initialized
  - stream_completion calls optimize_for_send before streaming
  - _check_and_apply_rate_limit correctly reads can_proceed from dict result
"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs for packages that are always optional in the test environment.
# We install these before any module import that transitively requires them.
# ---------------------------------------------------------------------------


def _ensure_stubs() -> None:
    if "xxhash" not in sys.modules:
        xh = types.ModuleType("xxhash")
        xh.xxh64 = MagicMock(return_value=MagicMock(hexdigest=MagicMock(return_value="0" * 16)))
        sys.modules["xxhash"] = xh


_ensure_stubs()


# ---------------------------------------------------------------------------
# Tier 1 — adapter-level tests (no anthropic SDK required)
# ---------------------------------------------------------------------------


class TestAdapterNewMethods:
    """Unit tests for the two new AutoBotClaudeAPIAdapter methods (#10849)."""

    def setup_method(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        AutoBotClaudeAPIAdapter.reset_instance()

    def teardown_method(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        AutoBotClaudeAPIAdapter.reset_instance()

    @pytest.mark.asyncio
    async def test_optimize_for_send_returns_optimized_content(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        mock_manager = MagicMock()
        mock_manager.is_running = True
        mock_manager._increment_metric = AsyncMock()
        mock_manager._check_and_apply_rate_limit = AsyncMock(return_value=True)
        mock_manager._optimize_payload_if_enabled = AsyncMock(return_value="optimized content")
        mock_manager.rate_limiter = None
        adapter.manager = mock_manager
        adapter._initialized = True

        result = await adapter.optimize_for_send("original content", context_type="chat")
        assert result == "optimized content"
        mock_manager._optimize_payload_if_enabled.assert_awaited_once_with("original content")

    @pytest.mark.asyncio
    async def test_optimize_for_send_fail_safe_on_rate_limit(self) -> None:
        """When rate-limited and no graceful degradation, returns original content."""
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        mock_manager = MagicMock()
        mock_manager.is_running = True
        mock_manager._increment_metric = AsyncMock()
        mock_manager._check_and_apply_rate_limit = AsyncMock(return_value=False)
        mock_manager.degradation_manager = None
        adapter.manager = mock_manager
        adapter._initialized = True

        result = await adapter.optimize_for_send("original", context_type="general")
        assert result == "original"

    @pytest.mark.asyncio
    async def test_optimize_for_send_noop_when_manager_absent(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        adapter.manager = None
        adapter._initialized = True

        result = await adapter.optimize_for_send("content", context_type="chat")
        assert result == "content"

    @pytest.mark.asyncio
    async def test_optimize_for_send_noop_when_manager_not_running(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        mock_manager = MagicMock()
        mock_manager.is_running = False
        adapter.manager = mock_manager
        adapter._initialized = True

        result = await adapter.optimize_for_send("content", context_type="chat")
        assert result == "content"

    @pytest.mark.asyncio
    async def test_record_send_result_increments_individual_on_success(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        mock_manager = MagicMock()
        mock_manager.is_running = True
        mock_manager._increment_metric = AsyncMock()
        mock_manager._update_response_time_metric = AsyncMock()
        mock_manager.pattern_analyzer = None
        adapter.manager = mock_manager
        adapter._initialized = True

        await adapter.record_send_result(
            context_type="chat",
            content_len=100,
            response_time=0.5,
            success=True,
        )
        mock_manager._increment_metric.assert_awaited_once_with("individual_requests")
        mock_manager._update_response_time_metric.assert_awaited_once_with(0.5)

    @pytest.mark.asyncio
    async def test_record_send_result_increments_failed_on_error(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        mock_manager = MagicMock()
        mock_manager.is_running = True
        mock_manager._increment_metric = AsyncMock()
        mock_manager._update_response_time_metric = AsyncMock()
        mock_manager.pattern_analyzer = None
        adapter.manager = mock_manager
        adapter._initialized = True

        await adapter.record_send_result(
            context_type="chat",
            content_len=50,
            response_time=1.0,
            success=False,
            error_message="timeout",
        )
        mock_manager._increment_metric.assert_awaited_once_with("failed_requests")
        mock_manager._update_response_time_metric.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_record_send_result_noop_when_manager_absent(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        adapter.manager = None
        adapter._initialized = True

        # Must not raise
        await adapter.record_send_result(
            context_type="chat",
            content_len=10,
            response_time=0.1,
            success=True,
        )

    @pytest.mark.asyncio
    async def test_record_send_result_calls_pattern_analyzer(self) -> None:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        mock_manager = MagicMock()
        mock_manager.is_running = True
        mock_manager._increment_metric = AsyncMock()
        mock_manager._update_response_time_metric = AsyncMock()
        mock_pattern = MagicMock()
        mock_pattern.record_tool_call = MagicMock()
        mock_manager.pattern_analyzer = mock_pattern
        adapter.manager = mock_manager
        adapter._initialized = True

        await adapter.record_send_result(
            context_type="general",
            content_len=200,
            response_time=1.2,
            success=True,
        )
        mock_pattern.record_tool_call.assert_called_once()
        call_kw = mock_pattern.record_tool_call.call_args.kwargs
        assert call_kw["tool_name"] == "general"
        assert call_kw["success"] is True


# ---------------------------------------------------------------------------
# Rate-limit dict-truthiness fix (#10849)
# ---------------------------------------------------------------------------


class TestRateLimitDictHandling:
    """_check_and_apply_rate_limit must honour the can_proceed key in a dict result."""

    @pytest.mark.asyncio
    async def test_dict_can_proceed_true_allows_request(self) -> None:
        from utils.claude_api_integration import ClaudeAPIBatchManager, ClaudeAPIConfig, OptimizationMetrics

        with patch("utils.graceful_degradation.Path.mkdir"):
            mgr = ClaudeAPIBatchManager(ClaudeAPIConfig(enable_rate_limiting=True))
        mgr.rate_limiter = MagicMock()
        mgr.rate_limiter.can_make_request = MagicMock(return_value={"can_proceed": True})
        mgr._lock = asyncio.Lock()
        mgr._metrics = OptimizationMetrics()

        result = await mgr._check_and_apply_rate_limit()
        assert result is True

    @pytest.mark.asyncio
    async def test_dict_can_proceed_false_blocks_request(self) -> None:
        from utils.claude_api_integration import ClaudeAPIBatchManager, ClaudeAPIConfig, OptimizationMetrics

        with patch("utils.graceful_degradation.Path.mkdir"):
            mgr = ClaudeAPIBatchManager(ClaudeAPIConfig(enable_rate_limiting=True))
        mgr.rate_limiter = MagicMock()
        mgr.rate_limiter.can_make_request = MagicMock(return_value={"can_proceed": False})
        mgr._lock = asyncio.Lock()
        mgr._metrics = OptimizationMetrics()

        result = await mgr._check_and_apply_rate_limit()
        assert result is False

    @pytest.mark.asyncio
    async def test_bool_true_allows_request(self) -> None:
        from utils.claude_api_integration import ClaudeAPIBatchManager, ClaudeAPIConfig, OptimizationMetrics

        with patch("utils.graceful_degradation.Path.mkdir"):
            mgr = ClaudeAPIBatchManager(ClaudeAPIConfig(enable_rate_limiting=True))
        mgr.rate_limiter = MagicMock()
        mgr.rate_limiter.can_make_request = MagicMock(return_value=True)
        mgr._lock = asyncio.Lock()
        mgr._metrics = OptimizationMetrics()

        result = await mgr._check_and_apply_rate_limit()
        assert result is True

    @pytest.mark.asyncio
    async def test_bool_false_blocks_request(self) -> None:
        from utils.claude_api_integration import ClaudeAPIBatchManager, ClaudeAPIConfig, OptimizationMetrics

        with patch("utils.graceful_degradation.Path.mkdir"):
            mgr = ClaudeAPIBatchManager(ClaudeAPIConfig(enable_rate_limiting=True))
        mgr.rate_limiter = MagicMock()
        mgr.rate_limiter.can_make_request = MagicMock(return_value=False)
        mgr._lock = asyncio.Lock()
        mgr._metrics = OptimizationMetrics()

        result = await mgr._check_and_apply_rate_limit()
        assert result is False


# ---------------------------------------------------------------------------
# Tier 2 — AnthropicProvider integration (skipped if llm_shared not importable)
# ---------------------------------------------------------------------------

# Inject the anthropic SDK stub before attempting the provider import so that
# the import itself succeeds even in the minimal test environment.
if "anthropic" not in sys.modules:
    _anthr_stub = types.ModuleType("anthropic")
    _anthr_stub.AsyncAnthropic = MagicMock
    sys.modules["anthropic"] = _anthr_stub

try:
    from llm_shared.providers.anthropic import AnthropicProvider as _AnthropicProvider  # noqa: E402
    from llm_shared.providers.anthropic import _get_adapter_sync as _get_adapter_sync_fn

    _ANTHROPIC_PROVIDER_AVAILABLE = True
except Exception:
    _AnthropicProvider = None  # type: ignore[assignment,misc]
    _get_adapter_sync_fn = None  # type: ignore[assignment]
    _ANTHROPIC_PROVIDER_AVAILABLE = False

_skip_no_provider = pytest.mark.skipif(
    not _ANTHROPIC_PROVIDER_AVAILABLE,
    reason="llm_shared.providers.anthropic not importable in this environment",
)


def _make_request(**kwargs):
    from llm_shared.models import LLMRequest

    defaults = dict(
        messages=[{"role": "user", "content": "Hello"}],
        model_name="claude-sonnet-4-6-20251001",
    )
    defaults.update(kwargs)
    return LLMRequest(**defaults)


def _make_sdk_response(text: str = "pong") -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.model = "claude-sonnet-4-6-20251001"
    resp.stop_reason = "end_turn"
    resp.usage = MagicMock(input_tokens=10, output_tokens=5, output_tokens_details=None)
    return resp


def _make_initialized_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.is_initialized = True
    adapter.optimize_for_send = AsyncMock(return_value="Hello")
    adapter.record_send_result = AsyncMock()
    return adapter


@_skip_no_provider
class TestAnthropicProviderAdapterWiring:
    """AnthropicProvider calls adapter hooks when adapter is present."""

    def _make_provider(self):
        return _AnthropicProvider(settings={"api_key": "test-key"})

    @pytest.mark.asyncio
    async def test_optimize_for_send_called_when_adapter_present(self) -> None:
        provider = self._make_provider()
        sdk_resp = _make_sdk_response("response text")
        mock_adapter = _make_initialized_adapter()

        with (
            patch("llm_shared.providers.anthropic._get_adapter_sync", return_value=mock_adapter),
            patch.object(provider, "_ensure_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=sdk_resp)
            mock_client_fn.return_value = mock_client

            req = _make_request()
            await provider._chat_completion_impl(req)

        mock_adapter.optimize_for_send.assert_awaited_once()
        call_kwargs = mock_adapter.optimize_for_send.call_args.kwargs
        assert call_kwargs["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_record_send_result_called_on_success(self) -> None:
        provider = self._make_provider()
        sdk_resp = _make_sdk_response("ok")
        mock_adapter = _make_initialized_adapter()

        with (
            patch("llm_shared.providers.anthropic._get_adapter_sync", return_value=mock_adapter),
            patch.object(provider, "_ensure_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=sdk_resp)
            mock_client_fn.return_value = mock_client

            await provider._chat_completion_impl(_make_request())

        mock_adapter.record_send_result.assert_awaited_once()
        kw = mock_adapter.record_send_result.call_args.kwargs
        assert kw["success"] is True

    @pytest.mark.asyncio
    async def test_record_send_result_called_on_api_error(self) -> None:
        provider = self._make_provider()
        mock_adapter = _make_initialized_adapter()

        with (
            patch("llm_shared.providers.anthropic._get_adapter_sync", return_value=mock_adapter),
            patch.object(provider, "_ensure_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(side_effect=RuntimeError("api error"))
            mock_client_fn.return_value = mock_client

            resp = await provider._chat_completion_impl(_make_request())

        assert resp.error
        mock_adapter.record_send_result.assert_awaited_once()
        kw = mock_adapter.record_send_result.call_args.kwargs
        assert kw["success"] is False
        assert "api error" in kw["error_message"]

    @pytest.mark.asyncio
    async def test_send_proceeds_when_adapter_absent(self) -> None:
        """Fail-safe: no adapter present — provider sends directly, no exception."""
        provider = self._make_provider()
        sdk_resp = _make_sdk_response("direct")

        with (
            patch("llm_shared.providers.anthropic._get_adapter_sync", return_value=None),
            patch.object(provider, "_ensure_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=sdk_resp)
            mock_client_fn.return_value = mock_client

            resp = await provider._chat_completion_impl(_make_request())

        assert resp.content == "direct"
        assert not resp.error

    @pytest.mark.asyncio
    async def test_send_proceeds_when_adapter_not_initialized(self) -> None:
        """Fail-safe: adapter present but not yet initialized — skip optimization."""
        provider = self._make_provider()
        sdk_resp = _make_sdk_response("direct2")
        mock_adapter = MagicMock()
        mock_adapter.is_initialized = False

        with (
            patch("llm_shared.providers.anthropic._get_adapter_sync", return_value=mock_adapter),
            patch.object(provider, "_ensure_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=sdk_resp)
            mock_client_fn.return_value = mock_client

            resp = await provider._chat_completion_impl(_make_request())

        assert resp.content == "direct2"
        mock_adapter.optimize_for_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_optimize_exception_is_fail_safe(self) -> None:
        """If optimize_for_send raises, send still proceeds (fail-safe)."""
        provider = self._make_provider()
        sdk_resp = _make_sdk_response("safe")
        mock_adapter = _make_initialized_adapter()
        mock_adapter.optimize_for_send = AsyncMock(side_effect=RuntimeError("optimizer boom"))

        with (
            patch("llm_shared.providers.anthropic._get_adapter_sync", return_value=mock_adapter),
            patch.object(provider, "_ensure_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=sdk_resp)
            mock_client_fn.return_value = mock_client

            resp = await provider._chat_completion_impl(_make_request())

        assert resp.content == "safe"
        assert not resp.error


@_skip_no_provider
class TestAnthropicStreamAdapterWiring:
    """AnthropicProvider.stream_completion calls adapter optimize_for_send."""

    def _make_provider(self):
        return _AnthropicProvider(settings={"api_key": "test-key"})

    @pytest.mark.asyncio
    async def test_optimize_for_send_called_before_stream(self) -> None:
        provider = self._make_provider()
        mock_adapter = _make_initialized_adapter()

        async def _fake_text_stream():
            yield "chunk1"
            yield "chunk2"

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=MagicMock(text_stream=_fake_text_stream()))
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("llm_shared.providers.anthropic._get_adapter_sync", return_value=mock_adapter),
            patch.object(provider, "_ensure_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)
            mock_client_fn.return_value = mock_client

            chunks = []
            async for chunk in provider.stream_completion(_make_request()):
                chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2"]
        mock_adapter.optimize_for_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_proceeds_when_adapter_absent(self) -> None:
        provider = self._make_provider()

        async def _fake_text_stream():
            yield "direct-chunk"

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=MagicMock(text_stream=_fake_text_stream()))
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "llm_shared.providers.anthropic._get_adapter_sync",
                return_value=None,
            ),
            patch.object(provider, "_ensure_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)
            mock_client_fn.return_value = mock_client

            chunks = []
            async for chunk in provider.stream_completion(_make_request()):
                chunks.append(chunk)

        assert chunks == ["direct-chunk"]
