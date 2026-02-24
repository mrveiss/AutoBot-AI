# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Interface Models - Dataclasses and settings for LLM operations.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from constants.model_constants import ModelConfig, ModelConstants
from constants.network_constants import NetworkConstants
from pydantic import Field
from pydantic_settings import BaseSettings

from .types import LLMType, ProviderType


class LLMSettings(BaseSettings):
    """LLM configuration using pydantic-settings for async config management"""

    # Ollama settings
    ollama_host: str = Field(
        default=NetworkConstants.MAIN_MACHINE_IP, env="OLLAMA_HOST"
    )
    ollama_port: int = Field(default=NetworkConstants.OLLAMA_PORT, env="OLLAMA_PORT")

    # Model settings - Uses centralized model constants
    default_model: str = Field(
        default=ModelConstants.DEFAULT_OLLAMA_MODEL, env="DEFAULT_LLM_MODEL"
    )
    temperature: float = Field(
        default=ModelConfig.DEFAULT_TEMPERATURE, env="LLM_TEMPERATURE"
    )
    top_k: int = Field(default=ModelConfig.DEFAULT_TOP_K, env="LLM_TOP_K")
    top_p: float = Field(default=ModelConfig.DEFAULT_TOP_P, env="LLM_TOP_P")
    repeat_penalty: float = Field(
        default=ModelConfig.DEFAULT_REPEAT_PENALTY, env="LLM_REPEAT_PENALTY"
    )
    num_ctx: int = Field(default=ModelConfig.DEFAULT_NUM_CTX, env="LLM_CONTEXT_SIZE")

    # Performance settings - optimized for high-end hardware
    max_retries: int = Field(default=ModelConfig.MAX_RETRIES, env="LLM_MAX_RETRIES")
    connection_pool_size: int = Field(
        default=ModelConfig.DEFAULT_CONNECTION_POOL_SIZE, env="LLM_POOL_SIZE"
    )
    max_concurrent_requests: int = Field(
        default=ModelConfig.DEFAULT_MAX_CONCURRENT_REQUESTS, env="LLM_MAX_CONCURRENT"
    )
    connection_timeout: float = Field(
        default=ModelConfig.DEFAULT_TIMEOUT, env="LLM_CONNECTION_TIMEOUT"
    )
    cache_ttl: int = Field(default=ModelConfig.DEFAULT_CACHE_TTL, env="LLM_CACHE_TTL")

    # Streaming settings - using completion signal detection
    max_chunks: int = Field(
        default=ModelConfig.DEFAULT_MAX_CHUNKS, env="LLM_MAX_CHUNKS"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


@dataclass
class LLMResponse:
    """Structured LLM response"""

    content: str
    model: str = ""
    provider: str = ""
    tokens_used: Optional[int] = None
    processing_time: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    request_id: str = ""
    error: Optional[str] = None
    fallback_used: bool = False


@dataclass
class ChatMessage:
    """Chat message structure"""

    role: str  # "user", "assistant", "system"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMRequest:
    """Standardized LLM request structure."""

    messages: List[Dict[str, str]]
    llm_type: Union[LLMType, str] = LLMType.GENERAL
    provider: Optional[ProviderType] = None
    model_name: Optional[str] = None
    temperature: float = ModelConfig.DEFAULT_TEMPERATURE
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[List[str]] = None
    stream: bool = False
    structured_output: bool = False
    timeout: int = None
    retry_count: int = ModelConfig.MAX_RETRIES
    fallback_enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


__all__ = [
    "LLMSettings",
    "LLMResponse",
    "ChatMessage",
    "LLMRequest",
]
