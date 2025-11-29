#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Model Constants for AutoBot - SINGLE SOURCE OF TRUTH
=====================================================

All LLM model configuration is centralized here.
Fallback values are defined ONCE and referenced throughout.

Usage:
    from src.constants.model_constants import ModelConstants

    # Use default model (reads from .env, falls back to FALLBACK_MODEL)
    model_name = ModelConstants.DEFAULT_OLLAMA_MODEL

    # Use model endpoints
    ollama_url = ModelConstants.get_ollama_url()
"""

import os
from dataclasses import dataclass
from typing import Optional


# =============================================================================
# FALLBACK DEFAULTS - DEFINED ONCE, USED EVERYWHERE
# =============================================================================
# These are the ultimate fallbacks if .env is not configured.
# Change these values to change the default for the entire system.

FALLBACK_MODEL = "mistral:7b-instruct"  # Default LLM model
FALLBACK_OPENAI_MODEL = "gpt-4"
FALLBACK_ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
FALLBACK_GOOGLE_MODEL = "gemini-pro"


@dataclass(frozen=True)
class ModelConstants:
    """
    LLM Model configuration constants for AutoBot.

    All models read from environment variables with centralized fallbacks.
    """

    # =========================================================================
    # DEFAULT MODELS - Read from .env, fallback to constants above
    # =========================================================================

    DEFAULT_OLLAMA_MODEL: str = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", FALLBACK_MODEL)
    DEFAULT_OPENAI_MODEL: str = os.getenv("AUTOBOT_OPENAI_MODEL", FALLBACK_OPENAI_MODEL)
    DEFAULT_ANTHROPIC_MODEL: str = os.getenv("AUTOBOT_ANTHROPIC_MODEL", FALLBACK_ANTHROPIC_MODEL)
    DEFAULT_GOOGLE_MODEL: str = os.getenv("AUTOBOT_GOOGLE_MODEL", FALLBACK_GOOGLE_MODEL)

    # =========================================================================
    # MODEL PROVIDERS
    # =========================================================================

    PROVIDER_OLLAMA: str = "ollama"
    PROVIDER_OPENAI: str = "openai"
    PROVIDER_ANTHROPIC: str = "anthropic"
    PROVIDER_GOOGLE: str = "google"
    PROVIDER_LM_STUDIO: str = "lm_studio"

    # =========================================================================
    # MODEL ENDPOINTS
    # =========================================================================

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
    """Model configuration settings - generation parameters and limits"""

    # Context limits
    DEFAULT_CONTEXT_LENGTH: int = 8192
    MAX_CONTEXT_LENGTH: int = 32768
    MAX_HISTORY_TOKENS: int = 3000

    # RAG Context Length Optimization (by complexity score)
    RAG_CONTEXT_HIGH_COMPLEXITY: int = 3000  # complexity > 0.8
    RAG_CONTEXT_MEDIUM_COMPLEXITY: int = 2500  # complexity > 0.6
    RAG_CONTEXT_LOW_COMPLEXITY: int = 2000  # complexity <= 0.6

    # RAG Chunk Count Optimization (by complexity score)
    RAG_CHUNKS_HIGH_COMPLEXITY: int = 8
    RAG_CHUNKS_MEDIUM_COMPLEXITY: int = 6
    RAG_CHUNKS_LOW_COMPLEXITY: int = 5

    # Model Size Thresholds (MB) for task complexity classification
    MODEL_SIZE_LIGHTWEIGHT_THRESHOLD_MB: int = 1000  # < 1GB = lightweight
    MODEL_SIZE_MODERATE_THRESHOLD_MB: int = 3000  # < 3GB = moderate

    # Generation parameters
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 0.9
    DEFAULT_MAX_TOKENS: int = 2048

    # Timeouts (in seconds)
    DEFAULT_TIMEOUT: int = 30
    LONG_GENERATION_TIMEOUT: int = 120

    # Retry settings
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2


# Singleton instances for easy access
model_constants = ModelConstants()
model_config = ModelConfig()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_default_model(provider: Optional[str] = None) -> str:
    """
    Get the default model for a specific provider or the system default.

    Args:
        provider: Optional provider name (ollama, openai, anthropic, google)

    Returns:
        Default model name for the provider
    """
    if provider == ModelConstants.PROVIDER_OLLAMA:
        return ModelConstants.DEFAULT_OLLAMA_MODEL
    elif provider == ModelConstants.PROVIDER_OPENAI:
        return ModelConstants.DEFAULT_OPENAI_MODEL
    elif provider == ModelConstants.PROVIDER_ANTHROPIC:
        return ModelConstants.DEFAULT_ANTHROPIC_MODEL
    elif provider == ModelConstants.PROVIDER_GOOGLE:
        return ModelConstants.DEFAULT_GOOGLE_MODEL
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
