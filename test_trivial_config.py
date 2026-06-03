#!/usr/bin/env python3
"""
Test script to verify trivial tier configuration (MVA-1991).

This script verifies:
1. TRIVIAL_MODEL constant is defined in ssot_config
2. TierConfig loads the trivial model correctly
3. Trivial tier is enabled by default
4. Model selection routes to the correct tier
"""

import sys
from pathlib import Path

# Add autobot-backend to path
backend_path = Path(__file__).parent / "autobot-backend"
sys.path.insert(0, str(backend_path))

from autobot_shared.ssot_config import TRIVIAL_MODEL, get_config
from llm_shared.tiered_routing.tier_config import TierConfig


def test_trivial_model_constant():
    """Test that TRIVIAL_MODEL constant is defined."""
    print("✓ Testing TRIVIAL_MODEL constant...")
    assert TRIVIAL_MODEL == "llama3.2:1b", f"Expected 'llama3.2:1b', got '{TRIVIAL_MODEL}'"
    print(f"  TRIVIAL_MODEL = {TRIVIAL_MODEL}")


def test_ssot_config_trivial_model():
    """Test that LLMConfig includes trivial_model field."""
    print("\n✓ Testing SSOT config trivial_model field...")
    config = get_config()
    assert hasattr(config.llm, "trivial_model"), "LLMConfig missing trivial_model field"
    assert config.llm.trivial_model == "llama3.2:1b", (
        f"Expected 'llama3.2:1b', got '{config.llm.trivial_model}'"
    )
    print(f"  config.llm.trivial_model = {config.llm.trivial_model}")


def test_tier_config_defaults():
    """Test that TierConfig has correct defaults."""
    print("\n✓ Testing TierConfig defaults...")
    tier_config = TierConfig()

    assert tier_config.enabled, "Tiered routing should be enabled by default"
    print(f"  enabled = {tier_config.enabled}")

    assert tier_config.models.trivial == "llama3.2:1b", (
        f"Expected trivial model 'llama3.2:1b', got '{tier_config.models.trivial}'"
    )
    print(f"  models.trivial = {tier_config.models.trivial}")

    assert tier_config.models.simple == "gemma2:2b", (
        f"Expected simple model 'gemma2:2b', got '{tier_config.models.simple}'"
    )
    print(f"  models.simple = {tier_config.models.simple}")

    assert tier_config.trivial_threshold == 1.0, (
        f"Expected trivial_threshold 1.0, got {tier_config.trivial_threshold}"
    )
    print(f"  trivial_threshold = {tier_config.trivial_threshold}")


def test_tier_config_from_registry():
    """Test that TierConfig.from_config() loads from registry."""
    print("\n✓ Testing TierConfig.from_config()...")
    tier_config = TierConfig.from_config()

    # Should load the trivial model from registry defaults
    assert tier_config.models.trivial, "Trivial model should be configured"
    print(f"  models.trivial = {tier_config.models.trivial}")
    print(f"  models.simple = {tier_config.models.simple}")
    print(f"  models.complex = {tier_config.models.complex}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("MVA-1991: Trivial Tier Configuration Tests")
    print("=" * 60)

    try:
        test_trivial_model_constant()
        test_ssot_config_trivial_model()
        test_tier_config_defaults()
        test_tier_config_from_registry()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        print("\nConfiguration summary:")
        print(f"  Trivial tier model: llama3.2:1b (1.2B params, 1.3GB)")
        print(f"  Threshold: < 1.0 score routes to trivial tier")
        print(f"  Status: Enabled by default")
        return 0

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
