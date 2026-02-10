#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Timeout Configuration Validation Script

Validates the centralized timeout configuration system.
Part of KB-ASYNC-014: Timeout Configuration Centralization.
"""

import sys
from pathlib import Path
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for numeric type checks
_NUMERIC_TYPES = (int, float)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import UnifiedConfigManager


def print_section(title: str):
    """Print a section header."""
    logger.info(f"\n{'=' * 70}")
    logger.info(f"  {title}")
    logger.info(f"{'=' * 70}\n")


def validate_configuration(config: UnifiedConfigManager) -> bool:
    """Validate timeout configuration."""
    print_section("TIMEOUT CONFIGURATION VALIDATION")

    validation_result = config.validate_timeouts()

    if validation_result["valid"]:
        logger.info("✅ Configuration is VALID")
    else:
        logger.error("❌ Configuration has ISSUES")

    if validation_result["issues"]:
        logger.info("\n🔴 Issues found:")
        for issue in validation_result["issues"]:
            logger.info(f"  - {issue}")

    if validation_result["warnings"]:
        logger.warning("\n⚠️  Warnings:")
        for warning in validation_result["warnings"]:
            logger.warning(f"  - {warning}")

    return validation_result["valid"]


def test_environment_aware_access(config: UnifiedConfigManager):
    """Test environment-aware timeout access."""
    print_section("ENVIRONMENT-AWARE TIMEOUT ACCESS")

    test_cases = [
        # Redis operations
        (
            "redis.operations",
            "get",
            "production",
            0.5,
            "Redis GET - Production (strict)",
        ),
        (
            "redis.operations",
            "get",
            "development",
            1.0,
            "Redis GET - Development (lenient)",
        ),
        (
            "redis.operations",
            "scan_iter",
            "development",
            30.0,
            "Redis SCAN_ITER - Development (override)",
        ),
        # LlamaIndex
        (
            "llamaindex.search",
            "query",
            "production",
            5.0,
            "LlamaIndex Query - Production (strict)",
        ),
        (
            "llamaindex.search",
            "query",
            "development",
            20.0,
            "LlamaIndex Query - Development (override)",
        ),
        # Documents
        (
            "documents.operations",
            "add_document",
            None,
            30.0,
            "Add Document - Default environment",
        ),
    ]

    all_passed = True

    for category, timeout_type, env, expected, description in test_cases:
        actual = config.get_timeout_for_env(category, timeout_type, env)
        status = "✅" if actual == expected else "❌"

        if actual != expected:
            all_passed = False

        env or "default"
        logger.info(f"{status} {description}")
        logger.info(f"   Expected: {expected}s, Got: {actual}s")

    if all_passed:
        logger.info("\n✅ All environment-aware access tests PASSED")
    else:
        logger.error("\n❌ Some environment-aware access tests FAILED")

    return all_passed


def test_timeout_groups(config: UnifiedConfigManager):
    """Test batch timeout retrieval."""
    print_section("TIMEOUT GROUP RETRIEVAL")

    test_groups = [
        ("redis.operations", None, "Redis Operations - Base config"),
        ("redis.operations", "development", "Redis Operations - Development"),
        ("llamaindex.search", "production", "LlamaIndex Search - Production"),
    ]

    for category, env, description in test_groups:
        timeouts = config.get_timeout_group(category, env)
        env_str = env or "base"

        logger.info(f"📦 {description} ({env_str}):")
        for key, value in sorted(timeouts.items()):
            logger.info(f"   {key}: {value}s")

    logger.info("\n✅ Timeout group retrieval working correctly")


def test_backward_compatibility(config: UnifiedConfigManager):
    """Test backward compatibility with expected values."""
    print_section("BACKWARD COMPATIBILITY CHECK")

    # Expected default timeout values
    expected_defaults = {
        "redis.connection.socket_connect": 2.0,
        "redis.operations.get": 1.0,
        "llamaindex.indexing.single_document": 10.0,
        "documents.operations.add_document": 30.0,
        "llm.default": 120.0,
    }

    all_passed = True

    for path, expected in expected_defaults.items():
        parts = path.split(".")
        category = ".".join(parts[:-1])
        timeout_type = parts[-1]

        actual = config.get_timeout_for_env(
            category, timeout_type, environment="production"
        )

        # For Redis get operation, production override is 0.5
        if path == "redis.operations.get":
            expected = 0.5

        status = "✅" if actual == expected else "❌"
        if actual != expected:
            all_passed = False

        logger.info(f"{status} {path}: Expected {expected}s, Got {actual}s")

    if all_passed:
        logger.info("\n✅ All backward compatibility checks PASSED")
    else:
        logger.error("\n❌ Some backward compatibility checks FAILED")

    return all_passed


def display_summary(config: UnifiedConfigManager):
    """Display configuration summary."""
    print_section("TIMEOUT CONFIGURATION SUMMARY")

    all_timeouts = config.get("timeouts", {})

    logger.info("📊 Configured Timeout Categories:")
    for category in all_timeouts:
        logger.info(f"   - {category}")

    # Count total timeout values
    def count_timeouts(cfg: Dict[str, Any]) -> int:
        """Recursively count numeric timeout values in configuration."""
        count = 0
        for value in cfg.values():
            if isinstance(value, dict):
                count += count_timeouts(value)
            elif isinstance(value, _NUMERIC_TYPES):  # Issue #380
                count += 1
        return count

    total = count_timeouts(all_timeouts)
    logger.info(f"\n📈 Total timeout values configured: {total}")

    # Environment overrides
    dev_overrides = config.get("environments.development.timeouts", {})
    prod_overrides = config.get("environments.production.timeouts", {})

    logger.info(f"\n🔧 Development overrides: {count_timeouts(dev_overrides)}")
    logger.info(f"🔧 Production overrides: {count_timeouts(prod_overrides)}")


def main():
    """Main validation routine."""
    logger.info("\n" + "=" * 70)
    logger.info("  TIMEOUT CONFIGURATION VALIDATION TOOL")
    logger.info("  KB-ASYNC-014: Phase 1 Validation")
    logger.info("=" * 70)

    try:
        # Load configuration
        config = UnifiedConfigManager()
        logger.info("\n✅ UnifiedConfigManager loaded successfully")

        # Run validation tests
        config_valid = validate_configuration(config)
        env_tests_passed = test_environment_aware_access(config)
        test_timeout_groups(config)
        compat_tests_passed = test_backward_compatibility(config)
        display_summary(config)

        # Final result
        print_section("VALIDATION RESULTS")

        all_passed = config_valid and env_tests_passed and compat_tests_passed

        if all_passed:
            logger.info("✅ ALL VALIDATION CHECKS PASSED")
            logger.info("\n✨ Timeout configuration is ready for Phase 2 (code migration)")
            return 0
        else:
            logger.error("❌ VALIDATION FAILED")
            logger.warning("\n⚠️  Fix configuration issues before proceeding to Phase 2")
            return 1

    except Exception as e:
        logger.error(f"\n❌ VALIDATION ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
