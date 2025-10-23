"""Unit tests for ContextWindowManager."""
import pytest
import tempfile
import yaml
from pathlib import Path
from src.context_window_manager import ContextWindowManager


class TestContextWindowManager:
    """Test suite for ContextWindowManager."""

    def test_load_model_config(self):
        """Test model configuration loading."""
        mgr = ContextWindowManager()

        # Check default model loaded
        assert mgr.current_model == "qwen2.5-coder-7b-instruct"

        # Check message limits
        assert mgr.get_message_limit() == 20
        assert mgr.get_max_history_tokens() == 3000

    def test_model_switching(self):
        """Test switching between models."""
        mgr = ContextWindowManager()

        # Switch to 14B model (larger context)
        mgr.set_model("qwen2.5-coder-14b-instruct")
        assert mgr.get_message_limit() == 30
        assert mgr.get_max_history_tokens() == 6000

        # Switch to smaller model
        mgr.set_model("llama-3.2-3b-instruct")
        assert mgr.get_message_limit() == 15

    def test_unknown_model_fallback(self):
        """Test fallback to default for unknown models."""
        mgr = ContextWindowManager()

        mgr.set_model("unknown-model-xyz")
        # Should fall back to default
        assert mgr.get_message_limit() == 20

    def test_token_estimation(self):
        """Test token count estimation."""
        mgr = ContextWindowManager()

        # 400 chars ≈ 100 tokens (4 chars/token)
        text = "a" * 400
        estimated = mgr.estimate_tokens(text)
        assert estimated == 100

    def test_retrieval_limit_calculation(self):
        """Test Redis retrieval limit calculation."""
        mgr = ContextWindowManager()

        # Should fetch 2x message limit (buffer)
        limit = mgr.calculate_retrieval_limit()
        assert limit == 40  # 20 messages * 2

        # Test with 14B model
        mgr.set_model("qwen2.5-coder-14b-instruct")
        limit = mgr.calculate_retrieval_limit()
        assert limit == 60  # 30 messages * 2

    def test_should_truncate_history(self):
        """Test history truncation detection."""
        mgr = ContextWindowManager()

        # Small history - no truncation needed
        small_messages = [
            {"content": "Hello" * 10} for _ in range(5)
        ]
        assert not mgr.should_truncate_history(small_messages)

        # Large history - truncation needed
        large_messages = [
            {"content": "x" * 1000} for _ in range(100)
        ]
        assert mgr.should_truncate_history(large_messages)

    def test_get_model_info(self):
        """Test retrieving full model configuration."""
        mgr = ContextWindowManager()

        info = mgr.get_model_info("qwen2.5-coder-7b-instruct")
        assert info["context_window_tokens"] == 4096
        assert info["max_output_tokens"] == 2048
        assert "message_budget" in info

    def test_fallback_config_when_file_missing(self):
        """Test fallback to default config when YAML file is missing."""
        mgr = ContextWindowManager(config_path="nonexistent.yaml")

        # Should still work with defaults
        assert mgr.get_message_limit() == 20
        assert mgr.current_model == "qwen2.5-coder-7b-instruct"

    def test_all_models_configured(self):
        """Test that all expected models are configured."""
        mgr = ContextWindowManager()

        expected_models = [
            "qwen2.5-coder-7b-instruct",
            "qwen2.5-coder-14b-instruct",
            "llama-3.2-3b-instruct",
            "phi-3-mini-4k-instruct"
        ]

        for model in expected_models:
            mgr.set_model(model)
            assert mgr.get_message_limit() > 0
            assert mgr.get_max_history_tokens() > 0

    def test_model_aware_limits_differ(self):
        """Test that different models have different limits."""
        mgr = ContextWindowManager()

        # 7B model
        mgr.set_model("qwen2.5-coder-7b-instruct")
        limit_7b = mgr.get_message_limit()

        # 14B model (should have higher limit)
        mgr.set_model("qwen2.5-coder-14b-instruct")
        limit_14b = mgr.get_message_limit()

        assert limit_14b > limit_7b

    def test_custom_yaml_loading(self):
        """Test loading custom YAML configuration."""
        # Create temporary YAML config
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            custom_config = {
                "models": {
                    "default": {
                        "name": "test-model",
                        "context_window_tokens": 8000,
                        "max_output_tokens": 4000,
                        "message_budget": {
                            "system_prompt": 600,
                            "recent_messages": 25,
                            "max_history_tokens": 5000
                        }
                    },
                    "test-model": {
                        "context_window_tokens": 8000,
                        "max_output_tokens": 4000,
                        "message_budget": {
                            "system_prompt": 600,
                            "recent_messages": 25,
                            "max_history_tokens": 5000
                        }
                    }
                },
                "token_estimation": {
                    "chars_per_token": 4,
                    "safety_margin": 0.9
                }
            }
            yaml.dump(custom_config, f)
            temp_path = f.name

        try:
            mgr = ContextWindowManager(config_path=temp_path)
            assert mgr.current_model == "test-model"
            assert mgr.get_message_limit() == 25
            assert mgr.get_max_history_tokens() == 5000
        finally:
            Path(temp_path).unlink()

    def test_efficiency_improvement(self):
        """Test that new system is more efficient than old hardcoded limits."""
        mgr = ContextWindowManager()

        # Old system: fetch 500, use 200 (60% waste)
        old_fetch = 500
        old_use = 200
        old_waste_percent = ((old_fetch - old_use) / old_fetch) * 100

        # New system: fetch 40, use 20 (50% buffer)
        new_fetch = mgr.calculate_retrieval_limit()
        new_use = mgr.get_message_limit()
        new_waste_percent = ((new_fetch - new_use) / new_fetch) * 100

        # New system should be more efficient
        assert new_fetch < old_fetch
        assert old_waste_percent > new_waste_percent

        print(f"\nEfficiency Improvement:")
        print(f"Old: Fetch {old_fetch}, Use {old_use} ({old_waste_percent:.1f}% overhead)")
        print(f"New: Fetch {new_fetch}, Use {new_use} ({new_waste_percent:.1f}% overhead)")
        print(f"Reduction: {old_fetch - new_fetch} fewer messages fetched ({((old_fetch - new_fetch) / old_fetch) * 100:.1f}% improvement)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
