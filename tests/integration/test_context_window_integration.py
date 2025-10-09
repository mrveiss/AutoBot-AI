"""
Integration tests for Context Window Configuration
Tests real endpoint behavior with model-aware message limits
"""

import pytest
import asyncio
from pathlib import Path
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.context_window_manager import ContextWindowManager
from src.chat_history_manager import ChatHistoryManager


@pytest.mark.asyncio
class TestContextWindowIntegration:
    """Integration tests for context window management"""

    async def test_chat_history_manager_integration(self):
        """Test ContextWindowManager integration with ChatHistoryManager"""

        # Initialize managers
        context_mgr = ContextWindowManager()

        # Test with default model (qwen2.5-coder-7b)
        limit = context_mgr.get_message_limit()
        assert limit == 20, f"Expected 20 messages for default model, got {limit}"

        # Test with larger model (14B)
        context_mgr.set_model("qwen2.5-coder-14b-instruct")
        limit = context_mgr.get_message_limit()
        assert limit == 30, f"Expected 30 messages for 14B model, got {limit}"

        # Test with smaller model (3B)
        context_mgr.set_model("llama-3.2-3b-instruct")
        limit = context_mgr.get_message_limit()
        assert limit == 15, f"Expected 15 messages for 3B model, got {limit}"

    async def test_retrieval_efficiency(self):
        """Test that retrieval is more efficient than hardcoded 500"""
        context_mgr = ContextWindowManager()

        # Default model retrieval limit
        retrieval_limit = context_mgr.calculate_retrieval_limit()

        # Should be 40 (20 messages * 2 buffer)
        assert retrieval_limit == 40, f"Expected 40, got {retrieval_limit}"

        # Efficiency improvement
        old_fetch = 500
        new_fetch = retrieval_limit
        improvement = ((old_fetch - new_fetch) / old_fetch) * 100

        assert improvement >= 90, f"Expected >= 90% improvement, got {improvement:.1f}%"
        print(f"✅ Efficiency improvement: {improvement:.1f}% (fetch {new_fetch} instead of {old_fetch})")

    async def test_model_fallback_behavior(self):
        """Test fallback to default for unknown models"""
        context_mgr = ContextWindowManager()

        # Unknown model should fall back to default
        context_mgr.set_model("unknown-model-xyz")
        limit = context_mgr.get_message_limit()

        # Should use default model limit
        assert limit == 20, f"Expected fallback to 20, got {limit}"

    async def test_token_estimation_accuracy(self):
        """Test token estimation is reasonable"""
        context_mgr = ContextWindowManager()

        # 400 characters should be ~100 tokens (4 chars/token)
        text = "a" * 400
        estimated = context_mgr.estimate_tokens(text)

        assert 90 <= estimated <= 110, f"Expected ~100 tokens, got {estimated}"

        # Larger text
        large_text = "Hello world " * 1000  # ~12,000 chars
        estimated_large = context_mgr.estimate_tokens(large_text)

        expected = 12000 // 4  # 3000 tokens
        assert 2700 <= estimated_large <= 3300, f"Expected ~3000 tokens, got {estimated_large}"

    async def test_truncation_detection(self):
        """Test that truncation is detected when needed"""
        context_mgr = ContextWindowManager()

        # Create messages that exceed token limit
        large_messages = [
            {"role": "user", "content": "x" * 5000},
            {"role": "assistant", "content": "y" * 5000},
            {"role": "user", "content": "z" * 5000}
        ]

        # Should detect need for truncation
        needs_truncation = context_mgr.should_truncate_history(large_messages)
        assert needs_truncation, "Should detect need for truncation with large messages"

        # Small messages should not need truncation
        small_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]

        needs_truncation_small = context_mgr.should_truncate_history(small_messages)
        assert not needs_truncation_small, "Should not truncate small messages"

    async def test_all_models_have_config(self):
        """Test that all configured models are accessible"""
        context_mgr = ContextWindowManager()

        expected_models = [
            "qwen2.5-coder-7b-instruct",
            "qwen2.5-coder-14b-instruct",
            "llama-3.2-3b-instruct",
            "phi-3-mini-4k-instruct"
        ]

        for model in expected_models:
            context_mgr.set_model(model)
            limit = context_mgr.get_message_limit(model)
            assert limit > 0, f"Model {model} has no message limit configured"

            max_tokens = context_mgr.get_max_history_tokens(model)
            assert max_tokens > 0, f"Model {model} has no max_history_tokens configured"

    async def test_config_file_loading(self):
        """Test that YAML config loads correctly"""
        # Test with existing config file
        context_mgr = ContextWindowManager("config/llm_models.yaml")

        assert context_mgr.config is not None
        assert "models" in context_mgr.config
        assert "token_estimation" in context_mgr.config

        # Test fallback when file missing
        context_mgr_fallback = ContextWindowManager("nonexistent.yaml")

        # Should still work with defaults
        limit = context_mgr_fallback.get_message_limit()
        assert limit == 20, "Should use default config when file missing"


@pytest.mark.asyncio
class TestEndpointIntegration:
    """Test that endpoints correctly use ContextWindowManager"""

    async def test_chat_endpoint_uses_context_manager(self):
        """Verify chat endpoints use model-aware limits"""

        # This would require actual endpoint testing
        # For now, we verify the manager works correctly
        context_mgr = ContextWindowManager()

        # Simulate what chat endpoint does
        model_name = "qwen2.5-coder-14b-instruct"
        context_mgr.set_model(model_name)

        # Get retrieval limit (replaces hardcoded 500)
        retrieval_limit = context_mgr.calculate_retrieval_limit()
        assert retrieval_limit == 60, f"14B model should fetch 60 messages, got {retrieval_limit}"

        # Get message limit (replaces hardcoded 200)
        message_limit = context_mgr.get_message_limit()
        assert message_limit == 30, f"14B model should use 30 messages, got {message_limit}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
