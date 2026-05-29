# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Interface Models - Dataclasses and settings for LLM operations.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from constants.model_constants import ModelConfig, ModelConstants
from constants.network_constants import NetworkConstants

from .types import LLMType, ProviderType


class LLMSettings(BaseSettings):
    """LLM configuration using pydantic-settings for async config management"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        populate_by_name=True,
    )

    # Ollama settings
    ollama_host: str = Field(
        default=NetworkConstants.MAIN_MACHINE_IP,
        validation_alias="OLLAMA_HOST",
    )
    ollama_port: int = Field(
        default=NetworkConstants.OLLAMA_PORT,
        validation_alias="OLLAMA_PORT",
    )

    # Model settings - Uses centralized model constants
    default_model: str = Field(
        default=ModelConstants.DEFAULT_OLLAMA_MODEL,
        validation_alias="DEFAULT_LLM_MODEL",
    )
    temperature: float = Field(
        default=ModelConfig.DEFAULT_TEMPERATURE,
        validation_alias="LLM_TEMPERATURE",
    )
    top_k: int = Field(
        default=ModelConfig.DEFAULT_TOP_K,
        validation_alias="LLM_TOP_K",
    )
    top_p: float = Field(
        default=ModelConfig.DEFAULT_TOP_P,
        validation_alias="LLM_TOP_P",
    )
    repeat_penalty: float = Field(
        default=ModelConfig.DEFAULT_REPEAT_PENALTY,
        validation_alias="LLM_REPEAT_PENALTY",
    )
    num_ctx: int = Field(
        default=ModelConfig.DEFAULT_NUM_CTX,
        validation_alias="LLM_CONTEXT_SIZE",
    )

    # Performance settings - optimized for high-end hardware
    max_retries: int = Field(
        default=ModelConfig.MAX_RETRIES,
        validation_alias="LLM_MAX_RETRIES",
    )
    connection_pool_size: int = Field(
        default=ModelConfig.DEFAULT_CONNECTION_POOL_SIZE,
        validation_alias="LLM_POOL_SIZE",
    )
    max_concurrent_requests: int = Field(
        default=ModelConfig.DEFAULT_MAX_CONCURRENT_REQUESTS,
        validation_alias="LLM_MAX_CONCURRENT",
    )
    connection_timeout: float = Field(
        default=ModelConfig.DEFAULT_TIMEOUT,
        validation_alias="LLM_CONNECTION_TIMEOUT",
    )
    cache_ttl: int = Field(
        default=ModelConfig.DEFAULT_CACHE_TTL,
        validation_alias="LLM_CACHE_TTL",
    )

    # Streaming settings - using completion signal detection
    max_chunks: int = Field(
        default=ModelConfig.DEFAULT_MAX_CHUNKS,
        validation_alias="LLM_MAX_CHUNKS",
    )


@dataclass
class ToolDefinition:
    """Describes a tool that can be called by an LLM."""

    name: str
    description: str
    input_schema: dict  # JSON Schema object


@dataclass
class ToolCall:
    """A tool invocation returned by an LLM."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Structured LLM response"""

    content: str
    model: str = ""
    provider: str = ""
    tokens_used: int | None = None
    processing_time: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    request_id: str = ""
    error: str | None = None
    fallback_used: bool = False
    provider_metadata: Dict[str, Any] | None = None
    hidden_params: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List["ToolCall"] | None = None


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
    llm_type: LLMType | str = LLMType.GENERAL
    provider: ProviderType | None = None
    model_name: str | None = None
    temperature: float = ModelConfig.DEFAULT_TEMPERATURE
    max_tokens: int | None = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: List[str] | None = None
    stream: bool = False
    structured_output: bool = False
    timeout: int = None
    retry_count: int = ModelConfig.MAX_RETRIES
    fallback_enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tools: List["ToolDefinition"] | None = None
    tool_choice: str | None = None  # "auto" | "none" | specific tool name


__all__ = [
    "LLMSettings",
    "ToolDefinition",
    "ToolCall",
    "LLMResponse",
    "ChatMessage",
    "LLMRequest",
]
