# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test lightweight mode bypasses middleware for trivial queries.

Issue MVA-1992: Verify that simple tier queries skip RAG, memory, and tools.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from llm_shared.models import LLMRequest
from llm_shared.tiered_routing.complexity_router import ComplexityRouter
from llm_shared.tiered_routing.tier_config import TierConfig


class TestLightweightMode:
    """Test lightweight mode flag and middleware bypass."""

    def test_llm_request_has_lightweight_mode_flag(self):
        """Verify LLMRequest has lightweight_mode field."""
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hi"}],
            lightweight_mode=True
        )
        assert request.lightweight_mode is True

    def test_llm_request_defaults_to_full_mode(self):
        """Verify lightweight_mode defaults to False."""
        request = LLMRequest(
            messages=[{"role": "user", "content": "Complex query"}]
        )
        assert request.lightweight_mode is False

    @pytest.mark.asyncio
    async def test_complexity_router_sets_simple_tier(self):
        """Verify ComplexityRouter identifies simple queries."""
        config = TierConfig(
            enabled=True,
            complexity_threshold=3.0
        )
        router = ComplexityRouter(config=config)

        # Simple query should score below threshold
        simple_messages = [{"role": "user", "content": "Hi"}]
        _, result = router.route(simple_messages)

        # Should be simple tier (score < 3.0)
        assert result.tier == "simple"
        assert result.score < 3.0

    @pytest.mark.asyncio
    async def test_prepare_llm_params_skips_rag_in_lightweight_mode(self):
        """Verify RAG is skipped when lightweight_mode=True."""
        from chat_workflow.llm_handler import LLMHandler

        # Mock dependencies
        handler = LLMHandler()
        handler.knowledge_service = MagicMock()
        handler._get_selected_model = MagicMock(return_value="test-model")
        handler._get_ollama_endpoint_for_model = MagicMock(return_value="http://test")
        handler._get_system_prompt = MagicMock(return_value="System prompt")
        handler._build_conversation_context = MagicMock(return_value="")
        handler._build_full_prompt = MagicMock(return_value="Full prompt")

        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.conversation_history = []
        mock_session.metadata = {}

        # Call with lightweight_mode=True
        with patch('chat_workflow.llm_handler._emit_before_prompt_build', new_callable=AsyncMock):
            with patch('chat_workflow.llm_handler._emit_system_prompt_ready', new_callable=AsyncMock, return_value="System prompt"):
                with patch('chat_workflow.llm_handler._emit_after_prompt_build', new_callable=AsyncMock, return_value="Full prompt"):
                    with patch('chat_workflow.llm_handler._emit_full_prompt_ready', new_callable=AsyncMock, return_value="Full prompt"):
                        params = await handler._prepare_llm_request_params(
                            mock_session,
                            "Hi",
                            use_knowledge=True,
                            lightweight_mode=True
                        )

        # Verify knowledge_service.search was NOT called
        handler.knowledge_service.search.assert_not_called()

        # Verify used_knowledge is False
        assert params["used_knowledge"] is False
        assert params["citations"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
