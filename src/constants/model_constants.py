#!/usr/bin/env python3
"""
Model Constants for AutoBot
============================

Centralized LLM model configuration constants to eliminate hardcoded model names
and provide a single source of truth for AI model configuration.

Usage:
    from src.constants.model_constants import ModelConstants

    # Use default model
    model_name = ModelConstants.DEFAULT_OLLAMA_MODEL

    # Use model endpoints
    ollama_url = ModelConstants.OLLAMA_BASE_URL
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModelConstants:
    """LLM Model configuration constants for AutoBot"""

    # Default Models - Can be overridden via environment variables
    DEFAULT_OLLAMA_MODEL: str = os.getenv("AUTOBOT_OLLAMA_MODEL", "deepseek-r1:14b")
    DEFAULT_OPENAI_MODEL: str = os.getenv("AUTOBOT_OPENAI_MODEL", "gpt-4")
    DEFAULT_ANTHROPIC_MODEL: str = os.getenv("AUTOBOT_ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    # Model Providers
    PROVIDER_OLLAMA: str = "ollama"
    PROVIDER_OPENAI: str = "openai"
    PROVIDER_ANTHROPIC: str = "anthropic"
    PROVIDER_LM_STUDIO: str = "lm_studio"

    # Popular Model Names (for reference/validation)
    DEEPSEEK_R1_14B: str = "deepseek-r1:14b"
    DEEPSEEK_R1_7B: str = "deepseek-r1:7b"
    LLAMA_3_70B: str = "llama3:70b"
    LLAMA_3_8B: str = "llama3:8b"
    QWEN_72B: str = "qwen:72b"
    MISTRAL_7B: str = "mistral:7b"

    # Model Endpoints (constructed from NetworkConstants)
    @staticmethod
    def get_ollama_url() -> str:
        """Get Ollama service URL from environment or default to AI Stack VM"""
        from src.constants.network_constants import NetworkConstants
        host = os.getenv("AUTOBOT_OLLAMA_HOST", NetworkConstants.AI_STACK_VM_IP)
        port = os.getenv("AUTOBOT_OLLAMA_PORT", str(NetworkConstants.OLLAMA_PORT))
        return f"http://{host}:{port}"

    @staticmethod
    def get_lm_studio_url() -> str:
        """Get LM Studio service URL from environment or default"""
        from src.constants.network_constants import NetworkConstants
        host = os.getenv("AUTOBOT_LM_STUDIO_HOST", NetworkConstants.LOCALHOST_IP)
        port = os.getenv("AUTOBOT_LM_STUDIO_PORT", "1234")
        return f"http://{host}:{port}"


@dataclass(frozen=True)
class ModelConfig:
    """Model configuration settings"""

    # Context limits
    DEFAULT_CONTEXT_LENGTH: int = 8192
    MAX_CONTEXT_LENGTH: int = 32768
    MAX_HISTORY_TOKENS: int = 3000  # Maximum tokens for conversation history

    # Generation parameters
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 0.9
    DEFAULT_MAX_TOKENS: int = 2048

    # Timeouts (in seconds)
    DEFAULT_TIMEOUT: int = 30
    LONG_GENERATION_TIMEOUT: int = 120

    # Retry settings
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2  # seconds


# Singleton instances for easy access
model_constants = ModelConstants()
model_config = ModelConfig()


# Convenience functions for common use cases
def get_default_model(provider: Optional[str] = None) -> str:
    """
    Get the default model for a specific provider or the system default.

    Args:
        provider: Optional provider name (ollama, openai, anthropic)

    Returns:
        Default model name for the provider
    """
    if provider == ModelConstants.PROVIDER_OLLAMA:
        return ModelConstants.DEFAULT_OLLAMA_MODEL
    elif provider == ModelConstants.PROVIDER_OPENAI:
        return ModelConstants.DEFAULT_OPENAI_MODEL
    elif provider == ModelConstants.PROVIDER_ANTHROPIC:
        return ModelConstants.DEFAULT_ANTHROPIC_MODEL
    else:
        return ModelConstants.DEFAULT_OLLAMA_MODEL  # System default


def get_model_endpoint(provider: str) -> str:
    """
    Get the endpoint URL for a specific provider.

    Args:
        provider: Provider name (ollama, lm_studio, etc.)

    Returns:
        Endpoint URL for the provider
    """
    if provider == ModelConstants.PROVIDER_OLLAMA:
        return ModelConstants.get_ollama_url()
    elif provider == ModelConstants.PROVIDER_LM_STUDIO:
        return ModelConstants.get_lm_studio_url()
    else:
        raise ValueError(f"Unknown provider: {provider}")
