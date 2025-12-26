#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Model Constants for AutoBot - SINGLE SOURCE OF TRUTH
=====================================================

All LLM model configuration is centralized here. This module now reads
from the SSOT (Single Source of Truth) configuration system.

MIGRATION (Issue #602):
    All values are now sourced from src/config/ssot_config.py which reads
    from the .env file. Hardcoded fallbacks are only used if SSOT fails.

Usage:
    from src.constants.model_constants import ModelConstants

    # Use default model (reads from SSOT/.env)
    model_name = ModelConstants.DEFAULT_OLLAMA_MODEL

    # Use model endpoints (reads from SSOT/.env)
    ollama_url = ModelConstants.get_ollama_url()

    # Preferred: Use SSOT directly
    from src.config.ssot_config import config
    model_name = config.llm.default_model
    ollama_url = config.ollama_url
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


def _get_ssot_config():
    """
    Get SSOT config with graceful fallback.

    Returns the SSOT config instance. If SSOT fails to load (e.g., during
    early imports or missing dependencies), returns None and callers should
    use hardcoded fallbacks.
    """
    try:
        from src.config.ssot_config import get_config

        return get_config()
    except Exception:
        # During early initialization or if .env is missing, SSOT may fail
        return None


# Get config once at module load time for efficiency
_ssot = _get_ssot_config()


# =============================================================================
# FALLBACK DEFAULTS - DEFINED ONCE, USED EVERYWHERE
# =============================================================================
# These are the ultimate fallbacks if SSOT/.env is not configured.
# Change these values to change the default for the entire system.

FALLBACK_MODEL = "mistral:7b-instruct"  # Default LLM model
FALLBACK_OPENAI_MODEL = "gpt-4"
FALLBACK_ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
FALLBACK_GOOGLE_MODEL = "gemini-pro"


class ModelConstants:
    """
    LLM Model configuration constants for AutoBot.

    SSOT Migration (Issue #602):
        All models now read from SSOT config (.env file) with hardcoded
        fallbacks only used if .env is missing or malformed.

    Usage remains unchanged for backward compatibility:
        from src.constants.model_constants import ModelConstants
        model = ModelConstants.DEFAULT_OLLAMA_MODEL
    """

    # =========================================================================
    # DEFAULT MODELS - Read from SSOT/.env, fallback to constants above
    # =========================================================================

    DEFAULT_OLLAMA_MODEL: str = (
        _ssot.llm.default_model
        if _ssot
        else os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", FALLBACK_MODEL)
    )
    DEFAULT_OPENAI_MODEL: str = os.getenv("AUTOBOT_OPENAI_MODEL", FALLBACK_OPENAI_MODEL)
    DEFAULT_ANTHROPIC_MODEL: str = os.getenv(
        "AUTOBOT_ANTHROPIC_MODEL", FALLBACK_ANTHROPIC_MODEL
    )
    DEFAULT_GOOGLE_MODEL: str = os.getenv("AUTOBOT_GOOGLE_MODEL", FALLBACK_GOOGLE_MODEL)

    # Additional model types from SSOT
    EMBEDDING_MODEL: str = (
        _ssot.llm.embedding_model
        if _ssot
        else os.getenv("AUTOBOT_EMBEDDING_MODEL", "nomic-embed-text:latest")
    )
    CLASSIFICATION_MODEL: str = (
        _ssot.llm.classification_model
        if _ssot
        else os.getenv("AUTOBOT_CLASSIFICATION_MODEL", FALLBACK_MODEL)
    )
    REASONING_MODEL: str = (
        _ssot.llm.reasoning_model
        if _ssot
        else os.getenv("AUTOBOT_REASONING_MODEL", FALLBACK_MODEL)
    )
    RAG_MODEL: str = (
        _ssot.llm.rag_model
        if _ssot
        else os.getenv("AUTOBOT_RAG_MODEL", FALLBACK_MODEL)
    )
    CODING_MODEL: str = (
        _ssot.llm.coding_model
        if _ssot
        else os.getenv("AUTOBOT_CODING_MODEL", FALLBACK_MODEL)
    )
    ORCHESTRATOR_MODEL: str = (
        _ssot.llm.orchestrator_model
        if _ssot
        else os.getenv("AUTOBOT_ORCHESTRATOR_MODEL", FALLBACK_MODEL)
    )

    # =========================================================================
    # MODEL PROVIDERS
    # =========================================================================

    PROVIDER_OLLAMA: str = "ollama"
    PROVIDER_OPENAI: str = "openai"
    PROVIDER_ANTHROPIC: str = "anthropic"
    PROVIDER_GOOGLE: str = "google"
    PROVIDER_LM_STUDIO: str = "lm_studio"

    # Current provider from SSOT
    CURRENT_PROVIDER: str = (
        _ssot.llm.provider if _ssot else os.getenv("AUTOBOT_LLM_PROVIDER", "ollama")
    )

    # =========================================================================
    # MODEL ENDPOINTS
    # =========================================================================

    @staticmethod
    def get_ollama_url() -> str:
        """
        Get Ollama service URL.

        SSOT Migration (Issue #602):
            Prefer using SSOT directly:
                from src.config.ssot_config import config
                url = config.ollama_url
        """
        if _ssot:
            return _ssot.ollama_url
        # Fallback to environment/network constants
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
    DEFAULT_TOP_K: int = 40
    DEFAULT_REPEAT_PENALTY: float = 1.1
    DEFAULT_MAX_TOKENS: int = 2048
    DEFAULT_NUM_CTX: int = 4096  # Ollama context window

    # Timeouts (in seconds) - prefer SSOT for these
    DEFAULT_TIMEOUT: int = _ssot.timeout.llm if _ssot else 30
    LONG_GENERATION_TIMEOUT: int = 120

    # Retry settings
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2

    # Performance settings
    DEFAULT_CONNECTION_POOL_SIZE: int = 20
    DEFAULT_MAX_CONCURRENT_REQUESTS: int = 8
    DEFAULT_CACHE_TTL: int = 300  # 5 minutes
    DEFAULT_MAX_CHUNKS: int = 1000  # Streaming response chunks

    # RAG search settings (Issue #611)
    RAG_DEFAULT_MAX_RESULTS: int = 5
    RAG_MAX_RESULTS_PER_STAGE: int = 20
    RAG_HYBRID_WEIGHT_SEMANTIC: float = 0.7
    RAG_HYBRID_WEIGHT_KEYWORD: float = 0.3
    RAG_DIVERSITY_THRESHOLD: float = 0.85
    RAG_DEFAULT_CONTEXT_LENGTH: int = 2000
    RAG_MAX_CONTEXT_LENGTH: int = 5000


# Singleton instances for easy access
model_constants = ModelConstants()
model_config = ModelConfig()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


@lru_cache(maxsize=8)
def get_default_model(provider: Optional[str] = None) -> str:
    """
    Get the default model for a specific provider or the system default.

    SSOT Migration (Issue #602):
        Prefer using SSOT directly:
            from src.config.ssot_config import config
            model = config.llm.default_model

    Issue #380: Added @lru_cache since models don't change at runtime.

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


@lru_cache(maxsize=8)
def get_model_endpoint(provider: str) -> str:
    """
    Get the endpoint URL for a specific provider.

    SSOT Migration (Issue #602):
        Prefer using SSOT directly:
            from src.config.ssot_config import config
            url = config.ollama_url

    Issue #380: Added @lru_cache since endpoints don't change at runtime.

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
