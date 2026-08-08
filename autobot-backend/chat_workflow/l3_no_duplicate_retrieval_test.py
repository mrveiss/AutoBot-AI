# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""L3 must not duplicate the chat path's RAG retrieval (#13742).

Found by the #13689 A/B — the first run in which L3 could fire at all. Both
`Layer3DeepSearch.render` and `_retrieve_knowledge_context` call
`knowledge_service.conversation_aware_retrieve` with the same query, so enabling
the tiered stack meant two vector searches per qualifying turn and the same
chunks twice in the prompt.

This was the sole blocker keeping `tiered_context_enabled` off.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.llm_handler import LLMHandlerMixin

KB_CONTEXT = "## Knowledge Base\nDeploy runbook: run code-sync from the maintenance page."


def _handler(knowledge_service):
    handler = LLMHandlerMixin.__new__(LLMHandlerMixin)
    handler.knowledge_service = knowledge_service
    handler._get_selected_model = MagicMock(return_value="test-model")
    handler._get_ollama_endpoint_for_model = MagicMock(return_value="http://test")
    handler._get_system_prompt = MagicMock(return_value="SYSTEM")
    handler._build_conversation_context = MagicMock(return_value="")
    handler._build_full_prompt = MagicMock(return_value="Full prompt")
    handler._discover_ollama_from_slm = AsyncMock(return_value=None)
    return handler


def _knowledge_service():
    svc = MagicMock()
    svc.conversation_aware_retrieve = AsyncMock(return_value=(KB_CONTEXT, [{"content": "chunk"}], None, None))
    return svc


def _session():
    session = MagicMock()
    session.session_id = "s-1"
    session.conversation_history = []
    session.metadata = {}
    return session


async def _run_turn(handler, message):
    """Drive the real prompt-preparation path with the tiered flag on."""
    with (
        patch("chat_history.layers.TIERED_CONTEXT_ENABLED", True),
        patch("chat_workflow.llm_handler._emit_before_prompt_build", new_callable=AsyncMock),
    ):
        with patch(
            "chat_workflow.llm_handler._emit_system_prompt_ready",
            new_callable=AsyncMock,
            side_effect=lambda prompt, _s: prompt,
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
                    return await handler._prepare_llm_request_params(_session(), message, use_knowledge=True)


class TestSingleRetrievalPerTurn:
    @pytest.mark.asyncio
    async def test_a_retrieval_keyword_turn_retrieves_exactly_once(self):
        """The headline: 'search ...' triggers L3 *and* the main RAG path.

        Before #13742 this was two identical vector searches.
        """
        svc = _knowledge_service()
        handler = _handler(svc)

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            await _run_turn(handler, "search the kb for the deploy runbook")

        assert svc.conversation_aware_retrieve.await_count == 1

    @pytest.mark.asyncio
    async def test_a_plain_turn_also_retrieves_exactly_once(self):
        """No retrieval keyword: L3 would not fire anyway. Guards the fix
        against regressing the ordinary path."""
        svc = _knowledge_service()
        handler = _handler(svc)

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            await _run_turn(handler, "how are you")

        assert svc.conversation_aware_retrieve.await_count == 1


class TestKnowledgeStillReachesThePrompt:
    @pytest.mark.asyncio
    async def test_the_tiered_block_no_longer_carries_a_kb_copy(self):
        """Removing the duplicate must remove the *copy*, not the content.

        The main path still owns retrieval — and unlike the tiered copy, its
        result passes through budget_grounded_context for trimming and citation
        rebinding (#3770/#10837). What must not survive is a second copy inside
        the tiered block, which escaped that budgeting entirely.
        """
        svc = _knowledge_service()
        handler = _handler(svc)

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            params = await _run_turn(handler, "search the kb for the deploy runbook")

        # The tiered context is prepended to the system prompt; the KB copy that
        # L3 used to inject would appear there.
        assert KB_CONTEXT not in params["system_prompt"]
        assert svc.conversation_aware_retrieve.await_count == 1

    @pytest.mark.asyncio
    async def test_l3_keeps_its_own_retrieval_path_for_other_callers(self):
        """The layer is unchanged — only this call site stops feeding it.

        A caller with no separate RAG stage still gets L3's retrieval.
        """
        from chat_history.layers import Layer3DeepSearch

        svc = _knowledge_service()

        rendered = await Layer3DeepSearch().render({"user_message": "search for the runbook", "knowledge_service": svc})

        assert rendered == KB_CONTEXT
        assert svc.conversation_aware_retrieve.await_count == 1
