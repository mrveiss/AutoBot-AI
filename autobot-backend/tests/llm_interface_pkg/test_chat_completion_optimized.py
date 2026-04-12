# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for chat_completion_optimized vLLM model name recording.

Tests for GitHub issue #3943: Ensure analytics records correct vLLM model name,
not the Ollama default, when using chat_completion_optimized().
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass


@dataclass
class MockLLMResponse:
    """Mock LLM response for testing."""
    model: str = None
    content: str = "test response"
    usage: dict = None
    cache_hit_rate: float = 0.0
    metadata: dict = None

    def __post_init__(self):
        if self.usage is None:
            self.usage = {"prompt_tokens": 10, "completion_tokens": 20}
        if self.metadata is None:
            self.metadata = {}


@pytest.mark.asyncio
async def test_chat_completion_optimized_uses_vllm_config_model():
    """
    Test that chat_completion_optimized reads vLLM model directly from config,
    not via _determine_provider_and_model which would return Ollama default.

    Fixes issue #3943: Model name recorded in analytics should be the vLLM model,
    not the Ollama default model.
    """
    from llm_interface_pkg.interface import LLMInterface
    from autobot_shared.ssot_config import config

    # Create a mock LLMInterface instance
    interface = LLMInterface()

    # Mock the config to return a specific vLLM model
    vllm_model = "meta-llama/Llama-3.2-70B-Instruct"

    with patch("llm_interface_pkg.interface.config") as mock_config, \
         patch("llm_interface_pkg.interface.get_optimized_prompt") as mock_prompt, \
         patch.object(interface, "_execute_with_fallback") as mock_execute, \
         patch.object(interface, "_check_cache") as mock_cache, \
         patch.object(interface, "_finalize_response") as mock_finalize, \
         patch.object(interface, "_calculate_cache_hit_rate") as mock_calc_cache:

        # Setup mocks
        mock_config.get.return_value = vllm_model
        mock_prompt.return_value = "system prompt"
        mock_cache.return_value = (None, None)  # No cache hit

        mock_response = MockLLMResponse(model=vllm_model)
        mock_execute.return_value = mock_response
        mock_finalize.return_value = mock_response

        # Call chat_completion_optimized
        result = await interface.chat_completion_optimized(
            agent_type="test_agent",
            user_message="test message",
            session_id="session-123",
        )

        # Verify config.get was called with correct vLLM key
        mock_config.get.assert_called_with(
            "llm.vllm.default_model",
            "meta-llama/Llama-3.2-3B-Instruct"
        )

        # Verify _finalize_response was called with vllm_model, not Ollama default
        # The actual_model_name should be vllm_model (either from response.model or config)
        call_args = mock_finalize.call_args
        assert call_args is not None
        # Model name should be in the positional args or kwargs
        finalize_model_arg = call_args[0][2] if len(call_args[0]) > 2 else None
        assert finalize_model_arg == vllm_model, \
            f"Expected model name '{vllm_model}' in _finalize_response call, got '{finalize_model_arg}'"


@pytest.mark.asyncio
async def test_chat_completion_optimized_uses_response_model_when_available():
    """
    Test that chat_completion_optimized uses response.model if the vLLM provider
    populated it, falling back to config value otherwise.

    This ensures analytics records the model name actually returned by vLLM,
    if different from the configured default.
    """
    from llm_interface_pkg.interface import LLMInterface

    interface = LLMInterface()

    config_model = "meta-llama/Llama-3.2-3B-Instruct"
    response_model = "meta-llama/Llama-3.2-70B-Instruct"  # vLLM provider returned different model

    with patch("llm_interface_pkg.interface.config") as mock_config, \
         patch("llm_interface_pkg.interface.get_optimized_prompt") as mock_prompt, \
         patch.object(interface, "_execute_with_fallback") as mock_execute, \
         patch.object(interface, "_check_cache") as mock_cache, \
         patch.object(interface, "_finalize_response") as mock_finalize, \
         patch.object(interface, "_calculate_cache_hit_rate") as mock_calc_cache:

        mock_config.get.return_value = config_model
        mock_prompt.return_value = "system prompt"
        mock_cache.return_value = (None, None)

        # vLLM provider returned a different model in response
        mock_response = MockLLMResponse(model=response_model)
        mock_execute.return_value = mock_response
        mock_finalize.return_value = mock_response

        result = await interface.chat_completion_optimized(
            agent_type="test_agent",
            user_message="test message",
            session_id="session-123",
        )

        # _finalize_response should be called with response.model, not config model
        call_args = mock_finalize.call_args
        finalize_model_arg = call_args[0][2] if len(call_args[0]) > 2 else None
        assert finalize_model_arg == response_model, \
            f"Expected model name from response '{response_model}', got '{finalize_model_arg}'"


@pytest.mark.asyncio
async def test_chat_completion_optimized_fallback_to_config_model():
    """
    Test that chat_completion_optimized falls back to config model name
    when response.model is not provided by the vLLM provider.
    """
    from llm_interface_pkg.interface import LLMInterface

    interface = LLMInterface()

    config_model = "meta-llama/Llama-3.2-3B-Instruct"

    with patch("llm_interface_pkg.interface.config") as mock_config, \
         patch("llm_interface_pkg.interface.get_optimized_prompt") as mock_prompt, \
         patch.object(interface, "_execute_with_fallback") as mock_execute, \
         patch.object(interface, "_check_cache") as mock_cache, \
         patch.object(interface, "_finalize_response") as mock_finalize, \
         patch.object(interface, "_calculate_cache_hit_rate") as mock_calc_cache:

        mock_config.get.return_value = config_model
        mock_prompt.return_value = "system prompt"
        mock_cache.return_value = (None, None)

        # vLLM provider did not populate response.model
        mock_response = MockLLMResponse(model=None)
        mock_execute.return_value = mock_response
        mock_finalize.return_value = mock_response

        result = await interface.chat_completion_optimized(
            agent_type="test_agent",
            user_message="test message",
            session_id="session-123",
        )

        # _finalize_response should be called with config_model (fallback)
        call_args = mock_finalize.call_args
        finalize_model_arg = call_args[0][2] if len(call_args[0]) > 2 else None
        assert finalize_model_arg == config_model, \
            f"Expected fallback to config model '{config_model}', got '{finalize_model_arg}'"


def test_determine_provider_and_model_vllm_prefix():
    """
    Test that _determine_provider_and_model correctly handles vllm_ prefixed aliases.

    This test documents the behavior: without proper config setup, calling
    _determine_provider_and_model("vllm") (no prefix) would return ollama provider.
    That's why chat_completion_optimized bypasses this and reads directly from config.
    """
    from llm_interface_pkg.interface import LLMInterface

    interface = LLMInterface()

    # Test with vllm_ prefixed model alias
    provider, model_name = interface._determine_provider_and_model(
        "vllm_llama3.1:405b"
    )

    assert provider == "vllm"
    assert model_name == "llama3.1:405b"


def test_determine_provider_and_model_unprefixed_falls_to_ollama():
    """
    Test that _determine_provider_and_model without a recognized prefix falls through
    to Ollama as the default provider.

    This documents why chat_completion_optimized cannot use _determine_provider_and_model("vllm")
    — it would return ollama provider with the Ollama default model.
    """
    from llm_interface_pkg.interface import LLMInterface

    interface = LLMInterface()

    # Calling with "vllm" (no prefix) without special handling
    # would fall through to the else branch and return ollama
    provider, model_name = interface._determine_provider_and_model("something_not_recognized")

    # This demonstrates why chat_completion_optimized has special logic:
    # it reads the vLLM model from config directly instead of using
    # _determine_provider_and_model which would return ollama/default
    assert provider == "ollama"
