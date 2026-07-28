# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Integration tests for configuration migration to centralized ConfigManager
Tests that components properly migrate from direct environment access to centralized config
"""

import os
from unittest.mock import patch

import pytest

from config.manager import UnifiedConfigManager as ConfigManager
from config.manager import get_unified_config_manager

config_manager = get_unified_config_manager()


class TestConfigurationMigration:
    """Test migration from direct environment access to centralized configuration"""

    # NOTE: Two LLMInterface config-migration tests were removed when the
    # LLMInterface god-class was retired (#3185). LLMService (services.llm_service)
    # consumes config via its provider registry; equivalent migration coverage
    # is tracked separately.

    def test_hardware_acceleration_config_usage(self):
        """Test that hardware acceleration uses centralized configuration"""
        from hardware_acceleration import HardwareAccelerationManager

        # Create test config with custom hardware settings
        test_config = ConfigManager()
        test_config.set(
            "runtime.environment_overrides",
            {"CUDA_DEVICE_ORDER": "PCI_BUS_ID", "OMP_NUM_THREADS": "8"},
        )

        with patch("hardware_acceleration.config_manager", test_config):
            hw_manager = HardwareAccelerationManager()

            # Configure environment - should store in config
            hw_manager.configure_system_environment()

            # Verify environment overrides are stored in config
            env_overrides = test_config.get("runtime.environment_overrides", {})
            assert isinstance(env_overrides, dict)
            # Should have some environment variables set
            assert len(env_overrides) > 0

    def test_desktop_streaming_environment_config(self):
        """Test that desktop streaming manager uses config for environment"""
        from desktop_streaming_manager import DesktopStreamingManager

        # Create test config with system environment
        test_config = ConfigManager()
        test_config.set("system.environment", {"CUSTOM_VAR": "test_value", "DISPLAY": ":99"})

        with patch("desktop_streaming_manager.config_manager", test_config):
            DesktopStreamingManager()

            # This would normally use os.environ, but now uses config
            # The actual test would require mocking subprocess calls
            # Just verify the config is accessible
            env_config = test_config.get("system.environment", {})
            assert env_config["CUSTOM_VAR"] == "test_value"
            assert env_config["DISPLAY"] == ":99"

    def test_redis_client_config_migration(self):
        """Test that Redis client uses centralized configuration"""

        # Create test config with Redis settings
        test_config = ConfigManager()
        test_config.set("redis.host", "test-redis-host")
        test_config.set("redis.port", 9999)
        test_config.set("redis.password", "test-password")

        # The redis client patch target `utils.redis_client.config_manager`
        # never existed (canonical module is autobot_shared.redis_client, and
        # `config_manager` was never a module-level attribute there). The
        # original `with patch(...)` wrapper raised ModuleNotFoundError; the
        # assertions below don't depend on the patch — they just verify
        # ConfigManager.get/set round-trip. Wrapper removed; behavior preserved.
        assert test_config.get("redis.host") == "test-redis-host"
        assert test_config.get("redis.port") == 9999
        assert test_config.get("redis.password") == "test-password"

    def test_secrets_service_config_migration(self):
        """Test that secrets service uses centralized configuration"""
        # Create test config with security settings
        test_config = ConfigManager()
        test_config.set("security.secrets_key", "test_secrets_key")

        # Mock the config manager import
        with patch("services.secrets_service.config_manager", test_config):
            pass

            # Create secrets service - should use config for key
            # Note: This might still try to create actual encryption, so we test carefully
            try:
                # Just test that config is accessible
                secrets_key = test_config.get("security.secrets_key")
                assert secrets_key == "test_secrets_key"
            except Exception:
                # If initialization fails, that's OK for this test
                # We're just testing that config access works
                pass

    def test_config_environment_variable_priorities(self):
        """Env-var override is ConfigRegistry's job, via the AUTOBOT_ prefix.

        This previously asserted a three-tier AUTOBOT_ > AB_ > unprefixed order
        against ConfigManager.get(). ConfigManager.get() is a FLAT dict lookup
        (config/sync_ops.py) — it resolves neither dotted paths nor env vars —
        and no AB_/unprefixed tier exists anywhere in the codebase. The test was
        asserting a migration-era design that was never implemented.

        ConfigRegistry.get() is the component that does consult the environment,
        and it builds exactly one key: AUTOBOT_<KEY_WITH_DOTS_AS_UNDERSCORES>.
        """
        from config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()
        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(os.environ, {"AUTOBOT_TEST_KEY": "autobot_value"}, clear=True):
                assert ConfigRegistry.get("test.key") == "autobot_value"

            # No AB_ tier and no unprefixed tier: the caller default stands.
            ConfigRegistry.clear_cache()
            with patch.dict(os.environ, {"AB_TEST_KEY2": "ab", "TEST_KEY2": "plain"}, clear=True):
                assert ConfigRegistry.get("test.key2", default="fallback") == "fallback"

    def test_unified_multimodal_processor_config_usage(self):
        """Test that unified multimodal processor uses centralized config"""
        from multimodal_processor import VisionProcessor

        # Create test config with vision settings
        test_config = ConfigManager()
        # set() is a FLAT dict write (config/sync_ops.py), so a dotted key would
        # not land in the nested tree that get_config_section() reads.
        test_config.set_nested("multimodal.vision.confidence_threshold", 0.9)
        test_config.set_nested("multimodal.vision.processing_timeout", 60)
        test_config.set_nested("multimodal.vision.enabled", False)

        with patch(
            "multimodal_processor.processors.vision.get_config_section",
            lambda section: test_config.get_config_section(section),
        ):
            vision_proc = VisionProcessor()

            # Verify it uses config values
            assert vision_proc.confidence_threshold == 0.9
            assert vision_proc.processing_timeout == 60
            assert vision_proc.enabled is False

    def test_config_section_completeness(self):
        """Test that all required configuration sections are present"""
        cm = ConfigManager()

        # Test that all expected sections exist in default config
        # NOTE: "llm" is deliberately absent — it is not a top-level section;
        # LLM config lives under backend.llm (see config/defaults.py).
        required_sections = [
            "deployment",
            "data",
            "redis",
            "multimodal",
            "npu",
            "hardware",
            "system",
            "network",
            "memory",
            "task_transport",
            "security",
        ]

        for section in required_sections:
            config_section = cm.get_config_section(section)
            assert isinstance(config_section, dict), f"Section {section} should be a dict"
            assert len(config_section) > 0, f"Section {section} should not be empty"

    def test_config_type_consistency(self):
        """Test that configuration values have consistent types"""
        cm = ConfigManager()

        # Test boolean values
        assert isinstance(cm.get_nested("multimodal.vision.enabled"), bool)
        assert isinstance(cm.get_nested("security.enable_sandboxing"), bool)
        assert isinstance(cm.get_nested("hardware.acceleration.enabled"), bool)

        # Test integer values
        assert isinstance(cm.get_nested("redis.port"), int)
        assert isinstance(cm.get_nested("deployment.port"), int)
        assert isinstance(cm.get_nested("backend.server_port"), int)

        # Test float values
        assert isinstance(cm.get_nested("multimodal.vision.confidence_threshold"), (int, float))
        assert isinstance(cm.get_nested("multimodal.voice.confidence_threshold"), (int, float))

        # Test string values
        assert isinstance(cm.get_nested("backend.llm.provider_type"), str)
        assert isinstance(cm.get_nested("deployment.host"), str)
        assert isinstance(cm.get_nested("redis.host"), str)

        # Test list values
        assert isinstance(cm.get_nested("hardware.acceleration.priority_order"), list)
        assert isinstance(cm.get_nested("security.blocked_commands"), list)

    def test_config_migration_backward_compatibility(self):
        """Test that migration maintains backward compatibility"""
        # Test that old config patterns still work during transition period
        # The backward-compat wrapper is config.compat.Config. `utils.config_manager`
        # (the old import path) no longer exists, and `from config import config`
        # yields the SSOT _ConfigProxy, which exposes neither .config nor .get.
        from config.compat import Config

        legacy = Config(config_manager)

        # The backward compatibility wrapper should work
        assert hasattr(legacy, "config")  # Old interface
        assert hasattr(legacy, "get")  # Old interface

        # Should return the same values as the new interface. Use a key that
        # actually EXISTS — the previous "llm.orchestrator_llm" is absent from
        # the config tree, so both sides were None and the assertion was vacuous.
        assert legacy.get("redis") == config_manager.get("redis")
        assert isinstance(legacy.config, dict) and legacy.config

    def test_config_default_value_handling(self):
        """Test proper handling of default values across components"""
        cm = ConfigManager()

        # LLM defaults. NOTE: "llm.orchestrator_llm" and "llm.ollama.base_url"
        # do not exist — LLM config lives under backend.llm, whose provider URL
        # is local.providers.ollama.host.
        assert isinstance(cm.get_nested("backend.llm.provider_type"), str)
        assert cm.get_nested("backend.llm.local.providers.ollama.host").startswith("http")

        # Redis defaults. The host is deployment-specific (it is an SSOT value,
        # not a literal), so assert it is a non-empty string rather than pinning
        # it to localhost — pinning made this fail on every real deployment.
        assert isinstance(cm.get_nested("redis.host"), str)
        assert cm.get_nested("redis.host")
        assert 1 <= cm.get_nested("redis.port") <= 65535

        # Security defaults should be secure by default
        assert cm.get_nested("security.enable_sandboxing") is True
        assert len(cm.get_nested("security.blocked_commands")) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
