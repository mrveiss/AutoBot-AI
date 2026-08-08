# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end prompt capture for the reconnected L2/L4 layers (#13686, #13687).

The unit tests in ``tiered_context_sources_test.py`` prove the resolvers return
the right objects. These prove the *prompt the model actually receives* now
contains the blocks those objects feed — which is what both acceptance criteria
ask for, and what could not happen before the fix.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _handler_with_tiered_context_on():
    """Build a bare LLMHandlerMixin for prompt assembly.

    Mirrors ``tests/test_lightweight_mode.py`` — every collaborator the method
    touches is mocked, so a bare instance exercises the real prompt assembly.
    """
    from chat_workflow.llm_handler import LLMHandlerMixin

    handler = LLMHandlerMixin.__new__(LLMHandlerMixin)
    handler.knowledge_service = None
    handler._get_selected_model = MagicMock(return_value="test-model")
    handler._get_ollama_endpoint_for_model = MagicMock(return_value="http://test")
    handler._get_system_prompt = MagicMock(return_value="SYSTEM")
    handler._build_conversation_context = MagicMock(return_value="")
    handler._build_full_prompt = MagicMock(return_value="Full prompt")
    handler._discover_ollama_from_slm = AsyncMock(return_value=None)
    return handler


def _tiered_context_on():
    """Turn the #5066 feature flag on for the duration of a test.

    The flag is resolved from SSOT config at import time
    (``chat_history/layers.py:46``), so an env-var reload cannot flip it. The
    production call site re-imports the name from the module on every turn, so
    patching the module attribute is what the running code actually reads.
    """
    return patch("chat_history.layers.TIERED_CONTEXT_ENABLED", True)


async def _capture_system_prompt(handler, session, message):
    """Run _prepare_llm_request_params under the flag and return the system prompt."""
    with _tiered_context_on(), patch(
        "chat_workflow.llm_handler._emit_before_prompt_build", new_callable=AsyncMock
    ):
        with patch(
            "chat_workflow.llm_handler._emit_system_prompt_ready",
            new_callable=AsyncMock,
            side_effect=lambda prompt, _session: prompt,
        ):
            with patch(
                "chat_workflow.llm_handler._emit_after_prompt_build",
                new_callable=AsyncMock,
                return_value="Full prompt",
            ):
                with patch(
                    "chat_workflow.llm_handler._emit_full_prompt_ready",
                    new_callable=AsyncMock,
                    return_value="Full prompt",
                ):
                    params = await handler._prepare_llm_request_params(
                        session,
                        message,
                        use_knowledge=False,
                        work_item_id=getattr(session, "_work_item_id", None),
                    )
    return params["system_prompt"]


def _session(work_item_id=None):
    session = MagicMock()
    session.session_id = "s-1"
    session.conversation_history = []
    session.metadata = {}
    session._work_item_id = work_item_id
    return session


class TestL2RendersInPrompt:
    @pytest.mark.asyncio
    async def test_known_entity_renders_related_context_block(self):
        """AC #13686: flag on + a known entity -> '## Related Context' in the prompt."""
        graph = MagicMock()
        graph.search_entities = AsyncMock(
            return_value=[{"name": "Redis", "description": "in-memory store used for sessions"}]
        )
        chm = MagicMock()
        chm.memory_graph = graph

        handler = _handler_with_tiered_context_on()
        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=chm,
        ):
            prompt = await _capture_system_prompt(handler, _session(), "How does Redis hold sessions?")

        assert "## Related Context" in prompt
        assert "in-memory store used for sessions" in prompt

    @pytest.mark.asyncio
    async def test_absent_graph_degrades_and_turn_completes(self):
        """AC #13686: graph unavailable -> no L2 block, turn still completes."""
        handler = _handler_with_tiered_context_on()

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            prompt = await _capture_system_prompt(handler, _session(), "How does Redis hold sessions?")

        assert "## Related Context" not in prompt
        assert "SYSTEM" in prompt


class TestL4RendersInPrompt:
    @pytest.mark.asyncio
    async def test_linked_goal_renders_goal_ancestry_block(self):
        """AC #13687: flag on + a session linked to a goal -> '## Goal Ancestry'."""
        chain = [
            {"id": "1", "title": "Ship the platform", "level": "vision", "status": "active"},
            {"id": "2", "title": "Wake the context stack", "level": "objective", "status": "active"},
        ]
        handler = _handler_with_tiered_context_on()

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            with patch(
                "chat_workflow.tiered_context_sources.resolve_goal_ancestry",
                new_callable=AsyncMock,
                return_value=chain,
            ):
                prompt = await _capture_system_prompt(handler, _session("wi-1"), "status?")

        assert "## Goal Ancestry" in prompt
        assert "Wake the context stack" in prompt

    @pytest.mark.asyncio
    async def test_unlinked_session_renders_no_goal_block(self):
        """AC #13687: no linked goal -> no L4 block (and no goal query)."""
        handler = _handler_with_tiered_context_on()

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            with patch("user_management.database.get_async_session_factory") as factory:
                prompt = await _capture_system_prompt(handler, _session(None), "status?")

        assert "## Goal Ancestry" not in prompt
        factory.assert_not_called()
