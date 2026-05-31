# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test lightweight mode bypasses middleware for trivial queries.

Issue MVA-1992: Verify that trivial-tier queries skip RAG, memory, and tools.
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
            lightweight_mode=True,
        )
        assert request.lightweight_mode is True

    def test_llm_request_defaults_to_full_mode(self):
        """Verify lightweight_mode defaults to False."""
        request = LLMRequest(
            messages=[{"role": "user", "content": "Complex query"}]
        )
        assert request.lightweight_mode is False

    def test_complexity_router_trivial_tier_when_configured(self):
        """Verify ComplexityRouter routes ultra-simple queries to trivial tier (GH#9050)."""
        # trivial_threshold only exists after GH#9050 merges; guard with getattr
        config_kwargs = {
            "enabled": True,
            "complexity_threshold": 3.0,
        }
        if hasattr(TierConfig, "trivial_threshold"):
            # Build a TierModels with a trivial model set so the router uses the tier
            from llm_shared.tiered_routing.tier_config import TierModels
            config_kwargs["trivial_threshold"] = 1.0
            config_kwargs["models"] = TierModels(trivial="phi3:mini", simple="llama3:8b", complex="llama3:70b")

        config = TierConfig(**config_kwargs)
        router = ComplexityRouter(config=config)

        simple_messages = [{"role": "user", "content": "Hi"}]
        _, result = router.route(simple_messages)

        if hasattr(TierConfig, "trivial_threshold"):
            assert result.tier == "trivial"
        else:
            # Pre-GH#9050: simple tier is the lowest
            assert result.tier == "simple"

        assert result.score < 3.0

    def test_complexity_router_simple_fallback(self):
        """Without trivial tier configured, simple tier scores < threshold."""
        config = TierConfig(
            enabled=True,
            complexity_threshold=3.0,
        )
        router = ComplexityRouter(config=config)

        simple_messages = [{"role": "user", "content": "Hi"}]
        _, result = router.route(simple_messages)

        assert result.tier in ("trivial", "simple")
        assert result.score < 3.0

    @pytest.mark.asyncio
    async def test_prepare_llm_params_skips_rag_in_lightweight_mode(self):
        """Verify RAG is skipped when lightweight_mode=True."""
        from chat_workflow.llm_handler import LLMHandler

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

        with patch("chat_workflow.llm_handler._emit_before_prompt_build", new_callable=AsyncMock):
            with patch("chat_workflow.llm_handler._emit_system_prompt_ready", new_callable=AsyncMock, return_value="System prompt"):
                with patch("chat_workflow.llm_handler._emit_after_prompt_build", new_callable=AsyncMock, return_value="Full prompt"):
                    with patch("chat_workflow.llm_handler._emit_full_prompt_ready", new_callable=AsyncMock, return_value="Full prompt"):
                        params = await handler._prepare_llm_request_params(
                            mock_session,
                            "Hi",
                            use_knowledge=True,
                            lightweight_mode=True,
                        )

        # RAG must be skipped
        handler.knowledge_service.search.assert_not_called()
        assert params["used_knowledge"] is False
        assert params["citations"] == []

    @pytest.mark.asyncio
    async def test_prepare_llm_params_skips_memory_in_lightweight_mode(self):
        """Verify memory graph lookup is skipped when lightweight_mode=True."""
        from chat_workflow.llm_handler import LLMHandler

        handler = LLMHandler()
        handler.knowledge_service = None
        handler.memory_graph = MagicMock()
        handler._get_selected_model = MagicMock(return_value="test-model")
        handler._get_ollama_endpoint_for_model = MagicMock(return_value="http://test")
        handler._get_system_prompt = MagicMock(return_value="System prompt")
        handler._build_conversation_context = MagicMock(return_value="")
        handler._build_full_prompt = MagicMock(return_value="Full prompt")

        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.conversation_history = []
        mock_session.metadata = {}

        tiered_ctx_build = AsyncMock(return_value=None)
        with patch("chat_workflow.llm_handler._emit_before_prompt_build", new_callable=AsyncMock):
            with patch("chat_workflow.llm_handler._emit_system_prompt_ready", new_callable=AsyncMock, return_value="System prompt"):
                with patch("chat_workflow.llm_handler._emit_after_prompt_build", new_callable=AsyncMock, return_value="Full prompt"):
                    with patch("chat_workflow.llm_handler._emit_full_prompt_ready", new_callable=AsyncMock, return_value="Full prompt"):
                        with patch("chat_history.layers.TieredContextBuilder.build", tiered_ctx_build):
                            await handler._prepare_llm_request_params(
                                mock_session,
                                "Hi",
                                use_knowledge=False,
                                lightweight_mode=True,
                            )

        # Memory graph (TieredContextBuilder) must NOT be called
        tiered_ctx_build.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
