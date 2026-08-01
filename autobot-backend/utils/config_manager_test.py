# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Test suite for centralized configuration management
Tests the ConfigManager functionality and standardized configuration access
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from autobot_shared.network_constants import NetworkConstants
from config import get_config, get_config_section, is_feature_enabled
from config.manager import ConfigManager as ConfigManager

# NOTE (#11954): This file tested a much older, flat-schema ConfigManager
# API (config_file=, dot-path .get(), get_section(), a generic per-key
# env-var-fallback mechanism, get_multimodal_config()/get_npu_config()).
# None of that survived the SSOT migrations (#763/#3829/#639/#620/#717) —
# .get() is now a literal flat-key lookup, .get_nested()/.get_config_section()
# do dot-path traversal, construction takes config_dir (a directory
# containing config.yaml) not a config_file path, and env overrides are a
# fixed ENV_VAR_MAPPINGS table applied once at load time (config/loader.py),
# not a dynamic per-key AUTOBOT_<PATH> convention. Assertions below were
# rewritten against the real, current API/schema — see config/manager.py,
# config/defaults.py, config/loader.py.


class TestConfigManager:
    """Test centralized configuration manager"""

    def test_default_config_initialization(self):
        """Test that ConfigManager initializes with default configuration"""
        cm = ConfigManager()

        # Test that default sections exist (dot-path access is get_nested())
        assert cm.get_nested("backend.llm.local.provider") == "ollama"
        assert cm.get_nested("deployment.mode") == "local"
        assert cm.get_nested("redis.port") == NetworkConstants.REDIS_PORT
        assert cm.get_nested("multimodal.vision.enabled") is True
        assert cm.get_nested("security.enable_sandboxing") is True

    def test_config_file_loading(self):
        """Test loading configuration from a config.yaml in config_dir.

        ConfigManager takes config_dir (a directory containing config.yaml),
        not an arbitrary config_file path (#11954).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_yaml = Path(tmpdir) / "config.yaml"
            override_text = "custom_ollama"
            config_yaml.write_text(
                "llm:\n"
                f'  orchestrator_llm: "{override_text}"\n'
                "  openai:\n"
                '    credential: "placeholder-credential"\n'
                "redis:\n"
                '  host: "test_redis"\n'
                "  port: 9999\n",
                encoding="utf-8",
            )

            cm = ConfigManager(config_dir=tmpdir)

            # New top-level keys from YAML are merged in as-is
            assert cm.get_nested("llm.orchestrator_llm") == override_text
            assert cm.get_nested("llm.openai.credential") == "placeholder-credential"
            # "redis" is a default section — YAML deep-merges onto it
            assert cm.get_nested("redis.host") == "test_redis"
            assert cm.get_nested("redis.port") == 9999

            # Test that unspecified values use defaults
            assert cm.get_nested("deployment.mode") == "local"
            assert cm.get_nested("multimodal.vision.enabled") is True

    def test_environment_variable_fallback(self):
        """Test fallback to environment variables.

        The real mechanism is a fixed ENV_VAR_MAPPINGS table
        (config/loader.py) applied once at config-load time — not a
        dynamic per-key AUTOBOT_<DOTPATH> convention or a `_get_env_var`
        method (neither exists) (#11954).
        """
        with patch.dict(os.environ, {"AUTOBOT_UI_THEME": "dark"}):
            cm = ConfigManager()
            assert cm.get_nested("ui.theme") == "dark"

        # Without the env var, the default applies
        cm_default = ConfigManager()
        assert cm_default.get_nested("ui.theme") == "light"

    def test_environment_value_parsing(self):
        """Test parsing of environment variable values to appropriate types.

        _convert_env_value() (config/loader.py) only coerces bool/int —
        there is no float or comma-list parsing (#11954).
        """
        with patch.dict(
            os.environ,
            {
                "AUTOBOT_CHAT_AUTO_SCROLL": "false",
                "AUTOBOT_CHAT_MAX_MESSAGES": "250",
                "AUTOBOT_LOG_LEVEL": "DEBUG",
            },
        ):
            cm = ConfigManager()
            assert cm.get_nested("chat.auto_scroll") is False
            assert cm.get_nested("chat.max_messages") == 250
            assert cm.get_nested("logging.log_level") == "DEBUG"

    def test_dot_notation_access(self):
        """Test dot notation for nested configuration access"""
        cm = ConfigManager()

        # Test existing nested values
        assert cm.get_nested("backend.llm.local.provider") == "ollama"
        assert cm.get_nested("multimodal.vision.confidence_threshold") == 0.7
        assert cm.get_nested("hardware.environment_variables.cuda_device_order") == "PCI_BUS_ID"

        # Test non-existent path returns default
        assert cm.get_nested("non.existent.path", "default_value") == "default_value"
        assert cm.get_nested("non.existent.path") is None

    def test_set_configuration(self):
        """Test setting configuration values"""
        cm = ConfigManager()

        # Set new value
        cm.set("test.new.value", "test_data")
        assert cm.get("test.new.value") == "test_data"

        # Override existing value
        cm.set("redis.port", 8888)
        assert cm.get("redis.port") == 8888

        # Set nested structure
        cm.set("test.nested.deep.value", {"key": "data"})
        assert cm.get("test.nested.deep.value") == {"key": "data"}

    def test_get_section(self):
        """Test getting entire configuration sections via get_config_section()

        (#11954: get_section() never existed — get_config_section() is the
        real, live section accessor, from ServiceConfigMixin.)
        """
        cm = ConfigManager()

        # Test existing sections
        backend_config = cm.get_config_section("backend")
        assert isinstance(backend_config, dict)
        assert "llm" in backend_config
        assert "ollama" in backend_config["llm"]["local"]["providers"]

        redis_config = cm.get_config_section("redis")
        assert isinstance(redis_config, dict)
        assert isinstance(redis_config["host"], str) and redis_config["host"]
        assert redis_config["port"] == NetworkConstants.REDIS_PORT

        # Test non-existent section
        empty_config = cm.get_config_section("nonexistent")
        assert empty_config == {}

    def test_feature_enabled_check(self):
        """Test is_feature_enabled functionality"""
        cm = ConfigManager()

        # Test existing enabled features
        assert cm.is_feature_enabled("multimodal.vision") is True
        assert cm.is_feature_enabled("multimodal.voice") is True

        # Test disabled features
        assert cm.is_feature_enabled("npu") is False

        # Test non-existent features
        assert cm.is_feature_enabled("nonexistent.feature") is False

    def test_configuration_validation(self):
        """Test configuration validation.

        validate_config() (ValidationMixin) returns a status dict with an
        "issues" list, not a bare list (#11954). The "trigger a validation
        issue" half of the original test is gone: get_llm_config() /
        get_selected_model() now self-heal (config -> env -> hardcoded
        ModelConstants.DEFAULT_OLLAMA_MODEL fallback) and get_redis_config()
        reads straight from SSOT — there is no longer a way to make either
        section "missing" via simple config mutation.
        """
        cm = ConfigManager()

        result = cm.validate_config()
        assert isinstance(result, dict)
        issues = result["issues"]
        assert isinstance(issues, list)
        assert len(issues) == 0  # Default config should be valid

    def test_config_save_and_reload(self):
        """Test saving and reloading configuration.

        save_config_to_yaml() + config_dir-based construction are the real
        persist/reload path (#11954: there is no bare save()/config_file=).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = ConfigManager(config_dir=tmpdir)

            # Modify config (set_nested is the dot-path setter)
            cm.set_nested("test.save.value", "saved_data")
            assert cm.get_nested("test.save.value") == "saved_data"

            # Save config
            cm.save_config_to_yaml()

            # Create new instance and verify it loads saved data
            cm2 = ConfigManager(config_dir=tmpdir)
            assert cm2.get_nested("test.save.value") == "saved_data"

            # Test reload
            cm.set_nested("test.reload.value", "reload_data")
            cm.save_config_to_yaml()

            cm2.reload()
            assert cm2.get_nested("test.reload.value") == "reload_data"

    def test_multimodal_and_npu_config(self):
        """Test multi-modal and NPU specific configuration.

        get_multimodal_config()/get_npu_config() never existed on
        ConfigManager — get_config_section() is the real generic section
        accessor (#11954).
        """
        cm = ConfigManager()

        # Test multi-modal configuration
        mm_config = cm.get_config_section("multimodal")
        assert isinstance(mm_config, dict)
        assert "vision" in mm_config
        assert "voice" in mm_config
        assert mm_config["vision"]["enabled"] is True
        assert mm_config["vision"]["confidence_threshold"] == 0.7

        # Test NPU configuration
        npu_config = cm.get_config_section("npu")
        assert isinstance(npu_config, dict)
        assert npu_config["enabled"] is False
        assert npu_config["device"] == "CPU"

    def test_hardware_configuration_sections(self):
        """Test new hardware configuration sections"""
        cm = ConfigManager()

        # Test hardware environment variables
        hw_env = cm.get_nested("hardware.environment_variables")
        assert isinstance(hw_env, dict)
        assert hw_env["cuda_device_order"] == "PCI_BUS_ID"
        assert hw_env["omp_num_threads"] == "4"

        # Test hardware acceleration settings
        hw_accel = cm.get_nested("hardware.acceleration")
        assert isinstance(hw_accel, dict)
        assert hw_accel["enabled"] is True
        assert hw_accel["priority_order"] == ["npu", "gpu", "cpu"]

    def test_system_configuration_sections(self):
        """Test system configuration sections"""
        cm = ConfigManager()

        # Test system environment
        sys_env = cm.get_nested("system.environment")
        assert isinstance(sys_env, dict)
        assert sys_env["DISPLAY"] == ":0"

        # Test desktop streaming settings
        desktop = cm.get_nested("system.desktop_streaming")
        assert isinstance(desktop, dict)
        assert desktop["default_resolution"] == "1024x768"
        assert desktop["max_sessions"] == 10

    def test_security_configuration(self):
        """Test security configuration sections"""
        cm = ConfigManager()

        # Test security settings
        security = cm.get_config_section("security")
        assert isinstance(security, dict)
        assert security["enable_sandboxing"] is True
        assert isinstance(security["blocked_commands"], list)
        assert "rm -rf" in security["blocked_commands"]
        assert security["secrets_key"] is None
        assert security["audit_log_file"] == "data/audit.log"

    def test_backward_compatibility_wrapper(self):
        """Test backward compatibility Config class wrapper.

        Config() requires a manager instance — Config(ConfigManager()) — and
        Config.get() delegates to the manager's flat .get(), not dot-path
        traversal (#11954).
        """
        from config import Config

        manager = ConfigManager()
        config = Config(manager)

        # Test that it provides access to complete config
        full_config = config.config
        assert isinstance(full_config, dict)
        assert "backend" in full_config
        assert "redis" in full_config

        # Config.get() delegates to the flat ConfigManager.get()
        manager.set("compat_test_key", "compat_value")
        assert config.get("compat_test_key") == "compat_value"
        assert config.get("nonexistent_key", "fallback") == "fallback"

    def test_global_instance_functions(self):
        """Test global convenience functions.

        get_config()/get_config_section() (config/__init__.py) delegate to
        the process-wide singleton's flat .get() / .get_nested() (#11954).
        """
        value = get_config("nonexistent.key", "default")
        assert value == "default"

        # A single (non-dotted) top-level key resolves via the flat .get()
        redis_top_level = get_config("redis")
        assert isinstance(redis_top_level, dict)
        assert redis_top_level["port"] == NetworkConstants.REDIS_PORT

        # Test get_config_section function (dot-path traversal)
        section = get_config_section("redis")
        assert isinstance(section, dict)
        assert section["port"] == NetworkConstants.REDIS_PORT

        # Test is_feature_enabled function
        assert is_feature_enabled("multimodal.vision") is True
        assert is_feature_enabled("npu") is False

    def test_data_and_task_transport_sections(self):
        """Test data and task transport configuration sections"""
        cm = ConfigManager()

        # Test data section
        data_config = cm.get_config_section("data")
        assert isinstance(data_config, dict)
        assert data_config["reliability_stats_file"] == "data/reliability_stats.json"
        assert data_config["long_term_db_path"] == "data/agent_memory.db"
        assert data_config["chat_history_file"] == "data/chat_history.json"

        # Test task transport section
        transport_config = cm.get_config_section("task_transport")
        assert isinstance(transport_config, dict)
        assert transport_config["type"] == "redis"
        assert isinstance(transport_config["redis"], dict)

    def test_network_configuration(self):
        """Test network configuration section"""
        cm = ConfigManager()

        network_config = cm.get_config_section("network")
        assert isinstance(network_config, dict)
        assert "share" in network_config
        assert network_config["share"]["username"] is None
        assert network_config["share"]["password"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
