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
    from autobot_shared.ssot_config import get_config, config

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
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Determine project root for .env file location
def _find_project_root() -> Path:
    """Find the project root directory containing .env file."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".env").exists():
            return parent
    # Fallback to runtime location (env var or /opt/autobot)
    return Path(os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"))


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
    slm: str = Field(default="172.16.168.19", alias="AUTOBOT_SLM_HOST")  # Issue #768
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
    slm: int = Field(default=8000, alias="AUTOBOT_SLM_PORT")  # Issue #768
    prometheus: int = Field(default=9090, alias="AUTOBOT_PROMETHEUS_PORT")
    grafana: int = Field(default=3000, alias="AUTOBOT_GRAFANA_PORT")


class LLMConfig(BaseSettings):
    """
    LLM model configuration with multi-provider support.

    Supports multiple LLM providers with different endpoints:
    - Ollama (local): http://127.0.0.1:11434
    - OpenAI: https://api.openai.com/v1
    - Anthropic: https://api.anthropic.com/v1
    - Custom providers via environment variables

    Each model type can specify its own provider via AUTOBOT_{MODEL}_PROVIDER
    environment variables, defaulting to the main AUTOBOT_LLM_PROVIDER.
    """

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
    coding_model: str = Field(default=DEFAULT_LLM_MODEL, alias="AUTOBOT_CODING_MODEL")

    # Agent/workflow models - all use DEFAULT_LLM_MODEL constant
    orchestrator_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_ORCHESTRATOR_MODEL"
    )
    agent_model: str = Field(default=DEFAULT_LLM_MODEL, alias="AUTOBOT_AGENT_MODEL")
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

    # Default provider for all models (can be overridden per-model)
    provider: str = Field(default="ollama", alias="AUTOBOT_LLM_PROVIDER")

    # Provider-specific endpoints (each provider can have its own URL)
    ollama_endpoint: str = Field(
        default="http://127.0.0.1:11434", alias="AUTOBOT_OLLAMA_ENDPOINT"
    )
    openai_endpoint: str = Field(
        default="https://api.openai.com/v1", alias="AUTOBOT_OPENAI_ENDPOINT"
    )
    anthropic_endpoint: str = Field(
        default="https://api.anthropic.com/v1", alias="AUTOBOT_ANTHROPIC_ENDPOINT"
    )
    custom_endpoint: str = Field(default="", alias="AUTOBOT_CUSTOM_LLM_ENDPOINT")

    # API keys (optional - can also come from provider-specific env vars)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # LlamaIndex-specific configuration for RAG/vectorization
    # These are explicit settings - no fallbacks. Must be configured correctly.
    llamaindex_llm_provider: str = Field(
        default="ollama", alias="AUTOBOT_LLAMAINDEX_LLM_PROVIDER"
    )
    llamaindex_llm_endpoint: str = Field(
        default="http://127.0.0.1:11434", alias="AUTOBOT_LLAMAINDEX_LLM_ENDPOINT"
    )
    llamaindex_llm_model: str = Field(
        default=DEFAULT_LLM_MODEL, alias="AUTOBOT_LLAMAINDEX_LLM_MODEL"
    )
    llamaindex_embedding_provider: str = Field(
        default="ollama", alias="AUTOBOT_LLAMAINDEX_EMBEDDING_PROVIDER"
    )
    llamaindex_embedding_endpoint: str = Field(
        default="http://127.0.0.1:11434", alias="AUTOBOT_LLAMAINDEX_EMBEDDING_ENDPOINT"
    )

    def get_provider_for_agent(self, agent_id: str) -> str:
        """
        Get the LLM provider for a specific agent.

        Looks up AUTOBOT_{AGENT_ID}_PROVIDER environment variable.
        Falls back to AUTOBOT_LLM_PROVIDER if not set.

        Args:
            agent_id: Agent identifier (e.g., 'orchestrator', 'research', 'code_analysis')

        Returns:
            Provider name (ollama, openai, anthropic, custom)

        Example:
            # In .env:
            AUTOBOT_RESEARCH_PROVIDER=openai
            AUTOBOT_CODE_ANALYSIS_PROVIDER=anthropic

            # In code:
            provider = config.llm.get_provider_for_agent("research")  # Returns "openai"
            provider = config.llm.get_provider_for_agent("chat")  # Returns default provider
        """
        # Check for agent-specific provider override via environment
        env_key = f"AUTOBOT_{agent_id.upper()}_PROVIDER"
        agent_provider = os.environ.get(env_key, "")
        if agent_provider:
            return agent_provider
        # Fall back to default provider
        return self.provider

    def get_endpoint_for_agent(self, agent_id: str) -> str:
        """
        Get the LLM API endpoint URL for a specific agent.

        First checks for agent-specific endpoint (AUTOBOT_{AGENT_ID}_ENDPOINT),
        then falls back to provider endpoint based on agent's provider setting.

        Args:
            agent_id: Agent identifier (e.g., 'orchestrator', 'research', 'code_analysis')

        Returns:
            API endpoint URL for the agent

        Example:
            # In .env:
            AUTOBOT_RESEARCH_PROVIDER=openai
            AUTOBOT_CODE_ANALYSIS_ENDPOINT=http://custom-claude-proxy:8080

            # In code:
            endpoint = config.llm.get_endpoint_for_agent("research")  # Returns OpenAI endpoint
            endpoint = config.llm.get_endpoint_for_agent("code_analysis")  # Returns custom endpoint
        """
        # Check for agent-specific endpoint override
        env_key = f"AUTOBOT_{agent_id.upper()}_ENDPOINT"
        agent_endpoint = os.environ.get(env_key, "")
        if agent_endpoint:
            return agent_endpoint

        # Get provider for this agent and return its endpoint
        provider = self.get_provider_for_agent(agent_id)
        return self.get_endpoint_for_provider(provider)

    def get_model_for_agent(self, agent_id: str) -> str:
        """
        Get the LLM model name for a specific agent.

        Looks up AUTOBOT_{AGENT_ID}_MODEL environment variable.
        Falls back to AUTOBOT_DEFAULT_LLM_MODEL if not set.

        Args:
            agent_id: Agent identifier (e.g., 'orchestrator', 'research', 'code_analysis')

        Returns:
            Model name (e.g., 'gpt-4', 'claude-3-opus', 'mistral:7b-instruct')

        Example:
            # In .env:
            AUTOBOT_RESEARCH_MODEL=gpt-4-turbo
            AUTOBOT_CODE_ANALYSIS_MODEL=claude-3-opus-20240229

            # In code:
            model = config.llm.get_model_for_agent("research")  # Returns "gpt-4-turbo"
            model = config.llm.get_model_for_agent("chat")  # Returns default model
        """
        # Check for agent-specific model override via environment
        env_key = f"AUTOBOT_{agent_id.upper()}_MODEL"
        agent_model = os.environ.get(env_key, "")
        if agent_model:
            return agent_model
        # Fall back to default model
        return self.default_model

    def get_agent_config(self, agent_id: str) -> dict:
        """
        Get complete LLM configuration for a specific agent.

        Returns a dictionary with provider, endpoint, model, and API key
        for the specified agent.

        Args:
            agent_id: Agent identifier (e.g., 'orchestrator', 'research', 'code_analysis')

        Returns:
            Dict with keys: provider, endpoint, model, api_key, timeout

        Example:
            config = config.llm.get_agent_config("research")
            # Returns: {
            #     "provider": "openai",
            #     "endpoint": "https://api.openai.com/v1",
            #     "model": "gpt-4-turbo",
            #     "api_key": "sk-...",
            #     "timeout": 30
            # }
        """
        provider = self.get_provider_for_agent(agent_id)
        return {
            "provider": provider,
            "endpoint": self.get_endpoint_for_agent(agent_id),
            "model": self.get_model_for_agent(agent_id),
            "api_key": self._get_api_key_for_provider(provider),
            "timeout": self.timeout,
        }

    def _get_api_key_for_provider(self, provider: str) -> str:
        """Get API key for a specific provider."""
        if provider.lower() == "openai":
            return self.openai_api_key
        elif provider.lower() == "anthropic":
            return self.anthropic_api_key
        # Ollama and custom providers may use different auth mechanisms
        return ""

    def get_endpoint_for_provider(self, provider: str) -> str:
        """
        Get the API endpoint URL for a specific provider.

        Args:
            provider: Provider name (ollama, openai, anthropic, custom)

        Returns:
            API endpoint URL
        """
        endpoints = {
            "ollama": self.ollama_endpoint,
            "openai": self.openai_endpoint,
            "anthropic": self.anthropic_endpoint,
            "custom": self.custom_endpoint,
        }
        return endpoints.get(provider.lower(), self.ollama_endpoint)

    # Backward compatibility aliases
    def get_provider_for_model(self, model_type: str) -> str:
        """Alias for get_provider_for_agent for backward compatibility."""
        return self.get_provider_for_agent(model_type)

    def get_endpoint_for_model(self, model_type: str) -> str:
        """
        Get the API endpoint URL for a specific model type.

        Args:
            model_type: Model type (embedding, orchestrator, research, coding, etc.)

        Returns:
            API endpoint URL for the model's provider
        """
        provider = self.get_provider_for_model(model_type)
        return self.get_endpoint_for_provider(provider)


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


class CacheCoordinatorConfig(BaseSettings):
    """
    Cache coordinator configuration for memory pressure management.

    Controls automatic eviction when system memory is under pressure.
    The coordinator monitors memory usage and triggers cache eviction
    across all caches to maintain performance and prevent OOM conditions.

    Issue: #743 - Memory Optimization (Phase 3.1)
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    pressure_threshold: float = Field(
        default=0.80,
        alias="AUTOBOT_CACHE_COORDINATOR_PRESSURE_THRESHOLD",
        description="Trigger eviction at this memory usage percentage (0.0-1.0)",
    )
    eviction_ratio: float = Field(
        default=0.20,
        alias="AUTOBOT_CACHE_COORDINATOR_EVICTION_RATIO",
        description="Percentage of each cache to evict during pressure (0.0-1.0)",
    )
    check_interval: int = Field(
        default=30,
        alias="AUTOBOT_CACHE_COORDINATOR_CHECK_INTERVAL",
        description="Seconds between memory pressure checks",
    )


class CacheRedisConfig(BaseSettings):
    """
    Redis connection pool configuration for caching.

    Controls connection pooling behavior for Redis cache operations.
    Separate from main Redis config to allow independent tuning.

    Issue: #743 - Memory Optimization (Phase 3.1)
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_connections: int = Field(
        default=20,
        alias="AUTOBOT_CACHE_REDIS_MAX_CONNECTIONS",
        description="Maximum Redis connections in pool",
    )
    socket_timeout: float = Field(
        default=5.0,
        alias="AUTOBOT_CACHE_REDIS_SOCKET_TIMEOUT",
        description="Socket timeout in seconds",
    )
    socket_connect_timeout: float = Field(
        default=5.0,
        alias="AUTOBOT_CACHE_REDIS_SOCKET_CONNECT_TIMEOUT",
        description="Socket connection timeout in seconds",
    )


class CacheL1Config(BaseSettings):
    """
    L1 (in-memory) cache size configuration.

    Controls maximum number of items stored in each in-memory LRU cache.
    These are fast but consume RAM, so sizes should be tuned based on
    available memory and usage patterns.

    Issue: #743 - Memory Optimization (Phase 3.1)
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    lru_memory: int = Field(
        default=1000,
        alias="AUTOBOT_CACHE_L1_LRU_MEMORY",
        description="Max items in LRU memory cache",
    )
    embedding: int = Field(
        default=1000,
        alias="AUTOBOT_CACHE_L1_EMBEDDING",
        description="Max items in embedding cache",
    )
    llm_response: int = Field(
        default=100,
        alias="AUTOBOT_CACHE_L1_LLM_RESPONSE",
        description="Max items in LLM response cache",
    )
    ast: int = Field(
        default=1000, alias="AUTOBOT_CACHE_L1_AST", description="Max items in AST cache"
    )
    file_content: int = Field(
        default=500,
        alias="AUTOBOT_CACHE_L1_FILE_CONTENT",
        description="Max items in file content cache",
    )
    weak_cache: int = Field(
        default=128,
        alias="AUTOBOT_CACHE_L1_WEAK_CACHE",
        description="Max items in weak reference cache",
    )


class CacheL2Config(BaseSettings):
    """
    L2 (Redis) cache TTL configuration.

    Controls time-to-live (in seconds) for different types of cached data in Redis.
    Longer TTLs reduce recomputation but may serve stale data.
    Shorter TTLs keep data fresh but increase computation load.

    Issue: #743 - Memory Optimization (Phase 3.1)
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_response: int = Field(
        default=300,
        alias="AUTOBOT_CACHE_L2_LLM_RESPONSE",
        description="TTL for LLM responses in seconds (5 minutes)",
    )
    knowledge: int = Field(
        default=300,
        alias="AUTOBOT_CACHE_L2_KNOWLEDGE",
        description="TTL for knowledge base entries in seconds (5 minutes)",
    )
    session: int = Field(
        default=300,
        alias="AUTOBOT_CACHE_L2_SESSION",
        description="TTL for session data in seconds (5 minutes)",
    )
    user_prefs: int = Field(
        default=3600,
        alias="AUTOBOT_CACHE_L2_USER_PREFS",
        description="TTL for user preferences in seconds (1 hour)",
    )
    computed: int = Field(
        default=7200,
        alias="AUTOBOT_CACHE_L2_COMPUTED",
        description="TTL for computed results in seconds (2 hours)",
    )


class CacheConfig(BaseSettings):
    """
    Master cache configuration for AutoBot.

    Aggregates all cache-related settings including coordinator,
    Redis connection pool, L1 (in-memory) sizes, and L2 (Redis) TTLs.

    Usage:
        from autobot_shared.ssot_config import config

        # Access cache settings
        pressure = config.cache.coordinator.pressure_threshold
        max_conns = config.cache.redis.max_connections
        lru_size = config.cache.l1.lru_memory
        ttl = config.cache.l2.llm_response

    Issue: #743 - Memory Optimization (Phase 3.1)
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configurations
    coordinator: CacheCoordinatorConfig = Field(default_factory=CacheCoordinatorConfig)
    redis: CacheRedisConfig = Field(default_factory=CacheRedisConfig)
    l1: CacheL1Config = Field(default_factory=CacheL1Config)
    l2: CacheL2Config = Field(default_factory=CacheL2Config)


class PermissionMode(str, Enum):
    """
    Permission modes for command execution control.

    Aligned with Claude Code's permission model:
    - DEFAULT: Standard risk-based approval (current behavior)
    - ACCEPT_EDITS: Auto-approve file edit operations for session
    - PLAN: Read-only mode - no modifications allowed
    - DONT_ASK: Auto-approve all commands (ADMIN ONLY - dangerous)
    - BYPASS: Skip all security checks (ADMIN ONLY - very dangerous)
    """

    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    DONT_ASK = "dontAsk"
    BYPASS = "bypassPermissions"


class PermissionAction(str, Enum):
    """Permission actions for rules."""

    ALLOW = "allow"  # Auto-approve matching commands
    ASK = "ask"  # Always prompt for matching commands
    DENY = "deny"  # Block matching commands


class PermissionConfig(BaseSettings):
    """
    Permission system configuration - Claude Code style.

    Provides flexible, user-configurable control over command execution
    with pattern-based rules and per-project approval memory.

    Security:
    - Normal users can use DEFAULT, ACCEPT_EDITS, and PLAN modes
    - DONT_ASK and BYPASS modes require admin privileges
    - Dangerous pattern overrides (ALLOW for rm -rf, etc.) require admin
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Enable permission system v2 (feature flag)
    enabled: bool = Field(
        default=False,
        alias="AUTOBOT_PERMISSION_SYSTEM_V2",
        description="Enable Claude Code-style permission system",
    )

    # Global permission mode
    mode: PermissionMode = Field(
        default=PermissionMode.DEFAULT,
        alias="AUTOBOT_PERMISSION_MODE",
        description="Default permission mode for command approval",
    )

    # Per-project approval memory
    approval_memory_enabled: bool = Field(
        default=True,
        alias="AUTOBOT_APPROVAL_MEMORY_ENABLED",
        description="Remember approved commands per project",
    )

    # Approval memory TTL in seconds (default: 30 days)
    approval_memory_ttl: int = Field(
        default=2592000,
        alias="AUTOBOT_APPROVAL_MEMORY_TTL",
        description="How long to remember approved commands (seconds)",
    )

    # Redis database for permission storage
    redis_db: int = Field(
        default=11,
        alias="AUTOBOT_REDIS_DB_PERMISSIONS",
        description="Redis database for permission rules and memory",
    )

    # Permission rules file path (relative to project root)
    rules_file: str = Field(
        default="config/permission_rules.yaml",
        alias="AUTOBOT_PERMISSION_RULES_FILE",
        description="Path to permission rules YAML file",
    )

    # Admin-only modes - users without admin role cannot use these
    ADMIN_ONLY_MODES: List[PermissionMode] = [
        PermissionMode.DONT_ASK,
        PermissionMode.BYPASS,
    ]

    def is_admin_only_mode(self, mode: PermissionMode) -> bool:
        """Check if a mode requires admin privileges."""
        return mode in self.ADMIN_ONLY_MODES

    def get_allowed_modes_for_role(self, is_admin: bool) -> List[PermissionMode]:
        """Get list of permission modes allowed for a role."""
        if is_admin:
            return list(PermissionMode)
        return [m for m in PermissionMode if m not in self.ADMIN_ONLY_MODES]


class TLSMode(str, Enum):
    """TLS operation modes."""

    DISABLED = "disabled"
    OPTIONAL = "optional"
    REQUIRED = "required"


class TLSConfig(BaseSettings):
    """TLS/PKI Configuration for secure communications.

    Issue #164: Added frontend TLS support for HTTPS on 172.16.168.21.
    TLS certificates are managed and deployed via SLM (172.16.168.19).
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: TLSMode = Field(default=TLSMode.DISABLED, alias="AUTOBOT_TLS_MODE")
    cert_dir: str = Field(default="certs", alias="AUTOBOT_TLS_CERT_DIR")
    ca_cert: str = Field(default="certs/ca/ca-cert.pem", alias="AUTOBOT_TLS_CA_CERT")
    remote_cert_dir: str = Field(
        default="/etc/autobot/certs", alias="AUTOBOT_TLS_REMOTE_CERT_DIR"
    )
    # Service-specific TLS settings
    redis_tls_enabled: bool = Field(default=False, alias="AUTOBOT_REDIS_TLS_ENABLED")
    redis_tls_port: int = Field(default=6380, alias="AUTOBOT_REDIS_TLS_PORT")
    backend_tls_enabled: bool = Field(
        default=False, alias="AUTOBOT_BACKEND_TLS_ENABLED"
    )
    backend_tls_port: int = Field(default=8443, alias="AUTOBOT_BACKEND_TLS_PORT")
    # Issue #164: Frontend TLS (HTTPS) support
    frontend_tls_enabled: bool = Field(
        default=False, alias="AUTOBOT_FRONTEND_TLS_ENABLED"
    )
    frontend_tls_port: int = Field(default=443, alias="AUTOBOT_FRONTEND_TLS_PORT")
    # SLM TLS settings (admin server)
    slm_tls_enabled: bool = Field(default=False, alias="AUTOBOT_SLM_TLS_ENABLED")
    slm_tls_port: int = Field(default=443, alias="AUTOBOT_SLM_TLS_PORT")

    @property
    def is_enabled(self) -> bool:
        """Check if TLS is enabled."""
        return self.mode != TLSMode.DISABLED

    @property
    def any_service_tls_enabled(self) -> bool:
        """Check if any service has TLS enabled."""
        return (
            self.redis_tls_enabled
            or self.backend_tls_enabled
            or self.frontend_tls_enabled
            or self.slm_tls_enabled
        )


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
    permission_system_v2: bool = Field(
        default=False, alias="AUTOBOT_PERMISSION_SYSTEM_V2"
    )


class AutoBotConfig(BaseSettings):
    """
    Master configuration - SINGLE SOURCE OF TRUTH.

    This class aggregates all configuration sections and provides
    computed properties for commonly used URLs.

    Usage:
        from autobot_shared.ssot_config import get_config

        config = get_config()
        backend = config.backend_url  # http://172.16.168.20:8001
        redis = config.redis_url  # redis://172.16.168.23:6379
        model = config.llm.default_model  # mistral:7b-instruct
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore={
            "PORT",
            "HOST",
        },  # Issue #858: Ignore uvicorn's env vars to prevent conflicts
    )

    # Sub-configurations
    vm: VMConfig = Field(default_factory=VMConfig)
    port: PortConfig = Field(default_factory=PortConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    timeout: TimeoutConfig = Field(default_factory=TimeoutConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    tls: TLSConfig = Field(default_factory=TLSConfig)
    feature: FeatureConfig = Field(default_factory=FeatureConfig)
    permission: PermissionConfig = Field(default_factory=PermissionConfig)

    # Top-level settings
    deployment_mode: str = Field(default="distributed", alias="AUTOBOT_DEPLOYMENT_MODE")
    environment: str = Field(default="development", alias="AUTOBOT_ENVIRONMENT")
    debug: bool = Field(default=False, alias="AUTOBOT_DEBUG")
    log_level: str = Field(default="INFO", alias="AUTOBOT_LOG_LEVEL")

    # Issue #858: Handle PORT env var from uvicorn without breaking port config
    @field_validator("port", mode="before")
    @classmethod
    def handle_port_env_var(cls, v):
        """Convert integer PORT (from uvicorn) to PortConfig object."""
        if isinstance(v, int):
            # PORT env var from uvicorn - ignore it and return default PortConfig
            return PortConfig()
        return v

    # Computed URL properties for backward compatibility
    # Issue #164: Support HTTPS when TLS is enabled
    @property
    def backend_url(self) -> str:
        """Get the full backend API URL (HTTP or HTTPS based on TLS config)."""
        if self.tls.backend_tls_enabled:
            return f"https://{self.vm.main}:{self.tls.backend_tls_port}"
        return f"http://{self.vm.main}:{self.port.backend}"

    @property
    def frontend_url(self) -> str:
        """Get the full frontend URL (HTTP or HTTPS based on TLS config)."""
        if self.tls.frontend_tls_enabled:
            return f"https://{self.vm.frontend}:{self.tls.frontend_tls_port}"
        return f"http://{self.vm.frontend}:{self.port.frontend}"

    @property
    def redis_url(self) -> str:
        """Get the full Redis URL (without password)."""
        if self.tls.redis_tls_enabled:
            return f"rediss://{self.vm.redis}:{self.tls.redis_tls_port}"
        return f"redis://{self.vm.redis}:{self.port.redis}"

    @property
    def redis_url_with_auth(self) -> str:
        """Get the full Redis URL with password if configured."""
        if self.tls.redis_tls_enabled:
            scheme = "rediss"
            port = self.tls.redis_tls_port
        else:
            scheme = "redis"
            port = self.port.redis
        if self.redis.password:
            return f"{scheme}://:{self.redis.password}@{self.vm.redis}:{port}"
        return f"{scheme}://{self.vm.redis}:{port}"

    @property
    def ollama_url(self) -> str:
        """
        Get the full Ollama API URL.

        Uses llm.ollama_endpoint if configured, otherwise constructs from vm.ollama + port.ollama.
        This allows flexibility: use the configured endpoint or build from host/port.
        """
        # If ollama_endpoint is set and not the default, use it directly
        if (
            self.llm.ollama_endpoint
            and self.llm.ollama_endpoint != "http://127.0.0.1:11434"
        ):
            return self.llm.ollama_endpoint
        # Otherwise construct from VM config (allows using different Ollama host)
        return f"http://{self.vm.ollama}:{self.port.ollama}"

    def get_llm_endpoint(self, model_type: str = "default") -> str:
        """
        Get the LLM API endpoint for a specific model type.

        This is the recommended method for getting LLM endpoints as it supports
        multi-provider configurations where different models use different providers.

        Args:
            model_type: Model type (embedding, orchestrator, research, coding, default, etc.)

        Returns:
            API endpoint URL for the model's provider

        Usage:
            endpoint = config.get_llm_endpoint("embedding")  # May return OpenAI endpoint
            endpoint = config.get_llm_endpoint("coding")     # May return Anthropic endpoint
            endpoint = config.get_llm_endpoint()             # Returns default provider endpoint
        """
        return self.llm.get_endpoint_for_model(model_type)

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

    @property
    def slm_url(self) -> str:
        """Get the SLM Admin server URL (Issue #768)."""
        if self.tls.slm_tls_enabled:
            return f"https://{self.vm.slm}:{self.tls.slm_tls_port}"
        return f"http://{self.vm.slm}:{self.port.slm}"

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
            "slm": self.slm_url,  # Issue #768
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

    @property
    def vm_definitions(self) -> Dict[str, str]:
        """
        Get VM definitions as a dictionary.

        Returns dict compatible with PKI and other systems that need
        VM name -> IP mappings.

        Issue #694: Centralized VM definitions for config consolidation.
        """
        return {
            "main-host": self.vm.main,
            "frontend": self.vm.frontend,
            "npu-worker": self.vm.npu,
            "redis": self.vm.redis,
            "ai-stack": self.vm.aistack,
            "browser": self.vm.browser,
        }


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
# This allows: from autobot_shared.ssot_config import config
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


# =============================================================================
# Agent-Specific Configuration Functions (EXPLICIT - NO FALLBACKS)
# =============================================================================
#
# These functions provide explicit configuration for agents.
# Each agent MUST have its configuration explicitly set in .env:
#   - AUTOBOT_{AGENT_ID}_PROVIDER
#   - AUTOBOT_{AGENT_ID}_ENDPOINT
#   - AUTOBOT_{AGENT_ID}_MODEL
#
# If any setting is missing, a ConfigurationError is raised.
# This enforces explicit configuration - no silent fallbacks that hide misconfigurations.
# =============================================================================


class AgentConfigurationError(Exception):
    """Raised when agent LLM configuration is missing or invalid."""


def get_agent_llm_config_explicit(agent_id: str) -> dict:
    """
    Get complete LLM configuration for a specific agent (EXPLICIT - NO FALLBACKS).

    Each agent MUST have its own provider, endpoint, and model via environment variables:
    - AUTOBOT_{AGENT_ID}_PROVIDER (e.g., AUTOBOT_ORCHESTRATOR_PROVIDER=ollama)
    - AUTOBOT_{AGENT_ID}_ENDPOINT (e.g., AUTOBOT_ORCHESTRATOR_ENDPOINT=http://127.0.0.1:11434)
    - AUTOBOT_{AGENT_ID}_MODEL (e.g., AUTOBOT_ORCHESTRATOR_MODEL=mistral:7b-instruct)

    Raises AgentConfigurationError if any setting is missing.

    Args:
        agent_id: The agent identifier (e.g., "orchestrator", "chat", "rag")

    Returns:
        Dict with provider, endpoint, model, api_key, and timeout

    Raises:
        AgentConfigurationError: If any required setting is missing
    """
    provider = get_agent_provider_explicit(agent_id)
    endpoint = get_agent_endpoint_explicit(agent_id)
    model = get_agent_model_explicit(agent_id)

    # Get API key for provider
    cfg = get_config()
    api_key = ""
    if provider.lower() == "openai":
        api_key = cfg.llm.openai_api_key
    elif provider.lower() == "anthropic":
        api_key = cfg.llm.anthropic_api_key

    return {
        "provider": provider,
        "endpoint": endpoint,
        "model": model,
        "api_key": api_key,
        "timeout": cfg.llm.timeout,
    }


def get_agent_endpoint_explicit(agent_id: str) -> str:
    """
    Get LLM API endpoint URL for a specific agent (EXPLICIT - NO FALLBACK).

    Reads AUTOBOT_{AGENT_ID}_ENDPOINT from environment.
    Raises AgentConfigurationError if not set.

    Args:
        agent_id: The agent identifier

    Returns:
        API endpoint URL for the agent's LLM provider

    Raises:
        AgentConfigurationError: If AUTOBOT_{AGENT_ID}_ENDPOINT is not set
    """
    env_key = f"AUTOBOT_{agent_id.upper()}_ENDPOINT"
    endpoint = os.environ.get(env_key, "")
    if not endpoint:
        raise AgentConfigurationError(
            f"Agent '{agent_id}' requires explicit LLM endpoint configuration. "
            f"Set {env_key} in .env file. "
            f"Example: {env_key}=http://127.0.0.1:11434"
        )
    return endpoint


def get_agent_model_explicit(agent_id: str) -> str:
    """
    Get LLM model name for a specific agent (EXPLICIT - NO FALLBACK).

    Reads AUTOBOT_{AGENT_ID}_MODEL from environment.
    Raises AgentConfigurationError if not set.

    Args:
        agent_id: The agent identifier

    Returns:
        Model name for the agent

    Raises:
        AgentConfigurationError: If AUTOBOT_{AGENT_ID}_MODEL is not set
    """
    env_key = f"AUTOBOT_{agent_id.upper()}_MODEL"
    model = os.environ.get(env_key, "")
    if not model:
        raise AgentConfigurationError(
            f"Agent '{agent_id}' requires explicit LLM model configuration. "
            f"Set {env_key} in .env file. "
            f"Example: {env_key}=mistral:7b-instruct"
        )
    return model


def get_agent_provider_explicit(agent_id: str) -> str:
    """
    Get LLM provider for a specific agent (EXPLICIT - NO FALLBACK).

    Reads AUTOBOT_{AGENT_ID}_PROVIDER from environment.
    Raises AgentConfigurationError if not set.

    Args:
        agent_id: The agent identifier

    Returns:
        Provider name (ollama, openai, anthropic, custom)

    Raises:
        AgentConfigurationError: If AUTOBOT_{AGENT_ID}_PROVIDER is not set
    """
    env_key = f"AUTOBOT_{agent_id.upper()}_PROVIDER"
    provider = os.environ.get(env_key, "")
    if not provider:
        raise AgentConfigurationError(
            f"Agent '{agent_id}' requires explicit LLM provider configuration. "
            f"Set {env_key} in .env file. "
            f"Supported providers: ollama, openai, anthropic, custom"
        )
    return provider


# =============================================================================
# Agent-Specific Configuration Functions (WITH FALLBACKS - DEPRECATED)
# =============================================================================
# These functions provide backward compatibility but are deprecated.
# New code should use the _explicit versions above.
# =============================================================================


def get_agent_llm_config(agent_id: str) -> dict:
    """
    Get complete LLM configuration for a specific agent.

    DEPRECATED: Use get_agent_llm_config_explicit() for new code.

    Each agent can have its own provider, endpoint, and model via environment variables:
    - AUTOBOT_{AGENT_ID}_PROVIDER (e.g., AUTOBOT_ORCHESTRATOR_PROVIDER=openai)
    - AUTOBOT_{AGENT_ID}_ENDPOINT (e.g., AUTOBOT_ORCHESTRATOR_ENDPOINT=https://api.openai.com/v1)
    - AUTOBOT_{AGENT_ID}_MODEL (e.g., AUTOBOT_ORCHESTRATOR_MODEL=gpt-4)

    If not specified, falls back to defaults from SSOT config.

    Args:
        agent_id: The agent identifier (e.g., "orchestrator", "chat", "rag")

    Returns:
        Dict with provider, endpoint, model, api_key, and timeout
    """
    return get_config().llm.get_agent_config(agent_id)


def get_agent_endpoint(agent_id: str) -> str:
    """
    Get LLM API endpoint URL for a specific agent.

    DEPRECATED: Use get_agent_endpoint_explicit() for new code.

    Checks AUTOBOT_{AGENT_ID}_ENDPOINT first, falls back to provider default.

    Args:
        agent_id: The agent identifier

    Returns:
        API endpoint URL for the agent's LLM provider
    """
    return get_config().llm.get_endpoint_for_agent(agent_id)


def get_agent_model(agent_id: str) -> str:
    """
    Get LLM model name for a specific agent.

    DEPRECATED: Use get_agent_model_explicit() for new code.

    Checks AUTOBOT_{AGENT_ID}_MODEL first, falls back to default_model.

    Args:
        agent_id: The agent identifier

    Returns:
        Model name for the agent
    """
    return get_config().llm.get_model_for_agent(agent_id)


def get_agent_provider(agent_id: str) -> str:
    """
    Get LLM provider for a specific agent.

    DEPRECATED: Use get_agent_provider_explicit() for new code.

    Checks AUTOBOT_{AGENT_ID}_PROVIDER first, falls back to default provider.

    Args:
        agent_id: The agent identifier

    Returns:
        Provider name (ollama, openai, anthropic, custom)
    """
    return get_config().llm.get_provider_for_agent(agent_id)


# Export commonly used values at module level for convenience
__all__ = [
    "AutoBotConfig",
    "VMConfig",
    "PortConfig",
    "LLMConfig",
    "TimeoutConfig",
    "RedisConfig",
    "CacheConfig",
    "CacheCoordinatorConfig",
    "CacheRedisConfig",
    "CacheL1Config",
    "CacheL2Config",
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
    # Agent-specific configuration (EXPLICIT - NO FALLBACKS)
    "AgentConfigurationError",
    "get_agent_llm_config_explicit",
    "get_agent_endpoint_explicit",
    "get_agent_model_explicit",
    "get_agent_provider_explicit",
    # Agent-specific configuration (DEPRECATED - WITH FALLBACKS)
    "get_agent_llm_config",
    "get_agent_endpoint",
    "get_agent_model",
    "get_agent_provider",
]
