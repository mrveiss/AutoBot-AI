# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Topic guidance on the chat system prompt: off by default, appended when ``AUTOBOT_CHAT_TOPIC_GUIDANCE`` is on (#21678)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ssot_config import config as ssot
from intent_classifier import GENERAL_TOPIC, detect_topic

BASE = "SYSTEM"
GUIDANCE = "INSTALL-GUIDANCE"


def _handler():
    from chat_workflow.llm_handler import LLMHandlerMixin

    handler = LLMHandlerMixin.__new__(LLMHandlerMixin)
    handler.knowledge_service = None
    handler._get_selected_model = MagicMock(return_value="test-model")
    handler._get_ollama_endpoint_for_model = MagicMock(return_value="http://test")
    handler._get_system_prompt = MagicMock(return_value=BASE)
    handler._build_conversation_context = MagicMock(return_value="")
    handler._build_full_prompt = MagicMock(return_value="Full prompt")
    handler._discover_ollama_from_slm = AsyncMock(return_value=None)
    return handler


def _session():
    session = MagicMock()
    session.session_id = "s-1"
    session.conversation_history = []
    session.metadata = {}
    return session


async def _system_prompt(message: str, flag: bool) -> str:
    handler = _handler()
    with (
        patch.object(ssot, "chat_topic_guidance_enabled", flag, create=True),
        patch("intent_classifier.get_prompt", return_value=GUIDANCE),
        patch("chat_workflow.llm_handler._emit_before_prompt_build", new_callable=AsyncMock),
        patch(
            "chat_workflow.llm_handler._emit_system_prompt_ready",
            new_callable=AsyncMock,
            side_effect=lambda prompt, _session: prompt,
        ),
        patch("chat_workflow.llm_handler._emit_after_prompt_build", new_callable=AsyncMock, return_value="Full prompt"),
        patch("chat_workflow.llm_handler._emit_full_prompt_ready", new_callable=AsyncMock, return_value="Full prompt"),
    ):
        params = await handler._prepare_llm_request_params(
            _session(), message, use_knowledge=False, lightweight_mode=True
        )
    return params["system_prompt"]


def test_the_flag_defaults_to_off(monkeypatch):
    """The declared default, isolated from the environment and any ``.env`` the developer has."""
    from autobot_shared.ssot_chat_graph_settings import ChatGraphSettings

    monkeypatch.delenv("AUTOBOT_CHAT_TOPIC_GUIDANCE", raising=False)
    assert ChatGraphSettings(_env_file=None).chat_topic_guidance_enabled is False


@pytest.mark.asyncio
async def test_flag_off_leaves_the_system_prompt_byte_identical():
    assert await _system_prompt("How do I install AutoBot?", flag=False) == BASE


@pytest.mark.asyncio
async def test_flag_on_with_a_topic_message_appends_the_guidance():
    prompt = await _system_prompt("How do I install AutoBot?", flag=True)
    assert prompt.startswith(BASE) and GUIDANCE in prompt and "installation conversation" in prompt


@pytest.mark.asyncio
async def test_flag_on_with_a_general_message_still_changes_nothing():
    assert await _system_prompt("Hello there", flag=True) == BASE


def test_a_keyword_inside_another_word_does_not_select_a_topic():
    assert detect_topic("I walked through the forest") == GENERAL_TOPIC
    assert detect_topic("vmware licensing") == GENERAL_TOPIC


def test_a_whole_word_keyword_selects_its_topic():
    assert detect_topic("rest api") == "api"
    assert detect_topic("my vm is slow") == "architecture"
