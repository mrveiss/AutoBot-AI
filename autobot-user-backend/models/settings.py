# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pydantic Settings Models for AutoBot Configuration

This module provides strongly-typed configuration management using Pydantic Settings,
replacing the manual config handling with validated, type-safe configuration models.
"""

import logging
import os
from typing import Dict, List, Optional

from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)
import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from constants.model_constants import Models
from constants.network_constants import NetworkConstants, ServiceURLs

# Issue #380: Module-level tuples for validation constants
_VALID_LOG_LEVELS = ("debug", "info", "warning", "error", "critical")
_VALID_TASK_TRANSPORTS = ("local", "redis")


class LLMSettings(BaseSettings):
    """LLM configuration settings with validation."""

    default_llm: str = Field(default="ollama", description="Default LLM provider")
    orchestrator_llm: str = Field(
        default=Models.ORCHESTRATOR, description="LLM model for orchestrator"
    )
    task_llm: str = Field(default="ollama", description="LLM provider for tasks")

    # Ollama configuration
    ollama_host: str = Field(
        default=ServiceURLs.OLLAMA_LOCAL, description="Ollama server host"
    )
    ollama_port: int = Field(
        default=NetworkConstants.OLLAMA_PORT, description="Ollama server port"
    )
    ollama_model: str = Field(
        default=Models.DEFAULT, description="Default Ollama model"
    )
    ollama_base_url: str = Field(
        default=ServiceURLs.OLLAMA_LOCAL, description="Ollama base URL"
    )

    # OpenAI configuration (optional)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="gpt-3.5-turbo", description="OpenAI model")

    # HuggingFace configuration (optional)
    huggingface_api_key: Optional[str] = Field(
        default=None, description="HuggingFace API key"
    )
    huggingface_model: str = Field(
        default="microsoft/DialoGPT-medium", description="HuggingFace model"
    )

    class Config:
        """Pydantic config for LLM settings with AUTOBOT_ env prefix."""

        env_prefix = "AUTOBOT_"
        case_sensitive = False


class RedisSettings(BaseSettings):
    """Redis configuration settings with validation."""

    enabled: bool = Field(
        default=True, description="Enable Redis for caching and task transport"
    )
    host: str = Field(default="localhost", description="Redis server host")
    port: int = Field(
        default=NetworkConstants.REDIS_PORT, description="Redis server port"
    )
    db: int = Field(default=1, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        """Validate port is in valid range (1-65535)."""
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    class Config:
        """Pydantic config for Redis settings with AUTOBOT_REDIS_ env prefix."""

        env_prefix = "AUTOBOT_REDIS_"
        case_sensitive = False


class DataSettings(BaseSettings):
    """Data storage configuration settings."""

    base_directory: str = Field(default="data", description="Base data directory")
    chat_history_file: str = Field(
        default="data/chat_history.json", description="Chat history file path"
    )
    chats_directory: str = Field(
        default="data/chats", description="Individual chat files directory"
    )
    long_term_db_path: str = Field(
        default="data/agent_memory.db", description="Long-term memory database path"
    )
    reliability_stats_file: str = Field(
        default="data/reliability_stats.json", description="Reliability statistics file"
    )
    knowledge_base_db: str = Field(
        default="data/knowledge_base.db", description="Knowledge base SQLite database"
    )
    chromadb_path: str = Field(
        default="data/chromadb", description="ChromaDB storage path"
    )

    class Config:
        """Pydantic config for Data settings with AUTOBOT_DATA_ env prefix."""

        env_prefix = "AUTOBOT_DATA_"
        case_sensitive = False


class BackendSettings(BaseSettings):
    """Backend server configuration settings."""

    server_host: str = Field(
        default=NetworkConstants.BIND_ALL_INTERFACES, description="Server bind address"
    )
    server_port: int = Field(
        default=NetworkConstants.BACKEND_PORT, description="Server port"
    )
    api_endpoint: str = Field(
        default=ServiceURLs.BACKEND_LOCAL, description="API endpoint URL"
    )
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:{NetworkConstants.AI_STACK_PORT}",
            ServiceURLs.FRONTEND_LOCAL,
        ],
        description="CORS allowed origins",
    )
    reload: bool = Field(default=False, description="Enable auto-reload in development")
    log_level: str = Field(default="info", description="Logging level")

    @field_validator("server_port")
    @classmethod
    def validate_port(cls, v):
        """Validate server port is in valid range (1-65535)."""
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate and normalize log level to lowercase (Issue #380: use module constant)."""
        if v.lower() not in _VALID_LOG_LEVELS:
            raise ValueError(f"Log level must be one of: {list(_VALID_LOG_LEVELS)}")
        return v.lower()

    class Config:
        """Pydantic config for Backend settings with AUTOBOT_BACKEND_ env prefix."""

        env_prefix = "AUTOBOT_BACKEND_"
        case_sensitive = False


class SecuritySettings(BaseSettings):
    """Security configuration settings."""

    # Issue #756: Security hardening - auth enabled by default
    enable_auth: bool = Field(default=True, description="Enable authentication")
    audit_log_file: str = Field(
        default="data/audit.log", description="Audit log file path"
    )
    allowed_users: Dict[str, str] = Field(
        default={}, description="Allowed users (username: password)"
    )
    roles: Dict[str, Metadata] = Field(
        default={}, description="User roles and permissions"
    )

    class Config:
        """Pydantic config for Security settings with AUTOBOT_SECURITY_ env prefix."""

        env_prefix = "AUTOBOT_SECURITY_"
        case_sensitive = False


class DiagnosticsSettings(BaseSettings):
    """Diagnostics and monitoring configuration."""

    enabled: bool = Field(default=True, description="Enable diagnostics")
    use_llm_for_analysis: bool = Field(
        default=True, description="Use LLM for failure analysis"
    )
    use_web_search_for_analysis: bool = Field(
        default=False, description="Use web search for analysis"
    )
    auto_apply_fixes: bool = Field(
        default=False, description="Automatically apply suggested fixes"
    )

    class Config:
        """Pydantic config for Diagnostics settings with AUTOBOT_DIAGNOSTICS_ env prefix."""

        env_prefix = "AUTOBOT_DIAGNOSTICS_"
        case_sensitive = False


class MemorySettings(BaseSettings):
    """Memory management configuration."""

    retention_days: int = Field(
        default=90, description="Memory retention period in days"
    )
    max_entries_per_category: int = Field(
        default=10000, description="Maximum entries per category"
    )

    class Config:
        """Pydantic config for Memory settings with AUTOBOT_MEMORY_ env prefix."""

        env_prefix = "AUTOBOT_MEMORY_"
        case_sensitive = False


class OrchestratorSettings(BaseSettings):
    """Orchestrator configuration settings."""

    use_langchain: bool = Field(default=False, description="Use LangChain orchestrator")
    task_transport: str = Field(
        default="local", description="Task transport mechanism (local/redis)"
    )
    max_concurrent_tasks: int = Field(default=5, description="Maximum concurrent tasks")

    @field_validator("task_transport")
    @classmethod
    def validate_transport(cls, v):
        """Validate task transport (Issue #380: use module constant)."""
        if v not in _VALID_TASK_TRANSPORTS:
            raise ValueError(
                f"Task transport must be one of: {list(_VALID_TASK_TRANSPORTS)}"
            )
        return v

    class Config:
        """Pydantic config for Orchestrator settings with AUTOBOT_ORCHESTRATOR_ env prefix."""

        env_prefix = "AUTOBOT_ORCHESTRATOR_"
        case_sensitive = False


class AutoBotSettings(BaseSettings):
    """Main AutoBot configuration aggregating all settings."""

    # Nested settings
    llm: LLMSettings = Field(default_factory=LLMSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    data: DataSettings = Field(default_factory=DataSettings)
    backend: BackendSettings = Field(default_factory=BackendSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    diagnostics: DiagnosticsSettings = Field(default_factory=DiagnosticsSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    orchestrator: OrchestratorSettings = Field(default_factory=OrchestratorSettings)

    # Global settings
    environment: str = Field(
        default="development", description="Environment (development/production)"
    )
    debug: bool = Field(default=False, description="Enable debug mode")

    model_config = SettingsConfigDict(
        env_prefix="AUTOBOT_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    def get_llm_config(self) -> Metadata:
        """Get LLM configuration as dict for backward compatibility."""
        return {
            "default_llm": self.llm.default_llm,
            "orchestrator_llm": self.llm.orchestrator_llm,
            "task_llm": self.llm.task_llm,
            "ollama": {
                "host": self.llm.ollama_host,
                "port": self.llm.ollama_port,
                "model": self.llm.ollama_model,
                "base_url": self.llm.ollama_base_url,
            },
            "openai": {
                "api_key": self.llm.openai_api_key,
                "model": self.llm.openai_model,
            },
            "huggingface": {
                "api_key": self.llm.huggingface_api_key,
                "model": self.llm.huggingface_model,
            },
        }

    def get_redis_config(self) -> Metadata:
        """Get Redis configuration as dict for backward compatibility."""
        return {
            "enabled": self.redis.enabled,
            "host": self.redis.host,
            "port": self.redis.port,
            "db": self.redis.db,
            "password": self.redis.password,
        }

    def get_backend_config(self) -> Metadata:
        """Get backend configuration as dict for backward compatibility."""
        return {
            "server_host": self.backend.server_host,
            "server_port": self.backend.server_port,
            "api_endpoint": self.backend.api_endpoint,
            "cors_origins": self.backend.cors_origins,
            "reload": self.backend.reload,
            "log_level": self.backend.log_level,
        }

    def to_dict(self) -> Metadata:
        """Convert settings to dictionary for backward compatibility."""
        return {
            "llm_config": self.get_llm_config(),
            "memory": {
                "redis": self.get_redis_config(),
                "retention_days": self.memory.retention_days,
                "max_entries_per_category": (self.memory.max_entries_per_category),
                "long_term_db_path": self.data.long_term_db_path,
            },
            "data": {
                "chat_history_file": self.data.chat_history_file,
                "chats_directory": self.data.chats_directory,
                "long_term_db_path": self.data.long_term_db_path,
                "reliability_stats_file": self.data.reliability_stats_file,
                "knowledge_base_db": self.data.knowledge_base_db,
                "chromadb_path": self.data.chromadb_path,
            },
            "backend": self.get_backend_config(),
            "security_config": {
                "enable_auth": self.security.enable_auth,
                "audit_log_file": self.security.audit_log_file,
                "allowed_users": self.security.allowed_users,
                "roles": self.security.roles,
            },
            "diagnostics": {
                "enabled": self.diagnostics.enabled,
                "use_llm_for_analysis": (self.diagnostics.use_llm_for_analysis),
                "use_web_search_for_analysis": (
                    self.diagnostics.use_web_search_for_analysis
                ),
                "auto_apply_fixes": self.diagnostics.auto_apply_fixes,
            },
            "orchestrator": {
                "use_langchain": self.orchestrator.use_langchain,
                "task_transport": self.orchestrator.task_transport,
                "max_concurrent_tasks": (self.orchestrator.max_concurrent_tasks),
            },
        }


def yaml_config_settings_source(settings: BaseSettings) -> Metadata:
    """
    A simple settings source that loads variables from a YAML file.
    """
    config_file = "config/config.yaml"
    if not os.path.exists(config_file):
        return {}

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}
        return yaml_config
    except Exception as e:
        logger.warning("Could not load YAML config from %s: %s", config_file, e)
        return {}


# Global settings instance
settings = AutoBotSettings()

# Export individual settings for convenience
llm_settings = settings.llm
redis_settings = settings.redis
data_settings = settings.data
backend_settings = settings.backend
security_settings = settings.security
diagnostics_settings = settings.diagnostics
memory_settings = settings.memory
orchestrator_settings = settings.orchestrator
