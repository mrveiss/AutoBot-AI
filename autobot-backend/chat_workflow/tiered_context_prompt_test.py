# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end prompt capture for the reconnected L2 and L4 layers (#13686, #13687).

``tiered_context_sources_test.py`` proves the resolver returns the graph the
manager owns. These prove the *prompt the model actually receives* now contains
the block that graph feeds — which is the acceptance criterion, and what could
not happen before the fix.
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
    with _tiered_context_on(), patch("chat_workflow.llm_handler._emit_before_prompt_build", new_callable=AsyncMock):
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
                    )
    return params["system_prompt"]


def _session():
    session = MagicMock()
    session.session_id = "s-1"
    session.conversation_history = []
    session.metadata = {}
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


class TestL4RendersInPromptViaTheBinding:
    """AC #13704-3: the goal block reaches a real prompt through the production path.

    Not by injecting a chain into the builder — that only proves
    `Layer4GoalAncestry` renders, which was never in doubt. This starts from the
    *server-side binding*, which is the only thing that can produce the state.
    """

    @pytest.mark.asyncio
    async def test_a_bound_session_renders_the_goal_ancestry_block(self):
        chain = [
            {"id": "1", "title": "Ship the platform", "level": "vision", "status": "active"},
            {"id": "2", "title": "Wake the context stack", "level": "objective", "status": "active"},
        ]
        handler = _handler_with_tiered_context_on()

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            # The binding is what the bind endpoint writes; everything downstream
            # is the real path.
            with patch(
                "chat_workflow.session_work_item.SessionWorkItemService.get_binding",
                new_callable=AsyncMock,
                return_value=("wi-1", "company-a"),
            ):
                with patch(
                    "chat_workflow.tiered_context_sources._query_goal_ancestry",
                    new_callable=AsyncMock,
                    return_value=chain,
                ):
                    prompt = await _capture_system_prompt(handler, _session(), "what is the status")

        assert "## Goal Ancestry" in prompt
        assert "Wake the context stack" in prompt

    @pytest.mark.asyncio
    async def test_an_unbound_session_renders_no_goal_block(self):
        handler = _handler_with_tiered_context_on()

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            with patch(
                "chat_workflow.session_work_item.SessionWorkItemService.get_binding",
                new_callable=AsyncMock,
                return_value=(None, None),
            ):
                prompt = await _capture_system_prompt(handler, _session(), "what is the status")

        assert "## Goal Ancestry" not in prompt
