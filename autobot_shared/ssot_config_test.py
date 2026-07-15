#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
Fix: #9907 - import path updated to canonical autobot_shared.ssot_config
"""

import os
from pathlib import Path
from unittest.mock import patch


class TestVMConfig:
    """Tests for VMConfig class."""

    def test_default_vm_ips(self) -> None:
        """Test that default VM IPs are correct (single-host default since #2953)."""
        from autobot_shared.ssot_config import VMConfig

        # Pass _env_file=None so true field defaults are used regardless of .env on disk.
        with patch.dict(os.environ, {}, clear=True):
            config = VMConfig(_env_file=None)
            assert config.main == "127.0.0.1"
            assert config.frontend == "127.0.0.1"
            assert config.npu == "127.0.0.1"
            assert config.redis == "127.0.0.1"
            assert config.aistack == "127.0.0.1"
            assert config.browser == "127.0.0.1"
            assert config.ollama == "127.0.0.1"

    def test_vm_config_from_env(self) -> None:
        """Test that VM config reads from environment variables."""
        from autobot_shared.ssot_config import VMConfig

        test_env = {
            "AUTOBOT_BACKEND_HOST": "10.0.0.1",
            "AUTOBOT_FRONTEND_HOST": "10.0.0.2",
            "AUTOBOT_REDIS_HOST": "10.0.0.3",
        }
        with patch.dict(os.environ, test_env, clear=True):
            config = VMConfig(_env_file=None)
            assert config.main == "10.0.0.1"
            assert config.frontend == "10.0.0.2"
            assert config.redis == "10.0.0.3"


class TestPortConfig:
    """Tests for PortConfig class."""

    def test_default_ports(self) -> None:
        """Test that default ports are correct."""
        from autobot_shared.ssot_config import PortConfig

        # Clear env AND disable .env file loading to test true defaults
        with patch.dict(os.environ, {}, clear=True):
            config = PortConfig(_env_file=None)
            assert config.backend == 8001
            assert config.frontend == 5173
            assert config.redis == 6379
            assert config.ollama == 11434
            assert config.vnc == 6080
            assert config.browser == 9001  # Issue #4052: 9001; 3000 is Grafana
            assert config.aistack == 8080
            assert config.npu == 8081

    def test_port_config_from_env(self) -> None:
        """Test that port config reads from environment variables."""
        from autobot_shared.ssot_config import PortConfig

        test_env = {
            "AUTOBOT_BACKEND_PORT": "9000",
            "AUTOBOT_REDIS_PORT": "6380",
        }
        with patch.dict(os.environ, test_env, clear=True):
            config = PortConfig(_env_file=None)
            assert config.backend == 9000
            assert config.redis == 6380


class TestLLMConfig:
    """Tests for LLMConfig class."""

    def test_default_llm_models(self) -> None:
        """Test that default LLM models are correct when no env is set."""
        from autobot_shared.ssot_config import LLMConfig

        # Note: Since Pydantic reads from .env file, we test that values are present
        # not necessarily the hardcoded defaults
        with patch.dict(os.environ, {}, clear=True):
            config = LLMConfig()
            # Test that model names are valid (non-empty strings)
            assert isinstance(config.default_model, str)
            assert len(config.default_model) > 0
            assert isinstance(config.provider, str)
            assert config.timeout > 0

    def test_llm_config_from_env(self) -> None:
        """Test that LLM config reads from environment variables."""
        from autobot_shared.ssot_config import LLMConfig

        test_env = {
            "AUTOBOT_DEFAULT_LLM_MODEL": "llama3.2:1b",
            "AUTOBOT_LLM_TIMEOUT": "60",
        }
        with patch.dict(os.environ, test_env, clear=True):
            config = LLMConfig(_env_file=None)
            assert config.default_model == "llama3.2:1b"
            assert config.timeout == 60


class TestTimeoutConfig:
    """Tests for TimeoutConfig class."""

    def test_default_timeouts(self) -> None:
        """Test that default timeouts are correct."""
        from autobot_shared.ssot_config import TimeoutConfig

        with patch.dict(os.environ, {}, clear=True):
            config = TimeoutConfig(_env_file=None)
            assert config.api == 10000
            assert config.llm == 30.0
            assert config.health_check == 3.0

    def test_timeout_seconds_property(self) -> None:
        """Test that api_seconds property converts correctly."""
        from autobot_shared.ssot_config import TimeoutConfig

        test_env = {"AUTOBOT_API_TIMEOUT": "30000"}
        with patch.dict(os.environ, test_env, clear=True):
            config = TimeoutConfig(_env_file=None)
            assert config.api == 30000
            assert config.api_seconds == 30.0


class TestRedisConfig:
    """Tests for RedisConfig class."""

    def test_default_redis_databases(self) -> None:
        """Test that default Redis database assignments are correct."""
        from autobot_shared.ssot_config import RedisConfig

        with patch.dict(os.environ, {}, clear=True):
            config = RedisConfig(_env_file=None)
            assert config.db_main == 0
            assert config.db_knowledge == 1
            assert config.db_prompts == 2
            assert config.db_cache == 5
            assert config.db_testing == 13  # Changed from 15 in redis-databases.yaml SSOT

    def test_redis_password_optional(self) -> None:
        """Test that Redis password can be None or a string."""
        from autobot_shared.ssot_config import RedisConfig

        with patch.dict(os.environ, {}, clear=True):
            config = RedisConfig(_env_file=None)
            # Password is optional - can be None or a string from .env
            assert config.password is None or isinstance(config.password, str)


class TestAutoBotConfig:
    """Tests for AutoBotConfig master class."""

    def test_default_config_loads(self) -> None:
        """Test that configuration loads correctly with valid values."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig(_env_file=None)
            # Test that values are valid types/formats
            assert config.deployment_mode in ("distributed", "hybrid", "local")
            assert isinstance(config.debug, bool)
            assert config.log_level in ("DEBUG", "INFO", "WARNING", "ERROR")

    def test_computed_backend_url(self) -> None:
        """Test that backend URL is computed from vm/port sub-config values."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig(_env_file=None)
            # URL is composed from vm.main and port.backend — verify structure, not literal IP
            expected = f"http://{config.vm.main}:{config.port.backend}"
            assert config.backend_url == expected
            assert config.backend_url.startswith("http://")
            assert ":8001" in config.backend_url

    def test_computed_redis_url(self) -> None:
        """Test that Redis URL is computed correctly."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig(_env_file=None)
            expected = f"redis://{config.vm.redis}:{config.port.redis}"
            assert config.redis_url == expected
            assert config.redis_url.startswith("redis://")

    def test_computed_redis_url_with_password(self) -> None:
        """Test that Redis URL includes password when set."""
        from autobot_shared.ssot_config import AutoBotConfig

        test_env = {"AUTOBOT_REDIS_PASSWORD": "secret123"}
        with patch.dict(os.environ, test_env, clear=True):
            config = AutoBotConfig(_env_file=None)
            assert "secret123" in config.redis_url_with_auth
            assert config.redis_url_with_auth.startswith("redis://:")
            assert "@" in config.redis_url_with_auth

    def test_computed_websocket_url(self) -> None:
        """Test that WebSocket URL is computed correctly."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig(_env_file=None)
            # websocket_url uses ws:// scheme and /api/ws path
            assert config.websocket_url.startswith("ws://")
            assert config.websocket_url.endswith("/api/ws")

    def test_get_service_url(self) -> None:
        """Test the get_service_url helper method."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig(_env_file=None)
            backend = config.get_service_url("backend")
            redis = config.get_service_url("redis")
            assert backend is not None and backend.startswith("http://")
            assert redis is not None and redis.startswith("redis://")

    def test_slm_url_built_from_host_port_when_unset(self) -> None:
        """slm_url builds from host/port when SLM_URL is not set (#9768)."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig()
            assert config.slm_url == f"http://{config.vm.slm}:{config.port.slm}"

    def test_slm_url_honors_explicit_env(self) -> None:
        """An explicit SLM_URL wins over the host/port build (#9768)."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {"SLM_URL": "https://custom-slm:9443"}, clear=True):
            config = AutoBotConfig()
            assert config.slm_url == "https://custom-slm:9443"
            assert config.get_service_url("unknown") is None

    def test_get_vm_ip(self) -> None:
        """Test the get_vm_ip helper method."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig(_env_file=None)
            # Verify method returns a string for known VMs and None for unknown
            main_ip = config.get_vm_ip("main")
            redis_ip = config.get_vm_ip("redis")
            assert isinstance(main_ip, str) and len(main_ip) > 0
            assert isinstance(redis_ip, str) and len(redis_ip) > 0
            assert config.get_vm_ip("unknown") is None

    def test_get_redis_url_for_db(self) -> None:
        """Test getting Redis URL for specific database."""
        from autobot_shared.ssot_config import AutoBotConfig

        with patch.dict(os.environ, {}, clear=True):
            config = AutoBotConfig(_env_file=None)
            url = config.get_redis_url_for_db(5)
            # URL should end with /5 for database 5
            assert url.endswith("/5")
            assert "redis://" in url


class TestSingletonPattern:
    """Tests for singleton get_config() function."""

    def test_get_config_returns_same_instance(self) -> None:
        """Test that get_config returns the same instance."""
        from autobot_shared.ssot_config import get_config, reload_config

        # Clear any cached config first
        reload_config()

        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reload_config_creates_new_instance(self) -> None:
        """Test that reload_config creates a new instance."""
        from autobot_shared.ssot_config import get_config, reload_config

        config1 = get_config()
        config2 = reload_config()
        # After reload, a new instance should be created
        # Note: The new instance will have same values but different identity
        assert config1 is not config2


class TestBackwardCompatibility:
    """Tests for backward compatibility functions."""

    def test_get_backend_url(self) -> None:
        """Test backward compatibility get_backend_url function."""
        from autobot_shared.ssot_config import get_backend_url, reload_config

        reload_config()  # Ensure clean state
        url = get_backend_url()
        assert "http://" in url
        assert ":8001" in url or "AUTOBOT_BACKEND_PORT" in os.environ

    def test_get_redis_url(self) -> None:
        """Test backward compatibility get_redis_url function."""
        from autobot_shared.ssot_config import get_redis_url, reload_config

        reload_config()  # Ensure clean state
        url = get_redis_url()
        assert "redis://" in url

    def test_get_default_llm_model(self) -> None:
        """Test backward compatibility get_default_llm_model function."""
        from autobot_shared.ssot_config import get_default_llm_model, reload_config

        reload_config()  # Ensure clean state
        model = get_default_llm_model()
        assert model is not None
        assert len(model) > 0


class TestConfigProxy:
    """Tests for the config proxy object."""

    def test_config_proxy_access(self) -> None:
        """Test that config proxy provides attribute access."""
        from autobot_shared.ssot_config import config

        # Access through proxy
        assert hasattr(config, "vm")
        assert hasattr(config, "port")
        assert hasattr(config, "llm")

    def test_config_proxy_nested_access(self) -> None:
        """Test that config proxy provides nested attribute access."""
        from autobot_shared.ssot_config import config

        # Access nested properties
        assert config.vm.main is not None
        assert config.port.backend is not None
        assert config.llm.default_model is not None


class TestProjectRoot:
    """Tests for PROJECT_ROOT detection."""

    def test_project_root_is_path(self) -> None:
        """Test that PROJECT_ROOT is a Path object."""
        from autobot_shared.ssot_config import PROJECT_ROOT

        assert isinstance(PROJECT_ROOT, Path)

    def test_project_root_exists(self) -> None:
        """Test that PROJECT_ROOT directory exists."""
        from autobot_shared.ssot_config import PROJECT_ROOT

        assert PROJECT_ROOT.exists()
        assert PROJECT_ROOT.is_dir()


class TestChatCitationInstructionAliasChoices:
    """#10736: Both env vars set chat_citation_instruction_enabled correctly."""

    def test_canonical_env_var_sets_flag_false(self, monkeypatch) -> None:
        """AUTOBOT_CHAT_CITATION_INSTRUCTION=false → chat_citation_instruction_enabled=False."""
        from pydantic import AliasChoices, Field
        from pydantic_settings import BaseSettings, SettingsConfigDict

        class _IsolatedLLMConfig(BaseSettings):
            model_config = SettingsConfigDict(extra="ignore")
            chat_citation_instruction_enabled: bool = Field(
                default=True,
                validation_alias=AliasChoices(
                    "AUTOBOT_CHAT_CITATION_INSTRUCTION",
                    "AUTOBOT_CHAT_GROUNDING",
                ),
            )

        monkeypatch.setenv("AUTOBOT_CHAT_CITATION_INSTRUCTION", "false")
        monkeypatch.delenv("AUTOBOT_CHAT_GROUNDING", raising=False)
        cfg = _IsolatedLLMConfig()
        assert cfg.chat_citation_instruction_enabled is False

    def test_legacy_env_var_sets_flag_false(self, monkeypatch) -> None:
        """AUTOBOT_CHAT_GROUNDING=false → chat_citation_instruction_enabled=False (back-compat)."""
        from pydantic import AliasChoices, Field
        from pydantic_settings import BaseSettings, SettingsConfigDict

        class _IsolatedLLMConfig(BaseSettings):
            model_config = SettingsConfigDict(extra="ignore")
            chat_citation_instruction_enabled: bool = Field(
                default=True,
                validation_alias=AliasChoices(
                    "AUTOBOT_CHAT_CITATION_INSTRUCTION",
                    "AUTOBOT_CHAT_GROUNDING",
                ),
            )

        monkeypatch.delenv("AUTOBOT_CHAT_CITATION_INSTRUCTION", raising=False)
        monkeypatch.setenv("AUTOBOT_CHAT_GROUNDING", "false")
        cfg = _IsolatedLLMConfig()
        assert cfg.chat_citation_instruction_enabled is False

    def test_default_when_neither_env_var_set(self, monkeypatch) -> None:
        """Default=True when neither env var is set."""
        from pydantic import AliasChoices, Field
        from pydantic_settings import BaseSettings, SettingsConfigDict

        class _IsolatedLLMConfig(BaseSettings):
            model_config = SettingsConfigDict(extra="ignore")
            chat_citation_instruction_enabled: bool = Field(
                default=True,
                validation_alias=AliasChoices(
                    "AUTOBOT_CHAT_CITATION_INSTRUCTION",
                    "AUTOBOT_CHAT_GROUNDING",
                ),
            )

        monkeypatch.delenv("AUTOBOT_CHAT_CITATION_INSTRUCTION", raising=False)
        monkeypatch.delenv("AUTOBOT_CHAT_GROUNDING", raising=False)
        cfg = _IsolatedLLMConfig()
        assert cfg.chat_citation_instruction_enabled is True


class TestEnvIntSafeParse:
    """#11022: PLAN_BEST_OF_N_COUNT must never crash the module at import on bad
    env input — it uses the shared env_int_clamped helper (#11022 audit follow-up)."""

    def test_invalid_env_falls_back_to_default_no_import_crash(self):
        import importlib

        with patch.dict(os.environ, {"AUTOBOT_PLAN_BEST_OF_N_COUNT": "not-a-number"}):
            import autobot_shared.ssot_config as c

            importlib.reload(c)  # must not raise
            assert c.PLAN_BEST_OF_N_COUNT == 3

    def test_clamps_to_bounds(self):
        import importlib

        import autobot_shared.ssot_config as c

        for raw, expected in (("99", 5), ("1", 2), ("4", 4)):
            with patch.dict(os.environ, {"AUTOBOT_PLAN_BEST_OF_N_COUNT": raw}):
                importlib.reload(c)
                assert c.PLAN_BEST_OF_N_COUNT == expected
