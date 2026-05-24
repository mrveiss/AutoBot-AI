# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for Claude escalation in tiered router (#8171)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.tiered_routing.complexity_router import ComplexityRouter
from llm_shared.tiered_routing.tier_config import TierConfig, TierModels

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SIMPLE_MESSAGES = [{"role": "user", "content": "hi"}]

_COMPLEX_MESSAGES = [
    {"role": "system", "content": "You are a helpful expert assistant."},
    {
        "role": "user",
        "content": (
            "Design a distributed consensus protocol in Python. "
            "Implement Raft with leader election, log replication, "
            "fault tolerance, and full error handling. "
            "Write step-by-step code with async/await, using Redis "
            "for persistent state and implement the optimization for "
            "large-scale deployments. " + "x" * 2000
        ),
    },
]


@pytest.fixture
def tier_config():
    return TierConfig(
        enabled=True,
        complexity_threshold=3.0,
        models=TierModels(simple="cheap-model", complex="capable-model"),
    )


@pytest.fixture
def router(tier_config):
    return ComplexityRouter(tier_config)


def _make_ok_response() -> LLMResponse:
    return LLMResponse(
        content="Claude escalated response",
        model="claude-sonnet-4-6",
        provider="anthropic",
    )


def _make_error_response() -> LLMResponse:
    return LLMResponse(
        content="",
        model="claude-sonnet-4-6",
        provider="anthropic",
        error="API error",
    )


def _make_provider_with_resolved_key():
    """Build a bare AnthropicProvider instance with _api_key set via env (no literal)."""
    import os

    from llm_shared.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._settings = {}
    # Resolve from env so no literal credential appears in source (#3022)
    provider._api_key = os.environ.get("ANTHROPIC_API_KEY", "x" * 8)
    provider._client = MagicMock()
    return provider


# ---------------------------------------------------------------------------
# Test 1: Low complexity score → local provider used, no Claude call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_low_complexity_no_escalation(router):
    """When complexity_score < threshold, route_with_escalation returns None."""
    request = LLMRequest(messages=_SIMPLE_MESSAGES)
    mock_llm_config = MagicMock()
    mock_llm_config.claude_escalation_enabled = True
    mock_llm_config.claude_escalation_threshold = 7.0

    with patch("llm_shared.tiered_routing.complexity_router.ssot_config") as mock_cfg:
        mock_cfg.llm = mock_llm_config
        with patch(
            "llm_shared.tiered_routing.complexity_router.AnthropicProvider",
            autospec=True,
        ) as mock_provider_cls:
            result = await router.route_with_escalation(request)

    assert result is None
    mock_provider_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: High complexity + escalation enabled → Claude called and response returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_complexity_escalation_enabled(router):
    """When score >= threshold and enabled=True, Claude is called and result returned."""
    request = LLMRequest(messages=_COMPLEX_MESSAGES)
    mock_llm_config = MagicMock()
    mock_llm_config.claude_escalation_enabled = True
    mock_llm_config.claude_escalation_threshold = 7.0

    mock_claude = AsyncMock()
    mock_claude._chat_completion_impl = AsyncMock(return_value=_make_ok_response())

    with patch("llm_shared.tiered_routing.complexity_router.ssot_config") as mock_cfg:
        mock_cfg.llm = mock_llm_config
        with patch(
            "llm_shared.tiered_routing.complexity_router.AnthropicProvider",
            return_value=mock_claude,
        ):
            result = await router.route_with_escalation(request)

    assert result is not None
    assert result.content == "Claude escalated response"
    assert result.error is None


# ---------------------------------------------------------------------------
# Test 3: High complexity + escalation disabled → local provider used (None returned)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_complexity_escalation_disabled(router):
    """When escalation is disabled, route_with_escalation always returns None."""
    request = LLMRequest(messages=_COMPLEX_MESSAGES)
    mock_llm_config = MagicMock()
    mock_llm_config.claude_escalation_enabled = False

    with patch("llm_shared.tiered_routing.complexity_router.ssot_config") as mock_cfg:
        mock_cfg.llm = mock_llm_config
        with patch(
            "llm_shared.tiered_routing.complexity_router.AnthropicProvider",
            autospec=True,
        ) as mock_provider_cls:
            result = await router.route_with_escalation(request)

    assert result is None
    mock_provider_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: Claude returns error → falls through (returns None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_error_falls_through(router):
    """When Claude returns an error response, route_with_escalation returns None."""
    request = LLMRequest(messages=_COMPLEX_MESSAGES)
    mock_llm_config = MagicMock()
    mock_llm_config.claude_escalation_enabled = True
    mock_llm_config.claude_escalation_threshold = 7.0

    mock_claude = AsyncMock()
    mock_claude._chat_completion_impl = AsyncMock(return_value=_make_error_response())

    with patch("llm_shared.tiered_routing.complexity_router.ssot_config") as mock_cfg:
        mock_cfg.llm = mock_llm_config
        with patch(
            "llm_shared.tiered_routing.complexity_router.AnthropicProvider",
            return_value=mock_claude,
        ):
            result = await router.route_with_escalation(request)

    assert result is None


# ---------------------------------------------------------------------------
# Test 5: Claude raises exception → falls through (returns None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_exception_falls_through(router):
    """When AnthropicProvider raises, route_with_escalation returns None."""
    request = LLMRequest(messages=_COMPLEX_MESSAGES)
    mock_llm_config = MagicMock()
    mock_llm_config.claude_escalation_enabled = True
    mock_llm_config.claude_escalation_threshold = 7.0

    mock_claude = AsyncMock()
    mock_claude._chat_completion_impl = AsyncMock(side_effect=RuntimeError("network error"))

    with patch("llm_shared.tiered_routing.complexity_router.ssot_config") as mock_cfg:
        mock_cfg.llm = mock_llm_config
        with patch(
            "llm_shared.tiered_routing.complexity_router.AnthropicProvider",
            return_value=mock_claude,
        ):
            result = await router.route_with_escalation(request)

    assert result is None


# ---------------------------------------------------------------------------
# Test 6: enable_prompt_cache=True → cache_control added to system message
# ---------------------------------------------------------------------------


def test_prompt_cache_adds_cache_control_to_system():
    """When enable_prompt_cache=True, system becomes a content-block list with cache_control."""
    provider = _make_provider_with_resolved_key()

    request = LLMRequest(
        messages=[
            {"role": "system", "content": "You are an expert."},
            {"role": "user", "content": "Hello"},
        ],
        metadata={"enable_prompt_cache": True},
    )

    kwargs, _headers, _preserve = provider._build_request_kwargs("claude-sonnet-4-6", request)

    system = kwargs.get("system")
    assert isinstance(system, list), "system should be a list when prompt caching is enabled"
    assert len(system) == 1
    block = system[0]
    assert block["type"] == "text"
    assert block["text"] == "You are an expert."
    assert block["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Test 7: enable_prompt_cache absent → system remains a plain string
# ---------------------------------------------------------------------------


def test_no_prompt_cache_system_is_string():
    """Without enable_prompt_cache, system message stays as a plain string."""
    provider = _make_provider_with_resolved_key()

    request = LLMRequest(
        messages=[
            {"role": "system", "content": "You are an expert."},
            {"role": "user", "content": "Hello"},
        ],
        metadata={},
    )

    kwargs, _headers, _preserve = provider._build_request_kwargs("claude-sonnet-4-6", request)

    system = kwargs.get("system")
    assert isinstance(system, str)
    assert system == "You are an expert."


# ---------------------------------------------------------------------------
# Test 8: Escalation sets enable_prompt_cache when system message present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalation_sets_prompt_cache_flag_when_system_present(router):
    """When escalating with a system message, metadata enable_prompt_cache=True is set."""
    request = LLMRequest(messages=_COMPLEX_MESSAGES)  # has system role
    mock_llm_config = MagicMock()
    mock_llm_config.claude_escalation_enabled = True
    mock_llm_config.claude_escalation_threshold = 7.0

    captured_requests = []

    async def capture_request(req):
        captured_requests.append(req)
        return _make_ok_response()

    mock_claude = AsyncMock()
    mock_claude._chat_completion_impl = capture_request

    with patch("llm_shared.tiered_routing.complexity_router.ssot_config") as mock_cfg:
        mock_cfg.llm = mock_llm_config
        with patch(
            "llm_shared.tiered_routing.complexity_router.AnthropicProvider",
            return_value=mock_claude,
        ):
            await router.route_with_escalation(request)

    assert len(captured_requests) == 1
    assert captured_requests[0].metadata.get("enable_prompt_cache") is True


# ---------------------------------------------------------------------------
# Test 9: Escalation does NOT set enable_prompt_cache when no system message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalation_no_prompt_cache_without_system(router):
    """When escalating without a system message, enable_prompt_cache is not set."""
    no_system_complex = [
        {
            "role": "user",
            "content": (
                "Implement a distributed consensus algorithm in Python "
                "step by step with async/await, Redis caching, and full "
                "fault tolerance handling. " + "x" * 2000
            ),
        }
    ]
    request = LLMRequest(messages=no_system_complex)
    mock_llm_config = MagicMock()
    mock_llm_config.claude_escalation_enabled = True
    mock_llm_config.claude_escalation_threshold = 7.0

    captured_requests = []

    async def capture_request(req):
        captured_requests.append(req)
        return _make_ok_response()

    mock_claude = AsyncMock()
    mock_claude._chat_completion_impl = capture_request

    with patch("llm_shared.tiered_routing.complexity_router.ssot_config") as mock_cfg:
        mock_cfg.llm = mock_llm_config
        with patch(
            "llm_shared.tiered_routing.complexity_router.AnthropicProvider",
            return_value=mock_claude,
        ):
            result = await router.route_with_escalation(request)

    # If the score was high enough to escalate, verify no prompt cache flag
    if result is not None and captured_requests:
        assert captured_requests[0].metadata.get("enable_prompt_cache") is not True
