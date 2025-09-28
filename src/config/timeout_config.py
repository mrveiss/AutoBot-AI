"""
AutoBot Unified Timeout Configuration
====================================

Centralized timeout configuration for all AutoBot services.
This module provides standardized timeout values that can be overridden
via environment variables.

Usage:
    from src.config.timeout_config import TIMEOUT_CONFIG

    redis_timeout = TIMEOUT_CONFIG.redis_socket_timeout
    api_timeout = TIMEOUT_CONFIG.api_request_timeout
"""

import os
from dataclasses import dataclass
from typing import Union


@dataclass
class TimeoutConfiguration:
    """Unified timeout configuration for AutoBot"""

    # Redis Configuration
    redis_socket_timeout: float = 5.0
    redis_connect_timeout: float = 5.0
    redis_retry_on_timeout: bool = True
    redis_max_retries: int = 3
    redis_circuit_breaker_timeout: int = 60

    # HTTP/API Configuration
    api_request_timeout: int = 30
    health_check_timeout: int = 3
    websocket_timeout: int = 30

    # Database Configuration
    database_query_timeout: int = 10
    chromadb_timeout: int = 15
    vector_search_timeout: int = 20
    sqlite_timeout: int = 30

    # LLM Configuration
    llm_connect_timeout: float = 5.0
    llm_non_streaming_timeout: int = 30
    llm_streaming_heartbeat: int = 5

    # File Operations
    upload_timeout: int = 300
    download_timeout: int = 120

    # Background Processing
    background_processing_timeout: int = 60
    long_running_operation_timeout: int = 1800  # 30 minutes

    # Deployment Configuration
    deployment_timeout: int = 1800
    health_check_deployment_timeout: int = 300
    graceful_shutdown_timeout: int = 30

    def get_env_override(self, key: str, default: Union[int, float, bool]) -> Union[int, float, bool]:
        """Get environment variable override for timeout value"""
        env_key = f"AUTOBOT_{key.upper()}"
        env_value = os.getenv(env_key)

        if env_value is None:
            return default

        try:
            if isinstance(default, bool):
                return env_value.lower() in ('true', '1', 'yes', 'on')
            elif isinstance(default, float):
                return float(env_value)
            elif isinstance(default, int):
                return int(env_value)
        except (ValueError, TypeError):
            return default

        return default

    def __post_init__(self):
        """Apply environment variable overrides"""
        for field_name in self.__dataclass_fields__:
            current_value = getattr(self, field_name)
            override_value = self.get_env_override(field_name, current_value)
            setattr(self, field_name, override_value)


# Global timeout configuration instance
TIMEOUT_CONFIG = TimeoutConfiguration()


def get_redis_timeout_config() -> dict:
    """Get Redis-specific timeout configuration"""
    return {
        'socket_timeout': TIMEOUT_CONFIG.redis_socket_timeout,
        'socket_connect_timeout': TIMEOUT_CONFIG.redis_connect_timeout,
        'retry_on_timeout': TIMEOUT_CONFIG.redis_retry_on_timeout,
        'max_retries': TIMEOUT_CONFIG.redis_max_retries
    }


def get_api_timeout_config() -> dict:
    """Get API-specific timeout configuration"""
    return {
        'request_timeout': TIMEOUT_CONFIG.api_request_timeout,
        'health_check_timeout': TIMEOUT_CONFIG.health_check_timeout,
        'websocket_timeout': TIMEOUT_CONFIG.websocket_timeout
    }


def get_database_timeout_config() -> dict:
    """Get database-specific timeout configuration"""
    return {
        'query_timeout': TIMEOUT_CONFIG.database_query_timeout,
        'chromadb_timeout': TIMEOUT_CONFIG.chromadb_timeout,
        'vector_search_timeout': TIMEOUT_CONFIG.vector_search_timeout,
        'sqlite_timeout': TIMEOUT_CONFIG.sqlite_timeout
    }


def validate_timeout_hierarchy():
    """Validate that timeout values maintain proper hierarchy"""
    issues = []

    # Connection timeout should be less than operation timeout
    if TIMEOUT_CONFIG.redis_connect_timeout >= TIMEOUT_CONFIG.redis_socket_timeout:
        issues.append("Redis connect timeout should be less than socket timeout")

    # Health check should be fast
    if TIMEOUT_CONFIG.health_check_timeout > TIMEOUT_CONFIG.api_request_timeout:
        issues.append("Health check timeout should be less than API request timeout")

    # WebSocket timeout should be reasonable for interactive use
    if TIMEOUT_CONFIG.websocket_timeout > 60:
        issues.append("WebSocket timeout should not exceed 60 seconds for user experience")

    return issues
