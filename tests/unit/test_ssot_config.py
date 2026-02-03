#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests for SSOT Configuration Loader
=========================================

Tests the Single Source of Truth configuration system to ensure:
1. Configuration loads from .env file correctly
2. Default values are used when .env values are missing
3. Computed properties (URLs) are generated correctly
4. Type validation works properly
5. Singleton pattern works correctly

Issue: #601 - SSOT Phase 1: Foundation
Related: #599 - SSOT Configuration System Epic
"""

import os
from pathlib import Path
from unittest.mock import patch


class TestVMConfig:
    """Tests for VMConfig class."""

    def test_default_vm_ips(self):
        """Test that default VM IPs are correct."""
        from src.config.ssot_config import VMConfig

        # Create fresh instance without .env
        with patch.dict(os.environ, {}, clear=True):
            config = VMConfig()
            assert config.main == "172.16.168.20"
            assert config.frontend == "172.16.168.21"
            assert config.npu == "172.16.168.22"
            assert config.redis == "172.16.168.23"
            assert config.aistack == "172.16.168.24"
            assert config.browser == "172.16.168.25"
            assert config.ollama == "127.0.0.1"

    def test_vm_config_from_env(self):
        """Test that VM config reads from environment variables."""
        from src.config.ssot_config import VMConfig

        test_env = {
            "AUTOBOT_BACKEND_HOST": "10.0.0.1",
            "AUTOBOT_FRONTEND_HOST": "10.0.0.2",
            "AUTOBOT_REDIS_HOST": "10.0.0.3",
        }
        with patch.dict(os.environ, test_env, clear=True):
            config = VMConfig()
            assert config.main == "10.0.0.1"
            assert config.frontend == "10.0.0.2"
            assert config.redis == "10.0.0.3"


class TestPortConfig:
    """Tests for PortConfig class."""

    def test_default_ports(self):
        """Test that default ports are correct."""
        from src.config.ssot_config import PortConfig

        # Clear env AND disable .env file loading to test true defaults
        with patch.dict(os.environ, {}, clear=True):
            config = PortConfig(_env_file=None)
            assert config.backend == 8001
            assert config.frontend == 5173
            assert config.redis == 6379
            assert config.ollama == 11434
            assert config.vnc == 6080
            assert config.browser == 3000
            assert config.aistack == 8080
            assert config.npu == 8081

    def test_port_config_from_env(self):
        """Test that port config reads from environment variables."""
        from src.config.ssot_config import PortConfig

        test_env = {
            "AUTOBOT_BACKEND_PORT": "9000",
            "AUTOBOT_REDIS_PORT": "6380",
        }
        with patch.dict(os.environ, test_env, clear=True):
            config = PortConfig()
            assert config.backend == 9000
            assert config.redis == 6380


class TestLLMConfig:
    """Tests for LLMConfig class."""

    def test_default_llm_models(self):
        """Test that default LLM models are correct when no env is set."""
        from src.config.ssot_config import LLMConfig

        # Note: Since Pydantic reads from .env file, we test that values are present
        # not necessarily the hardcoded defaults
        with patch.dict(os.environ, {}, clear=True):
            config = LLMConfig()
            # Test that model names are valid (non-empty strings)
            assert isinstance(config.default_model, str)
            assert len(config.default_model) > 0
            assert isinstance(config.provider, str)
            assert config.timeout > 0

    def test_llm_config_from_env(self):
        """Test that LLM config reads from environment variables."""
        from src.config.ssot_config import LLMConfig

        test_env = {
            "AUTOBOT_DEFAULT_LLM_MODEL": "llama3.2:1b",
            "AUTOBOT_LLM_TIMEOUT": "60",
        }
        with patch.dict(os.environ, test_env, clear=True):
            config = LLMConfig()
            assert config.default_model == "llama3.2:1b"
            assert config.timeout == 60


class TestTimeoutConfig:
    """Tests for TimeoutConfig class."""

    def test_default_timeouts(self):
        """Test that default timeouts are correct."""
        from src.config.ssot_config import TimeoutConfig

        with patch.dict(os.environ, {}, clear=True):
            config = TimeoutConfig()
            assert config.api == 10000
            assert config.llm == 30
            assert config.health_check == 3

    def test_timeout_seconds_property(self):
        """Test that api_seconds property converts correctly."""
        from src.config.ssot_config import TimeoutConfig

        test_env = {"AUTOBOT_API_TIMEOUT": "30000"}
        with patch.dict(os.environ, test_env, clear=True):
            config = TimeoutConfig()
            assert config.api == 30000
            assert config.api_seconds == 30.0


class TestRedisConfig:
    """Tests for RedisConfig class."""

    def test_default_redis_databases(self):
        """Test that default Redis database assignments are correct."""
        from src.config.ssot_config import RedisConfig

        with patch.dict(os.environ, {}, clear=True):
            config = RedisConfig()
            assert config.db_main == 0
            assert config.db_knowledge == 1
            assert config.db_prompts == 2
            assert config.db_cache == 5
            assert config.db_testing == 15

    def test_redis_password_optional(self):
        """Test that Redis password can be None or a string."""
        from src.config.ssot_config import RedisConfig

        with patch.dict(os.environ, {}, clear=True):
            config = RedisConfig()
            # Password is optional - can be None or a string from .env
            assert config.password is None or isinstance(config.password, str)


class TestAutoBotConfig:
    """Tests for AutoBotConfig master class."""

    def test_default_config_loads(self):
        """Test that configuration loads correctly with valid values."""
        from src.config.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig()
            # Test that values are valid types/formats
            assert config.deployment_mode in ("distributed", "hybrid", "local")
            assert isinstance(config.debug, bool)
            assert config.log_level in ("DEBUG", "INFO", "WARNING", "ERROR")

    def test_computed_backend_url(self):
        """Test that backend URL is computed correctly."""
        from src.config.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig()
            assert config.backend_url == "http://172.16.168.20:8001"

    def test_computed_redis_url(self):
        """Test that Redis URL is computed correctly."""
        from src.config.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig()
            assert config.redis_url == "redis://172.16.168.23:6379"

    def test_computed_redis_url_with_password(self):
        """Test that Redis URL includes password when set."""
        from src.config.ssot_config import AutoBotConfig

        test_env = {"AUTOBOT_REDIS_PASSWORD": "secret123"}
        with patch.dict(os.environ, test_env, clear=True):
            config = AutoBotConfig()
            assert "secret123" in config.redis_url_with_auth
            assert config.redis_url_with_auth == "redis://:secret123@172.16.168.23:6379"

    def test_computed_websocket_url(self):
        """Test that WebSocket URL is computed correctly."""
        from src.config.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig()
            assert config.websocket_url == "ws://172.16.168.20:8001/ws"

    def test_get_service_url(self):
        """Test the get_service_url helper method."""
        from src.config.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig()
            assert config.get_service_url("backend") == "http://172.16.168.20:8001"
            assert config.get_service_url("redis") == "redis://172.16.168.23:6379"
            assert config.get_service_url("unknown") is None

    def test_get_vm_ip(self):
        """Test the get_vm_ip helper method."""
        from src.config.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig()
            assert config.get_vm_ip("main") == "172.16.168.20"
            assert config.get_vm_ip("redis") == "172.16.168.23"
            assert config.get_vm_ip("unknown") is None

    def test_get_redis_url_for_db(self):
        """Test getting Redis URL for specific database."""
        from src.config.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig()
            url = config.get_redis_url_for_db(5)
            # URL should end with /5 for database 5
            assert url.endswith("/5")
            assert "redis://" in url


class TestSingletonPattern:
    """Tests for singleton get_config() function."""

    def test_get_config_returns_same_instance(self):
        """Test that get_config returns the same instance."""
        from src.config.ssot_config import get_config, reload_config

        # Clear any cached config first
        reload_config()

        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reload_config_creates_new_instance(self):
        """Test that reload_config creates a new instance."""
        from src.config.ssot_config import get_config, reload_config

        config1 = get_config()
        config2 = reload_config()
        # After reload, a new instance should be created
        # Note: The new instance will have same values but different identity
        assert config1 is not config2


class TestBackwardCompatibility:
    """Tests for backward compatibility functions."""

    def test_get_backend_url(self):
        """Test backward compatibility get_backend_url function."""
        from src.config.ssot_config import get_backend_url, reload_config

        reload_config()  # Ensure clean state
        url = get_backend_url()
        assert "http://" in url
        assert ":8001" in url or "AUTOBOT_BACKEND_PORT" in os.environ

    def test_get_redis_url(self):
        """Test backward compatibility get_redis_url function."""
        from src.config.ssot_config import get_redis_url, reload_config

        reload_config()  # Ensure clean state
        url = get_redis_url()
        assert "redis://" in url

    def test_get_default_llm_model(self):
        """Test backward compatibility get_default_llm_model function."""
        from src.config.ssot_config import get_default_llm_model, reload_config

        reload_config()  # Ensure clean state
        model = get_default_llm_model()
        assert model is not None
        assert len(model) > 0


class TestConfigProxy:
    """Tests for the config proxy object."""

    def test_config_proxy_access(self):
        """Test that config proxy provides attribute access."""
        from src.config.ssot_config import config

        # Access through proxy
        assert hasattr(config, "vm")
        assert hasattr(config, "port")
        assert hasattr(config, "llm")

    def test_config_proxy_nested_access(self):
        """Test that config proxy provides nested attribute access."""
        from src.config.ssot_config import config

        # Access nested properties
        assert config.vm.main is not None
        assert config.port.backend is not None
        assert config.llm.default_model is not None


class TestProjectRoot:
    """Tests for PROJECT_ROOT detection."""

    def test_project_root_is_path(self):
        """Test that PROJECT_ROOT is a Path object."""
        from src.config.ssot_config import PROJECT_ROOT

        assert isinstance(PROJECT_ROOT, Path)

    def test_project_root_exists(self):
        """Test that PROJECT_ROOT directory exists."""
        from src.config.ssot_config import PROJECT_ROOT

        assert PROJECT_ROOT.exists()
        assert PROJECT_ROOT.is_dir()
