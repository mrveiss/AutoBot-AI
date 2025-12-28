#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSOT Configuration Loader for Python
=====================================

Single Source of Truth - reads from .env file with AUTOBOT_ prefix.

This module provides typed configuration access across the entire backend.
All configuration values are defined in the master .env file and accessed
through Pydantic models for type safety and validation.

Usage:
    from src.config.ssot_config import get_config, config

    # Access VM IPs
    redis_ip = config.vm.redis
    backend_ip = config.vm.main

    # Access ports
    backend_port = config.port.backend

    # Access computed URLs
    backend_url = config.backend_url
    redis_url = config.redis_url

    # Access LLM settings
    default_model = config.llm.default_model

    # Access timeouts
    http_timeout = config.timeout.http

Issue: #601 - SSOT Phase 1: Foundation
Related: #599 - SSOT Configuration System Epic
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Determine project root for .env file location
def _find_project_root() -> Path:
    """Find the project root directory containing .env file."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".env").exists():
            return parent
    # Fallback to expected location
    return Path("/home/kali/Desktop/AutoBot")


PROJECT_ROOT = _find_project_root()

# Default model constants - single source of truth for fallback values
# These are used when .env doesn't specify a value
DEFAULT_LLM_MODEL = "mistral:7b-instruct"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text:latest"


class VMConfig(BaseSettings):
    """
    VM IP address configuration.

    Supports the 6-VM distributed architecture:
    - Main (WSL) - Backend API + VNC Desktop
    - Frontend (VM1) - Web interface
    - NPU Worker (VM2) - Hardware AI acceleration
    - Redis (VM3) - Data layer
    - AI Stack (VM4) - AI processing
    - Browser (VM5) - Web automation
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    main: str = Field(default="172.16.168.20", alias="AUTOBOT_BACKEND_HOST")
    frontend: str = Field(default="172.16.168.21", alias="AUTOBOT_FRONTEND_HOST")
    npu: str = Field(default="172.16.168.22", alias="AUTOBOT_NPU_WORKER_HOST")
    redis: str = Field(default="172.16.168.23", alias="AUTOBOT_REDIS_HOST")
    aistack: str = Field(default="172.16.168.24", alias="AUTOBOT_AI_STACK_HOST")
    browser: str = Field(default="172.16.168.25", alias="AUTOBOT_BROWSER_SERVICE_HOST")
    ollama: str = Field(default="127.0.0.1", alias="AUTOBOT_OLLAMA_HOST")


class PortConfig(BaseSettings):
    """Service port configuration."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend: int = Field(default=8001, alias="AUTOBOT_BACKEND_PORT")
    frontend: int = Field(default=5173, alias="AUTOBOT_FRONTEND_PORT")
    redis: int = Field(default=6379, alias="AUTOBOT_REDIS_PORT")
    ollama: int = Field(default=11434, alias="AUTOBOT_OLLAMA_PORT")
    vnc: int = Field(default=6080, alias="AUTOBOT_VNC_PORT")
    browser: int = Field(default=3000, alias="AUTOBOT_BROWSER_SERVICE_PORT")
    aistack: int = Field(default=8080, alias="AUTOBOT_AI_STACK_PORT")
    npu: int = Field(default=8081, alias="AUTOBOT_NPU_WORKER_PORT")
    prometheus: int = Field(default=9090, alias="AUTOBOT_PROMETHEUS_PORT")
    grafana: int = Field(default=3000, alias="AUTOBOT_GRAFANA_PORT")


class LLMConfig(BaseSettings):
    """LLM model configuration."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Primary models - all use DEFAULT_LLM_MODEL constant for consistency
    default_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_DEFAULT_LLM_MODEL"
    )
    embedding_model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL, alias="AUTOBOT_EMBEDDING_MODEL"
    )
    classification_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_CLASSIFICATION_MODEL"
    )
    reasoning_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_REASONING_MODEL"
    )
    rag_model: str = Field(default=DEFAULT_LLM_MODEL, alias="AUTOBOT_RAG_MODEL")
    coding_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_CODING_MODEL"
    )

    # Agent/workflow models - all use DEFAULT_LLM_MODEL constant
    orchestrator_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_ORCHESTRATOR_MODEL"
    )
    agent_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_AGENT_MODEL"
    )
    research_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_RESEARCH_MODEL"
    )
    analysis_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_ANALYSIS_MODEL"
    )
    planning_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_PLANNING_MODEL"
    )

    # Timeout (seconds)
    timeout: int = Field(default=30, alias="AUTOBOT_LLM_TIMEOUT")

    # Provider (for future multi-provider support)
    provider: str = Field(default="ollama", alias="AUTOBOT_LLM_PROVIDER")


class TimeoutConfig(BaseSettings):
    """
    Timeout configuration (in milliseconds for HTTP, seconds for LLM).

    Note: Frontend uses milliseconds, backend uses seconds for LLM.
    The config stores values as they appear in .env for consistency.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API timeouts (milliseconds)
    api: int = Field(default=10000, alias="AUTOBOT_API_TIMEOUT")
    api_retry_attempts: int = Field(default=3, alias="AUTOBOT_API_RETRY_ATTEMPTS")
    api_retry_delay: int = Field(default=1000, alias="AUTOBOT_API_RETRY_DELAY")

    # LLM timeout (seconds)
    llm: int = Field(default=30, alias="AUTOBOT_LLM_TIMEOUT")

    # Health check timeout (seconds)
    health_check: int = Field(default=3, alias="AUTOBOT_HEALTH_CHECK_TIMEOUT")

    # WebSocket timeout (seconds)
    websocket: int = Field(default=30, alias="AUTOBOT_WEBSOCKET_TIMEOUT")

    @property
    def api_seconds(self) -> float:
        """Get API timeout in seconds."""
        return self.api / 1000.0

    @property
    def http(self) -> int:
        """Alias for api timeout (milliseconds)."""
        return self.api

    @property
    def http_seconds(self) -> float:
        """Get HTTP timeout in seconds."""
        return self.api / 1000.0


class RedisConfig(BaseSettings):
    """Redis database configuration."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Enable/disable Redis
    enabled: bool = Field(default=True, alias="AUTOBOT_REDIS_ENABLED")

    # Database assignments
    db_main: int = Field(default=0, alias="AUTOBOT_REDIS_DB_MAIN")
    db_knowledge: int = Field(default=1, alias="AUTOBOT_REDIS_DB_KNOWLEDGE")
    db_prompts: int = Field(default=2, alias="AUTOBOT_REDIS_DB_PROMPTS")
    db_agents: int = Field(default=3, alias="AUTOBOT_REDIS_DB_AGENTS")
    db_metrics: int = Field(default=4, alias="AUTOBOT_REDIS_DB_METRICS")
    db_cache: int = Field(default=5, alias="AUTOBOT_REDIS_DB_CACHE")
    db_sessions: int = Field(default=6, alias="AUTOBOT_REDIS_DB_SESSIONS")
    db_tasks: int = Field(default=7, alias="AUTOBOT_REDIS_DB_TASKS")
    db_logs: int = Field(default=8, alias="AUTOBOT_REDIS_DB_LOGS")
    db_temp: int = Field(default=9, alias="AUTOBOT_REDIS_DB_TEMP")
    db_backup: int = Field(default=10, alias="AUTOBOT_REDIS_DB_BACKUP")
    db_testing: int = Field(default=15, alias="AUTOBOT_REDIS_DB_TESTING")

    # Security
    password: Optional[str] = Field(default=None, alias="AUTOBOT_REDIS_PASSWORD")


class FeatureConfig(BaseSettings):
    """Feature flags configuration."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    unified_config: bool = Field(default=True, alias="AUTOBOT_USE_UNIFIED_CONFIG")
    semantic_chunking: bool = Field(default=True, alias="AUTOBOT_SEMANTIC_CHUNKING")
    debug_mode: bool = Field(default=False, alias="AUTOBOT_DEBUG_MODE")
    hot_reload: bool = Field(default=True, alias="AUTOBOT_HOT_RELOAD")
    single_user_mode: bool = Field(default=True, alias="AUTOBOT_SINGLE_USER_MODE")


class AutoBotConfig(BaseSettings):
    """
    Master configuration - SINGLE SOURCE OF TRUTH.

    This class aggregates all configuration sections and provides
    computed properties for commonly used URLs.

    Usage:
        from src.config.ssot_config import get_config

        config = get_config()
        backend = config.backend_url  # http://172.16.168.20:8001
        redis = config.redis_url  # redis://172.16.168.23:6379
        model = config.llm.default_model  # mistral:7b-instruct
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configurations
    vm: VMConfig = Field(default_factory=VMConfig)
    port: PortConfig = Field(default_factory=PortConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    timeout: TimeoutConfig = Field(default_factory=TimeoutConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    feature: FeatureConfig = Field(default_factory=FeatureConfig)

    # Top-level settings
    deployment_mode: str = Field(default="distributed", alias="AUTOBOT_DEPLOYMENT_MODE")
    environment: str = Field(default="development", alias="AUTOBOT_ENVIRONMENT")
    debug: bool = Field(default=False, alias="AUTOBOT_DEBUG")
    log_level: str = Field(default="INFO", alias="AUTOBOT_LOG_LEVEL")

    # Computed URL properties for backward compatibility
    @property
    def backend_url(self) -> str:
        """Get the full backend API URL."""
        return f"http://{self.vm.main}:{self.port.backend}"

    @property
    def frontend_url(self) -> str:
        """Get the full frontend URL."""
        return f"http://{self.vm.frontend}:{self.port.frontend}"

    @property
    def redis_url(self) -> str:
        """Get the full Redis URL (without password)."""
        return f"redis://{self.vm.redis}:{self.port.redis}"

    @property
    def redis_url_with_auth(self) -> str:
        """Get the full Redis URL with password if configured."""
        if self.redis.password:
            return f"redis://:{self.redis.password}@{self.vm.redis}:{self.port.redis}"
        return self.redis_url

    @property
    def ollama_url(self) -> str:
        """Get the full Ollama API URL."""
        return f"http://{self.vm.ollama}:{self.port.ollama}"

    @property
    def websocket_url(self) -> str:
        """Get the WebSocket URL for real-time communication."""
        return f"ws://{self.vm.main}:{self.port.backend}/ws"

    @property
    def aistack_url(self) -> str:
        """Get the AI Stack service URL."""
        return f"http://{self.vm.aistack}:{self.port.aistack}"

    @property
    def npu_worker_url(self) -> str:
        """Get the NPU Worker service URL."""
        return f"http://{self.vm.npu}:{self.port.npu}"

    @property
    def browser_service_url(self) -> str:
        """Get the Browser automation service URL."""
        return f"http://{self.vm.browser}:{self.port.browser}"

    @property
    def vnc_url(self) -> str:
        """Get the VNC desktop URL."""
        return f"http://{self.vm.main}:{self.port.vnc}/vnc.html"

    def get_redis_url_for_db(self, db_number: int) -> str:
        """Get Redis URL for a specific database number."""
        base = self.redis_url_with_auth
        return f"{base}/{db_number}"

    def get_service_url(self, service_name: str) -> Optional[str]:
        """
        Get service URL by name.

        Args:
            service_name: Name of service (backend, frontend, redis, ollama, etc.)

        Returns:
            Service URL or None if not found
        """
        url_map = {
            "backend": self.backend_url,
            "frontend": self.frontend_url,
            "redis": self.redis_url,
            "ollama": self.ollama_url,
            "websocket": self.websocket_url,
            "aistack": self.aistack_url,
            "ai_stack": self.aistack_url,
            "npu": self.npu_worker_url,
            "npu_worker": self.npu_worker_url,
            "browser": self.browser_service_url,
            "vnc": self.vnc_url,
        }
        return url_map.get(service_name.lower())

    def get_vm_ip(self, vm_name: str) -> Optional[str]:
        """
        Get VM IP address by name.

        Args:
            vm_name: Name of VM (main, frontend, redis, etc.)

        Returns:
            IP address or None if not found
        """
        vm_map = {
            "main": self.vm.main,
            "frontend": self.vm.frontend,
            "npu": self.vm.npu,
            "npu_worker": self.vm.npu,
            "redis": self.vm.redis,
            "aistack": self.vm.aistack,
            "ai_stack": self.vm.aistack,
            "browser": self.vm.browser,
            "ollama": self.vm.ollama,
        }
        return vm_map.get(vm_name.lower())


@lru_cache(maxsize=1)
def get_config() -> AutoBotConfig:
    """
    Get singleton configuration instance.

    Uses LRU cache to ensure only one instance is created.
    The configuration is loaded from .env file on first access.

    Returns:
        AutoBotConfig instance with all configuration loaded
    """
    return AutoBotConfig()


def reload_config() -> AutoBotConfig:
    """
    Force reload of configuration.

    Clears the cached config and creates a new instance.
    Use this when .env file has changed and you need fresh values.

    Returns:
        Fresh AutoBotConfig instance
    """
    get_config.cache_clear()
    return get_config()


# Convenience export - lazy singleton
# This allows: from src.config.ssot_config import config
# while still supporting get_config() for explicit access
class _ConfigProxy:
    """Lazy proxy for config singleton."""

    def __getattr__(self, name):
        return getattr(get_config(), name)


config = _ConfigProxy()


# Backward compatibility exports
# These provide drop-in compatibility with NetworkConstants usage patterns
def get_backend_url() -> str:
    """Get backend URL (backward compatibility)."""
    return get_config().backend_url


def get_redis_url() -> str:
    """Get Redis URL (backward compatibility)."""
    return get_config().redis_url


def get_ollama_url() -> str:
    """Get Ollama URL (backward compatibility)."""
    return get_config().ollama_url


def get_default_llm_model() -> str:
    """Get default LLM model name (backward compatibility)."""
    return get_config().llm.default_model


# Export commonly used values at module level for convenience
__all__ = [
    "AutoBotConfig",
    "VMConfig",
    "PortConfig",
    "LLMConfig",
    "TimeoutConfig",
    "RedisConfig",
    "FeatureConfig",
    "get_config",
    "reload_config",
    "config",
    # Backward compatibility
    "get_backend_url",
    "get_redis_url",
    "get_ollama_url",
    "get_default_llm_model",
    "PROJECT_ROOT",
]
