# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for per-request/per-conversation model & provider override (#11585).

Covers:
- ChatMessage schema accepts optional model/provider fields
- _validate_and_pin_provider: 422 on unknown provider, conversation pinning
- _generate_ai_response threads model/provider into LLMService.chat()
- _get_selected_model prefers the per-request override over global config
"""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Resolve the REAL provider_registry module from sys.modules — the conftest
# llm_shared package stub is a MagicMock, so string-target patching
# ("llm_shared.provider_registry.get_provider_registry") would patch an
# auto-created mock attribute instead of the module api.chat imports from.
_pr_mod = importlib.import_module("llm_shared.provider_registry")

# ---------------------------------------------------------------------------
# ChatMessage schema fields
# ---------------------------------------------------------------------------


class TestChatMessageSchema:
    def test_model_and_provider_default_to_none(self):
        from api.schemas_chat import ChatMessage

        msg = ChatMessage(content="hi", session_id="s1")
        assert msg.model is None
        assert msg.provider is None

    def test_model_and_provider_accepted(self):
        from api.schemas_chat import ChatMessage

        msg = ChatMessage(content="hi", session_id="s1", model="llama3.2:3b", provider="ollama")
        assert msg.model == "llama3.2:3b"
        assert msg.provider == "ollama"


# ---------------------------------------------------------------------------
# _validate_and_pin_provider
# ---------------------------------------------------------------------------


def _mock_registry(known: bool):
    registry = MagicMock()
    registry.get_provider_by_name.return_value = object() if known else None
    registry.list_providers.return_value = [{"name": "ollama"}, {"name": "openai"}]
    return registry


class TestValidateAndPinProvider:
    def test_unknown_provider_raises_422_with_registered_list(self):
        from api.chat import _validate_and_pin_provider

        registry = _mock_registry(known=False)
        with patch.object(_pr_mod, "get_provider_registry", return_value=registry):
            with pytest.raises(HTTPException) as exc_info:
                _validate_and_pin_provider("nope", "sess-1")

        assert exc_info.value.status_code == 422
        assert "nope" in exc_info.value.detail
        assert "ollama" in exc_info.value.detail
        registry.set_conversation_provider.assert_not_called()

    def test_valid_provider_pinned_to_conversation(self):
        from api.chat import _validate_and_pin_provider

        registry = _mock_registry(known=True)
        with patch.object(_pr_mod, "get_provider_registry", return_value=registry):
            _validate_and_pin_provider("ollama", "sess-1")

        registry.set_conversation_provider.assert_called_once_with("sess-1", "ollama")

    def test_valid_provider_without_session_not_pinned(self):
        from api.chat import _validate_and_pin_provider

        registry = _mock_registry(known=True)
        with patch.object(_pr_mod, "get_provider_registry", return_value=registry):
            _validate_and_pin_provider("ollama", None)

        registry.set_conversation_provider.assert_not_called()

    def test_none_provider_is_noop(self):
        from api.chat import _validate_and_pin_provider

        registry = _mock_registry(known=True)
        with patch.object(_pr_mod, "get_provider_registry", return_value=registry):
            _validate_and_pin_provider(None, "sess-1")

        registry.get_provider_by_name.assert_not_called()
        registry.set_conversation_provider.assert_not_called()


# ---------------------------------------------------------------------------
# _generate_ai_response threading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_ai_response_threads_model_and_provider():
    from api.chat import _generate_ai_response

    llm_service = MagicMock()
    response = MagicMock()
    response.error = ""
    response.content = "hello"
    llm_service.chat = AsyncMock(return_value=response)

    ai_response, llm_response = await _generate_ai_response(
        llm_service,
        [{"role": "user", "content": "hi"}],
        "sess-1",
        "req-1",
        model="llama3.2:3b",
        provider="ollama",
    )

    kwargs = llm_service.chat.call_args.kwargs
    assert kwargs["model_name"] == "llama3.2:3b"
    assert kwargs["provider_name"] == "ollama"
    assert kwargs["conversation_id"] == "sess-1"
    assert ai_response["content"] == "hello"
    assert llm_response is response


@pytest.mark.asyncio
async def test_generate_ai_response_defaults_preserve_prior_behavior():
    from api.chat import _generate_ai_response

    llm_service = MagicMock()
    response = MagicMock()
    response.error = ""
    response.content = "ok"
    llm_service.chat = AsyncMock(return_value=response)

    await _generate_ai_response(llm_service, [{"role": "user", "content": "hi"}], "sess-1", "req-1")

    kwargs = llm_service.chat.call_args.kwargs
    assert kwargs["model_name"] is None
    assert kwargs["provider_name"] is None


# ---------------------------------------------------------------------------
# Workflow path: _get_selected_model request-scoped override
# ---------------------------------------------------------------------------


class TestGetSelectedModelOverride:
    def test_requested_model_wins_over_global_config(self):
        from chat_workflow.llm_handler import LLMHandlerMixin

        class _Stub(LLMHandlerMixin):
            pass

        assert _Stub()._get_selected_model("mistral:7b") == "mistral:7b"

    def test_unset_override_falls_back_to_global_config(self):
        from chat_workflow.llm_handler import LLMHandlerMixin

        class _Stub(LLMHandlerMixin):
            pass

        config = MagicMock()
        config.get_default_llm_model.return_value = "default-model"
        config.get_nested.return_value = "global-model"
        with patch("chat_workflow.llm_handler.get_config", return_value=config):
            assert _Stub()._get_selected_model(None) == "global-model"
