#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Model Constants for AutoBot - SINGLE SOURCE OF TRUTH
=====================================================

All LLM model configuration is centralized here.

MIGRATION (Issue #763):
    All values now use ConfigRegistry with five-tier fallback:
    Cache -> Redis -> Environment -> Registry Defaults -> Caller Default

    Issue #1882: ConfigRegistry calls moved out of class/dataclass body to
    avoid circular imports during ConfigManager init. Class attributes now use
    static fallback values identical to what ConfigRegistry returns when Redis
    is unreachable. Call ConfigRegistry directly for live/Redis-backed values.

Usage:
    from constants.model_constants import ModelConstants

    # Use default model
    model_name = ModelConstants.DEFAULT_OLLAMA_MODEL

    # Use model endpoints
    ollama_url = ModelConstants.get_ollama_url()

    # Preferred: Use ConfigRegistry directly for live values
    from config.registry import ConfigRegistry
    model_name = ConfigRegistry.get("llm.default_model", DEFAULT_LLM_MODEL)
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional

from autobot_shared.ssot_config import CLASSIFICATION_MODEL as SSOT_CLASSIFICATION_MODEL
from autobot_shared.ssot_config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
)
from autobot_shared.ssot_config import INSTRUCTION_MODEL as SSOT_INSTRUCTION_MODEL
from autobot_shared.ssot_config import (
    LIGHT_PROCESSING_MODEL as SSOT_LIGHT_PROCESSING_MODEL,
)
from autobot_shared.ssot_config import QUALITY_MODEL as SSOT_QUALITY_MODEL
from autobot_shared.ssot_config import ROUTING_MODEL as SSOT_ROUTING_MODEL
from autobot_shared.ssot_config import SYSTEM_MODEL as SSOT_SYSTEM_MODEL

# =============================================================================
# FALLBACK DEFAULTS - DEFINED ONCE, USED EVERYWHERE (#2553)
# =============================================================================
# All values derive from ssot_config.py constants — never hardcode model names.
# Change models in autobot_shared/ssot_config.py to change the entire system.

FALLBACK_MODEL = DEFAULT_LLM_MODEL

# =============================================================================
# EXPLICIT MODEL NAME CONSTANTS (#3528)
# =============================================================================
# Named constants for every model string used anywhere in the codebase.
# Add new entries here rather than hardcoding strings in service files.

# OpenAI — preview/reasoning aliases without dated suffix
OPENAI_O1_PREVIEW = "o1-preview"

# OpenAI — GPT-4 family
OPENAI_GPT4 = "gpt-4"
OPENAI_GPT4_TURBO = "gpt-4-turbo"
OPENAI_GPT4O = "gpt-4o"
OPENAI_GPT4O_MINI = "gpt-4o-mini"
OPENAI_GPT4_VISION_PREVIEW = "gpt-4-vision-preview"
OPENAI_GPT4_TURBO_PREVIEW = "gpt-4-turbo-preview"
# OpenAI — GPT-3.5 family
OPENAI_GPT35_TURBO = "gpt-3.5-turbo"
OPENAI_GPT35_TURBO_16K = "gpt-3.5-turbo-16k"
# OpenAI — reasoning models
OPENAI_O1 = "o1"
OPENAI_O1_MINI = "o1-mini"
OPENAI_O3 = "o3"
OPENAI_O3_MINI = "o3-mini"
OPENAI_O4_MINI = "o4-mini"
# OpenAI — GPT-4.1 family (2025)
OPENAI_GPT41 = "gpt-4.1"
OPENAI_GPT41_MINI = "gpt-4.1-mini"
OPENAI_GPT41_NANO = "gpt-4.1-nano"

# Anthropic — Claude 4.x
ANTHROPIC_CLAUDE_OPUS4 = "claude-opus-4-20250514"
ANTHROPIC_CLAUDE_HAIKU4_5 = "claude-haiku-4-5-20251001"
ANTHROPIC_CLAUDE_SONNET4 = "claude-sonnet-4-20250514"
# Anthropic — Claude 3.x / Sonnet 4
ANTHROPIC_CLAUDE35_SONNET = "claude-3-5-sonnet-20241022"
ANTHROPIC_CLAUDE35_HAIKU = "claude-3-5-haiku-20241022"
ANTHROPIC_CLAUDE3_OPUS_DATED = "claude-3-opus-20240229"
ANTHROPIC_CLAUDE3_SONNET_DATED = "claude-3-sonnet-20240229"
ANTHROPIC_CLAUDE3_HAIKU_DATED = "claude-3-haiku-20240307"
# Anthropic — short-form names used in analytics/cost matching
ANTHROPIC_CLAUDE3_OPUS = "claude-3-opus"
ANTHROPIC_CLAUDE3_SONNET = "claude-3-sonnet"
ANTHROPIC_CLAUDE3_HAIKU = "claude-3-haiku"
ANTHROPIC_CLAUDE_SONNET4_SHORT = "claude-sonnet-4"
# Anthropic — release aliases without dated suffix (latest stable pointers)
ANTHROPIC_CLAUDE_SONNET4_6 = "claude-sonnet-4-6"
ANTHROPIC_CLAUDE_OPUS4_6 = "claude-opus-4-6"

# Google — Gemini 2.5
GOOGLE_GEMINI25_PRO = "gemini-2.5-pro"
GOOGLE_GEMINI25_FLASH = "gemini-2.5-flash"
# Google — Gemini 2.0 / 1.5
GOOGLE_GEMINI20_FLASH = "gemini-2.0-flash"
GOOGLE_GEMINI15_PRO = "gemini-1.5-pro"
GOOGLE_GEMINI15_FLASH = "gemini-1.5-flash"
# Google — legacy models
GOOGLE_GEMINI_PRO = "gemini-pro"          # plain base model (distinct from vision)
GOOGLE_GEMINI_PRO_VISION = "gemini-pro-vision"

# DeepSeek hosted API
DEEPSEEK_V3 = "deepseek-v3"
DEEPSEEK_R1_API = "deepseek-r1-api"

# Local / Ollama free models
LOCAL_LLAMA3 = "llama3"
LOCAL_LLAMA31 = "llama3.1"
LOCAL_LLAMA32 = "llama3.2"
LOCAL_LLAMA33 = "llama3.3"
LOCAL_MISTRAL = "mistral"
LOCAL_MIXTRAL = "mixtral"
LOCAL_CODELLAMA = "codellama"
LOCAL_QWEN25 = "qwen2.5"
LOCAL_QWEN3 = "qwen3"
LOCAL_DEEPSEEK_CODER = "deepseek-coder"
LOCAL_DEEPSEEK_R1 = "deepseek-r1"
LOCAL_PHI3 = "phi3"
LOCAL_PHI4 = "phi4"
LOCAL_GEMMA2 = "gemma2"
LOCAL_GEMMA3 = "gemma3"

# Substring markers used by cost/efficiency heuristics (#3528)
# These are substrings matched with ``in model.lower()``, not full model IDs.
EXPENSIVE_MODEL_MARKER_OPUS = "opus"
EXPENSIVE_MODEL_MARKER_GPT4 = "gpt-4"

# Fallback model aliases — defined after constants to reference them directly
FALLBACK_OPENAI_MODEL = OPENAI_GPT4
FALLBACK_ANTHROPIC_MODEL = ANTHROPIC_CLAUDE35_SONNET
FALLBACK_GOOGLE_MODEL = GOOGLE_GEMINI_PRO

# =============================================================================
# MODEL_PRICING — SINGLE SOURCE OF TRUTH (#3528)
# =============================================================================
# Two formats are needed by different consumers; both derive from the same data.
#
# MODEL_PRICING_PER_1M_TOKENS  — USD per 1 million tokens (llm_cost_tracker)
#   keys: "input", "output"
#
# MODEL_PRICING_PER_1K_TOKENS  — USD per 1 thousand tokens (calculators.py,
#   CostCalculator)  keys: "prompt", "completion"
#
# Pricing source: provider published rates as of 2026-03.
# Update PRICING_VERSION in llm_cost_tracker.py when editing these tables.

MODEL_PRICING_PER_1M_TOKENS: Dict[str, Dict[str, float]] = {
    # Anthropic Claude 4.x (2025-2026)
    ANTHROPIC_CLAUDE_OPUS4: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE_HAIKU4_5: {"input": 0.80, "output": 4.00},
    # Anthropic Claude 3.x / Sonnet 4
    ANTHROPIC_CLAUDE_SONNET4: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE35_SONNET: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE35_HAIKU: {"input": 0.80, "output": 4.00},
    ANTHROPIC_CLAUDE3_OPUS_DATED: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE3_SONNET_DATED: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE3_HAIKU_DATED: {"input": 0.25, "output": 1.25},
    # OpenAI GPT-4.1 family (2025)
    OPENAI_GPT41: {"input": 2.00, "output": 8.00},
    OPENAI_GPT41_MINI: {"input": 0.40, "output": 1.60},
    OPENAI_GPT41_NANO: {"input": 0.10, "output": 0.40},
    # OpenAI GPT-4o / GPT-4 / GPT-3.5
    OPENAI_GPT4O: {"input": 2.50, "output": 10.00},
    OPENAI_GPT4O_MINI: {"input": 0.15, "output": 0.60},
    OPENAI_GPT4_TURBO: {"input": 10.00, "output": 30.00},
    OPENAI_GPT4: {"input": 30.00, "output": 60.00},
    OPENAI_GPT35_TURBO: {"input": 0.50, "output": 1.50},
    # OpenAI reasoning models
    OPENAI_O1: {"input": 15.00, "output": 60.00},
    OPENAI_O1_MINI: {"input": 3.00, "output": 12.00},
    OPENAI_O3: {"input": 2.00, "output": 8.00},
    OPENAI_O3_MINI: {"input": 1.10, "output": 4.40},
    OPENAI_O4_MINI: {"input": 1.10, "output": 4.40},
    # Google Gemini 2.5 (2025-2026)
    GOOGLE_GEMINI25_PRO: {"input": 1.25, "output": 10.00},
    GOOGLE_GEMINI25_FLASH: {"input": 0.15, "output": 0.60},
    # Google Gemini 2.0 / 1.5
    GOOGLE_GEMINI20_FLASH: {"input": 0.10, "output": 0.40},
    GOOGLE_GEMINI15_PRO: {"input": 1.25, "output": 5.00},
    GOOGLE_GEMINI15_FLASH: {"input": 0.075, "output": 0.30},
    # DeepSeek hosted API models (2025)
    DEEPSEEK_V3: {"input": 0.27, "output": 1.10},
    DEEPSEEK_R1_API: {"input": 0.55, "output": 2.19},
    # Local/Ollama models (free)
    LOCAL_LLAMA3: {"input": 0.0, "output": 0.0},
    LOCAL_LLAMA31: {"input": 0.0, "output": 0.0},
    LOCAL_LLAMA32: {"input": 0.0, "output": 0.0},
    LOCAL_LLAMA33: {"input": 0.0, "output": 0.0},
    LOCAL_MISTRAL: {"input": 0.0, "output": 0.0},
    LOCAL_MIXTRAL: {"input": 0.0, "output": 0.0},
    LOCAL_CODELLAMA: {"input": 0.0, "output": 0.0},
    LOCAL_QWEN25: {"input": 0.0, "output": 0.0},
    LOCAL_QWEN3: {"input": 0.0, "output": 0.0},
    LOCAL_DEEPSEEK_CODER: {"input": 0.0, "output": 0.0},
    LOCAL_DEEPSEEK_R1: {"input": 0.0, "output": 0.0},
    LOCAL_PHI3: {"input": 0.0, "output": 0.0},
    LOCAL_PHI4: {"input": 0.0, "output": 0.0},
    LOCAL_GEMMA2: {"input": 0.0, "output": 0.0},
    LOCAL_GEMMA3: {"input": 0.0, "output": 0.0},
}

# Per-1K token pricing used by TokenTracker / CostCalculator in
# code_intelligence/llm_pattern_analysis/calculators.py (#3528).
# Values are derived from MODEL_PRICING_PER_1M_TOKENS ÷ 1000.
MODEL_PRICING_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    OPENAI_GPT4: {"prompt": 0.03, "completion": 0.06},
    OPENAI_GPT4_TURBO: {"prompt": 0.01, "completion": 0.03},
    OPENAI_GPT4O: {"prompt": 0.005, "completion": 0.015},
    OPENAI_GPT35_TURBO: {"prompt": 0.0015, "completion": 0.002},
    ANTHROPIC_CLAUDE3_OPUS: {"prompt": 0.015, "completion": 0.075},
    ANTHROPIC_CLAUDE3_SONNET: {"prompt": 0.003, "completion": 0.015},
    ANTHROPIC_CLAUDE3_HAIKU: {"prompt": 0.00025, "completion": 0.00125},
    ANTHROPIC_CLAUDE_SONNET4_SHORT: {"prompt": 0.003, "completion": 0.015},
    "ollama": {"prompt": 0.0, "completion": 0.0},  # Local, no API cost
    "default": {"prompt": 0.001, "completion": 0.002},
}

# Per-1M token cost table used by analytics_llm_patterns.py (#3528).
# Keys use short-form names to match partial model identifiers submitted by
# clients (e.g. "claude-3-opus" instead of the full dated variant).
MODEL_COSTS_PER_1M_TOKENS: Dict[str, Dict[str, float]] = {
    # Anthropic (short-form names for analytics matching)
    ANTHROPIC_CLAUDE3_OPUS: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE3_SONNET: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE3_HAIKU: {"input": 0.25, "output": 1.25},
    ANTHROPIC_CLAUDE_SONNET4_SHORT: {"input": 3.00, "output": 15.00},
    # OpenAI
    OPENAI_GPT4O: {"input": 2.50, "output": 10.00},
    OPENAI_GPT4O_MINI: {"input": 0.15, "output": 0.60},
    OPENAI_GPT4_TURBO: {"input": 10.00, "output": 30.00},
    OPENAI_GPT35_TURBO: {"input": 0.50, "output": 1.50},
    # Google
    GOOGLE_GEMINI15_PRO: {"input": 1.25, "output": 5.00},
    GOOGLE_GEMINI15_FLASH: {"input": 0.075, "output": 0.30},
    # Local (free)
    LOCAL_LLAMA3: {"input": 0.0, "output": 0.0},
    LOCAL_MISTRAL: {"input": 0.0, "output": 0.0},
    LOCAL_CODELLAMA: {"input": 0.0, "output": 0.0},
}


class ModelConstants:
    """
    LLM Model configuration constants for AutoBot.

    SSOT Migration (Issue #763):
        All models now use ConfigRegistry with five-tier fallback.

    Issue #1882: ConfigRegistry calls removed from class body to break the
    circular import triggered during ConfigManager init. Class attributes now
    hold static defaults; use ConfigRegistry directly for live Redis-backed
    values:
        from config.registry import ConfigRegistry
        model = ConfigRegistry.get("llm.default_model", DEFAULT_LLM_MODEL)

    Usage remains unchanged for backward compatibility:
        from constants.model_constants import ModelConstants
        model = ModelConstants.DEFAULT_OLLAMA_MODEL
    """

    # =========================================================================
    # DEFAULT MODELS - Static fallback values (Issue #1882: no import-time
    # ConfigRegistry calls — use ConfigRegistry directly for live values)
    # =========================================================================

    DEFAULT_OLLAMA_MODEL: str = FALLBACK_MODEL
    DEFAULT_OPENAI_MODEL: str = FALLBACK_OPENAI_MODEL
    DEFAULT_ANTHROPIC_MODEL: str = FALLBACK_ANTHROPIC_MODEL
    DEFAULT_GOOGLE_MODEL: str = FALLBACK_GOOGLE_MODEL

    # Role-specific models — 6-tier mapping from SSOT constants (#2553)
    EMBEDDING_MODEL: str = DEFAULT_EMBEDDING_MODEL
    CLASSIFICATION_MODEL: str = SSOT_CLASSIFICATION_MODEL
    LIGHT_PROCESSING_MODEL: str = SSOT_LIGHT_PROCESSING_MODEL
    INSTRUCTION_MODEL: str = SSOT_INSTRUCTION_MODEL
    SYSTEM_MODEL: str = SSOT_SYSTEM_MODEL
    REASONING_MODEL: str = SSOT_QUALITY_MODEL
    RAG_MODEL: str = SSOT_INSTRUCTION_MODEL
    CODING_MODEL: str = SSOT_QUALITY_MODEL
    ORCHESTRATOR_MODEL: str = SSOT_ROUTING_MODEL

    # =========================================================================
    # MODEL PROVIDERS
    # =========================================================================

    PROVIDER_OLLAMA: str = "ollama"
    PROVIDER_OPENAI: str = "openai"
    PROVIDER_ANTHROPIC: str = "anthropic"
    PROVIDER_GOOGLE: str = "google"
    PROVIDER_LM_STUDIO: str = "lm_studio"

    # Current provider - static default; use ConfigRegistry for live value
    CURRENT_PROVIDER: str = "ollama"

    # =========================================================================
    # MODEL ENDPOINTS
    # =========================================================================

    @staticmethod
    def get_ollama_url() -> str:
        """
        Get Ollama service URL.

        Issue #763: Now uses ConfigRegistry with NetworkConstants fallback.
        Issue #1882: ConfigRegistry imported lazily inside method body to
        avoid circular imports during ConfigManager init.
        """
        from config.registry import ConfigRegistry
        from constants.network_constants import NetworkConstants

        host = ConfigRegistry.get("vm.ollama", NetworkConstants.AI_STACK_VM_IP)
        port = ConfigRegistry.get("port.ollama", str(NetworkConstants.OLLAMA_PORT))
        return f"http://{host}:{port}"

    @staticmethod
    def get_lm_studio_url() -> str:
        """Get LM Studio service URL from environment or default"""
        from constants.network_constants import NetworkConstants

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

    # Timeouts (in seconds)
    # Issue #763: Was ConfigRegistry.get("timeout.llm", "30").
    # Issue #1882: Moved to static default to break circular import during
    # ConfigManager init. Registry default for "timeout.llm" is 120 (see
    # config/registry_defaults.py). Use ConfigRegistry directly for live value:
    #   from config.registry import ConfigRegistry
    #   timeout = int(ConfigRegistry.get("timeout.llm", "120"))
    DEFAULT_TIMEOUT: int = 120
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

    # MMR diversity scoring (Issue #2090)
    # 0.0 = disabled (pure relevance); 1.0 = pure diversity; 0.5 = balanced
    RAG_MMR_LAMBDA: float = 0.0


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

    Issue #763: Prefer using ConfigRegistry directly:
        from config.registry import ConfigRegistry
        model = ConfigRegistry.get("llm.default_model", DEFAULT_LLM_MODEL)

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

    Issue #763: Prefer using ConfigRegistry directly:
        from config.registry import ConfigRegistry
        host = ConfigRegistry.get("vm.ollama")
        port = ConfigRegistry.get("port.ollama")

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
