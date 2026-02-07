"""
Test suite for centralized configuration management
Tests the ConfigManager functionality and standardized configuration access
"""

import os
import tempfile
from unittest.mock import patch

import pytest
from src.utils.config_manager import (
    ConfigManager,
    get_config,
    get_config_section,
    is_feature_enabled,
)


class TestConfigManager:
    """Test centralized configuration manager"""

    def test_default_config_initialization(self):
        """Test that ConfigManager initializes with default configuration"""
        cm = ConfigManager()

        # Test that default sections exist
        assert cm.get("llm.orchestrator_llm") == "ollama"
        assert cm.get("deployment.host") == "localhost"
        assert cm.get("redis.port") == 6379
        assert cm.get("multimodal.vision.enabled") is True
        assert cm.get("security.enable_sandboxing") is True

    def test_config_file_loading(self):
        """Test loading configuration from YAML file"""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
llm:
  orchestrator_llm: "custom_ollama"
  openai:
    api_key: "test_key"
redis:
  host: "test_redis"
  port: 9999
"""
            )
            config_file = f.name

        try:
            cm = ConfigManager(config_file=config_file)

            # Test that file config overrides defaults
            assert cm.get("llm.orchestrator_llm") == "custom_ollama"
            assert cm.get("llm.openai.api_key") == "test_key"
            assert cm.get("redis.host") == "test_redis"
            assert cm.get("redis.port") == 9999

            # Test that unspecified values use defaults
            assert cm.get("deployment.host") == "localhost"
            assert cm.get("multimodal.vision.enabled") is True

        finally:
            os.unlink(config_file)

    def test_environment_variable_fallback(self):
        """Test fallback to environment variables"""
        cm = ConfigManager()

        # Test with environment variables set
        with patch.dict(
            os.environ,
            {
                "AUTOBOT_LLM_OPENAI_API_KEY": "env_test_key",
                "AB_NONEXISTENT_VAR": "env_nonexistent_value",
                "REDIS_PORT": "7777",
            },
        ):
            # Test that empty config values fall back to environment
            assert (
                cm.get("llm.openai.api_key") == "env_test_key"
            )  # Empty string should fallback

            # Test environment fallback for non-existent keys
            assert cm.get("nonexistent.var") == "env_nonexistent_value"

            # Test with no matching environment variable
            assert cm.get("no.env.match", "default_val") == "default_val"

            # Test direct environment access via _get_env_var
            env_value = cm._get_env_var("llm.openai.api_key", None)
            assert env_value == "env_test_key"

    def test_environment_value_parsing(self):
        """Test parsing of environment variable values to appropriate types"""
        cm = ConfigManager()

        with patch.dict(
            os.environ,
            {
                "AUTOBOT_TEST_BOOL_TRUE": "true",
                "AUTOBOT_TEST_BOOL_FALSE": "false",
                "AUTOBOT_TEST_INT": "42",
                "AUTOBOT_TEST_FLOAT": "3.14",
                "AUTOBOT_TEST_LIST": "item1,item2,item3",
            },
        ):
            assert cm.get("test.bool.true") is True
            assert cm.get("test.bool.false") is False
            assert cm.get("test.int") == 42
            assert cm.get("test.float") == 3.14
            assert cm.get("test.list") == ["item1", "item2", "item3"]

    def test_dot_notation_access(self):
        """Test dot notation for nested configuration access"""
        cm = ConfigManager()

        # Test existing nested values
        assert cm.get("llm.ollama.model") == "llama3.2"
        assert cm.get("multimodal.vision.confidence_threshold") == 0.7
        assert (
            cm.get("hardware.environment_variables.cuda_device_order") == "PCI_BUS_ID"
        )

        # Test non-existent path returns default
        assert cm.get("non.existent.path", "default_value") == "default_value"
        assert cm.get("non.existent.path") is None

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
        """Test getting entire configuration sections"""
        cm = ConfigManager()

        # Test existing sections
        llm_config = cm.get_section("llm")
        assert isinstance(llm_config, dict)
        assert "orchestrator_llm" in llm_config
        assert "ollama" in llm_config

        redis_config = cm.get_section("redis")
        assert isinstance(redis_config, dict)
        assert redis_config["host"] == "localhost"
        assert redis_config["port"] == 6379

        # Test non-existent section
        empty_config = cm.get_section("nonexistent")
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
        """Test configuration validation"""
        cm = ConfigManager()

        # Should validate successfully with default config
        issues = cm.validate_config()
        assert isinstance(issues, list)
        assert len(issues) == 0  # Default config should be valid

        # Test with missing required section
        cm._config_cache = {"llm": {}}  # Missing required fields
        issues = cm.validate_config()
        assert len(issues) > 0
        assert any("Missing" in issue for issue in issues)

    def test_config_save_and_reload(self):
        """Test saving and reloading configuration"""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_file = f.name

        try:
            cm = ConfigManager(config_file=config_file)

            # Modify config
            cm.set("test.save.value", "saved_data")
            assert cm.get("test.save.value") == "saved_data"

            # Save config
            cm.save()

            # Create new instance and verify it loads saved data
            cm2 = ConfigManager(config_file=config_file)
            assert cm2.get("test.save.value") == "saved_data"

            # Test reload
            cm.set("test.reload.value", "reload_data")
            cm.save()

            cm2.reload()
            assert cm2.get("test.reload.value") == "reload_data"

        finally:
            if os.path.exists(config_file):
                os.unlink(config_file)

    def test_multimodal_and_npu_config(self):
        """Test multi-modal and NPU specific configuration"""
        cm = ConfigManager()

        # Test multi-modal configuration
        mm_config = cm.get_multimodal_config()
        assert isinstance(mm_config, dict)
        assert "vision" in mm_config
        assert "voice" in mm_config
        assert mm_config["vision"]["enabled"] is True
        assert mm_config["vision"]["confidence_threshold"] == 0.7

        # Test NPU configuration
        npu_config = cm.get_npu_config()
        assert isinstance(npu_config, dict)
        assert npu_config["enabled"] is False
        assert npu_config["device"] == "CPU"

    def test_hardware_configuration_sections(self):
        """Test new hardware configuration sections"""
        cm = ConfigManager()

        # Test hardware environment variables
        hw_env = cm.get("hardware.environment_variables")
        assert isinstance(hw_env, dict)
        assert hw_env["cuda_device_order"] == "PCI_BUS_ID"
        assert hw_env["omp_num_threads"] == "4"

        # Test hardware acceleration settings
        hw_accel = cm.get("hardware.acceleration")
        assert isinstance(hw_accel, dict)
        assert hw_accel["enabled"] is True
        assert hw_accel["priority_order"] == ["npu", "gpu", "cpu"]

    def test_system_configuration_sections(self):
        """Test system configuration sections"""
        cm = ConfigManager()

        # Test system environment
        sys_env = cm.get("system.environment")
        assert isinstance(sys_env, dict)
        assert sys_env["DISPLAY"] == ":0"

        # Test desktop streaming settings
        desktop = cm.get("system.desktop_streaming")
        assert isinstance(desktop, dict)
        assert desktop["default_resolution"] == "1024x768"
        assert desktop["max_sessions"] == 10

    def test_security_configuration(self):
        """Test security configuration sections"""
        cm = ConfigManager()

        # Test security settings
        security = cm.get_section("security")
        assert isinstance(security, dict)
        assert security["enable_sandboxing"] is True
        assert isinstance(security["blocked_commands"], list)
        assert "rm -rf" in security["blocked_commands"]
        assert security["secrets_key"] is None
        assert security["audit_log_file"] == "data/audit.log"

    def test_backward_compatibility_wrapper(self):
        """Test backward compatibility Config class wrapper"""
        from src.utils.config_manager import Config

        config = Config()

        # Test that it provides access to complete config
        full_config = config.config
        assert isinstance(full_config, dict)
        assert "llm" in full_config
        assert "redis" in full_config

        # Test that get method works
        assert config.get("llm.orchestrator_llm") == "ollama"
        assert config.get("redis.port") == 6379

    def test_global_instance_functions(self):
        """Test global convenience functions"""
        # Test get_config function
        value = get_config("llm.orchestrator_llm")
        assert value == "ollama"

        value = get_config("nonexistent.key", "default")
        assert value == "default"

        # Test get_config_section function
        section = get_config_section("redis")
        assert isinstance(section, dict)
        assert section["host"] == "localhost"

        # Test is_feature_enabled function
        assert is_feature_enabled("multimodal.vision") is True
        assert is_feature_enabled("npu") is False

    def test_data_and_task_transport_sections(self):
        """Test data and task transport configuration sections"""
        cm = ConfigManager()

        # Test data section
        data_config = cm.get_section("data")
        assert isinstance(data_config, dict)
        assert data_config["reliability_stats_file"] == "data/reliability_stats.json"
        assert data_config["long_term_db_path"] == "data/agent_memory.db"
        assert data_config["chat_history_file"] == "data/chat_history.json"

        # Test task transport section
        transport_config = cm.get_section("task_transport")
        assert isinstance(transport_config, dict)
        assert transport_config["type"] == "redis"
        assert isinstance(transport_config["redis"], dict)

    def test_network_configuration(self):
        """Test network configuration section"""
        cm = ConfigManager()

        network_config = cm.get_section("network")
        assert isinstance(network_config, dict)
        assert "share" in network_config
        assert network_config["share"]["username"] is None
        assert network_config["share"]["password"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
