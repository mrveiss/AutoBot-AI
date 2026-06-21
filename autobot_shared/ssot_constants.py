#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Consolidated Constants - Single Source of Truth
================================================

All AutoBot constants consolidated from 12 domain-specific files.

This module replaces:
  - autobot-backend/constants/api_constants.py
  - autobot-backend/constants/error_constants.py
  - autobot-backend/constants/model_constants.py
  - autobot-backend/constants/network_constants.py (re-export shim → autobot_shared/network_constants)
  - autobot-backend/constants/path_constants.py
  - autobot-backend/constants/redis_constants.py
  - autobot-backend/constants/security_constants.py
  - autobot-backend/constants/terminal_constants.py
  - autobot-backend/constants/threshold_constants.py
  - autobot-backend/constants/ttl_constants.py
  - autobot-backend/code_intelligence/security/constants.py
  - autobot-backend/voice_processing/constants.py
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List

# ============================================================================
# API CONSTANTS
# ============================================================================

PATH_HEALTH = "/health"
PATH_API_HEALTH = "/api/health"
PATH_OLLAMA_GENERATE = "/api/generate"
PATH_OLLAMA_CHAT = "/api/chat"
PATH_OLLAMA_TAGS = "/api/tags"
PATH_OLLAMA_PULL = "/api/pull"


# ============================================================================
# ERROR CONSTANTS
# ============================================================================

ERR_ASSESSMENT_NOT_FOUND = "Assessment not found"
ERR_SESSION_NOT_FOUND = "Session not found"
ERR_FILE_NOT_FOUND = "File not found"
ERR_DIRECTORY_NOT_FOUND = "Directory not found"
ERR_FILE_OR_DIR_NOT_FOUND = "File or directory not found"
ERR_PATH_NOT_FOUND = "Path not found"
ERR_CONNECTOR_NOT_FOUND = "Connector not found"
ERR_JOB_NOT_FOUND = "Job not found"
ERR_TEMPLATE_NOT_FOUND = "Template not found"
ERR_WORKFLOW_NOT_FOUND = "Workflow not found"
ERR_EXPERIMENT_NOT_FOUND = "Experiment not found"
ERR_INVALID_CREDENTIALS = "Invalid username or password"
ERR_INVALID_TOKEN = "Invalid token"  # nosec B105 - user-facing error message string, not a credential


# ============================================================================
# MODEL CONSTANTS (imported from ssot_config)
# ============================================================================

from autobot_shared.ssot_config import CLASSIFICATION_MODEL as SSOT_CLASSIFICATION_MODEL
from autobot_shared.ssot_config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
)
from autobot_shared.ssot_config import INSTRUCTION_MODEL as SSOT_INSTRUCTION_MODEL
from autobot_shared.ssot_config import LIGHT_PROCESSING_MODEL as SSOT_LIGHT_PROCESSING_MODEL
from autobot_shared.ssot_config import QUALITY_MODEL as SSOT_QUALITY_MODEL
from autobot_shared.ssot_config import ROUTING_MODEL as SSOT_ROUTING_MODEL
from autobot_shared.ssot_config import SYSTEM_MODEL as SSOT_SYSTEM_MODEL

FALLBACK_MODEL = DEFAULT_LLM_MODEL

OPENAI_O1_PREVIEW = "o1-preview"
OPENAI_GPT4 = "gpt-4"
OPENAI_GPT4_TURBO = "gpt-4-turbo"
OPENAI_GPT4O = "gpt-4o"
OPENAI_GPT4O_MINI = "gpt-4o-mini"
OPENAI_GPT4_VISION_PREVIEW = "gpt-4-vision-preview"
OPENAI_GPT4_TURBO_PREVIEW = "gpt-4-turbo-preview"
OPENAI_GPT35_TURBO = "gpt-3.5-turbo"
OPENAI_GPT35_TURBO_16K = "gpt-3.5-turbo-16k"
OPENAI_O1 = "o1"
OPENAI_O1_MINI = "o1-mini"
OPENAI_O3 = "o3"
OPENAI_O3_MINI = "o3-mini"
OPENAI_O4_MINI = "o4-mini"
OPENAI_GPT41 = "gpt-4.1"
OPENAI_GPT41_MINI = "gpt-4.1-mini"
OPENAI_GPT41_NANO = "gpt-4.1-nano"

ANTHROPIC_CLAUDE_OPUS4 = "claude-opus-4-20250514"
ANTHROPIC_CLAUDE_HAIKU4_5 = "claude-haiku-4-5-20251001"
ANTHROPIC_CLAUDE_SONNET4 = "claude-sonnet-4-20250514"
ANTHROPIC_CLAUDE35_SONNET = "claude-3-5-sonnet-20241022"
ANTHROPIC_CLAUDE35_HAIKU = "claude-3-5-haiku-20241022"
ANTHROPIC_CLAUDE3_OPUS_DATED = "claude-3-opus-20240229"
ANTHROPIC_CLAUDE3_SONNET_DATED = "claude-3-sonnet-20240229"
ANTHROPIC_CLAUDE3_HAIKU_DATED = "claude-3-haiku-20240307"

ANTHROPIC_CLAUDE3_OPUS = "claude-3-opus"
ANTHROPIC_CLAUDE3_SONNET = "claude-3-sonnet"
ANTHROPIC_CLAUDE3_HAIKU = "claude-3-haiku"
ANTHROPIC_CLAUDE_SONNET4_SHORT = "claude-sonnet-4"
ANTHROPIC_CLAUDE_SONNET4_6 = "claude-sonnet-4-6"
ANTHROPIC_CLAUDE_OPUS4_6 = "claude-opus-4-6"

GOOGLE_GEMINI25_PRO = "gemini-2.5-pro"
GOOGLE_GEMINI25_FLASH = "gemini-2.5-flash"
GOOGLE_GEMINI20_FLASH = "gemini-2.0-flash"
GOOGLE_GEMINI15_PRO = "gemini-1.5-pro"
GOOGLE_GEMINI15_FLASH = "gemini-1.5-flash"
GOOGLE_GEMINI_PRO = "gemini-pro"
GOOGLE_GEMINI_PRO_VISION = "gemini-pro-vision"

GROQ_LLAMA3_8B = "llama3-8b-8192"
GROQ_LLAMA3_70B = "llama3-70b-8192"
GROQ_LLAMA31_8B = "llama-3.1-8b-instant"
GROQ_LLAMA33_70B = "llama-3.3-70b-versatile"
GROQ_MIXTRAL_8X7B = "mixtral-8x7b-32768"
GROQ_GEMMA2_9B = "gemma2-9b-it"

DEEPSEEK_V3 = "deepseek-v3"
DEEPSEEK_R1_API = "deepseek-r1-api"

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

EXPENSIVE_MODEL_MARKER_OPUS = "opus"
EXPENSIVE_MODEL_MARKER_GPT4 = "gpt-4"

FALLBACK_OPENAI_MODEL = OPENAI_GPT4
FALLBACK_ANTHROPIC_MODEL = ANTHROPIC_CLAUDE35_SONNET
FALLBACK_GOOGLE_MODEL = GOOGLE_GEMINI_PRO


@dataclass(frozen=True)
class ModelConfig:
    """Model configuration settings — generation parameters and limits."""

    DEFAULT_CONTEXT_LENGTH: int = 8192
    MAX_CONTEXT_LENGTH: int = 32768
    MAX_HISTORY_TOKENS: int = 3000

    # RAG context-length optimization (by complexity score)
    RAG_CONTEXT_HIGH_COMPLEXITY: int = 3000
    RAG_CONTEXT_MEDIUM_COMPLEXITY: int = 2500
    RAG_CONTEXT_LOW_COMPLEXITY: int = 2000

    # RAG chunk-count optimization
    RAG_CHUNKS_HIGH_COMPLEXITY: int = 8
    RAG_CHUNKS_MEDIUM_COMPLEXITY: int = 6
    RAG_CHUNKS_LOW_COMPLEXITY: int = 5

    # Model-size thresholds (MB)
    MODEL_SIZE_LIGHTWEIGHT_THRESHOLD_MB: int = 1000
    MODEL_SIZE_MODERATE_THRESHOLD_MB: int = 3000

    # Generation parameters
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 0.9
    DEFAULT_TOP_K: int = 40
    DEFAULT_REPEAT_PENALTY: float = 1.1
    DEFAULT_MAX_TOKENS: int = 2048
    DEFAULT_NUM_CTX: int = 4096
    CHAT_NUM_CTX: int = 8192

    # Timeouts (seconds)
    DEFAULT_TIMEOUT: int = 120
    LONG_GENERATION_TIMEOUT: int = 120

    # Retry settings
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2

    # Performance settings
    DEFAULT_CONNECTION_POOL_SIZE: int = 20
    DEFAULT_MAX_CONCURRENT_REQUESTS: int = 8
    DEFAULT_CACHE_TTL: int = 300  # TTL_5_MINUTES — hardcoded to avoid forward-ref
    DEFAULT_MAX_CHUNKS: int = 1000

    # RAG search settings
    RAG_DEFAULT_MAX_RESULTS: int = 5
    RAG_MAX_RESULTS_PER_STAGE: int = 20
    RAG_HYBRID_WEIGHT_SEMANTIC: float = 0.7
    RAG_HYBRID_WEIGHT_KEYWORD: float = 0.3
    RAG_DIVERSITY_THRESHOLD: float = 0.85
    RAG_DEFAULT_CONTEXT_LENGTH: int = 2000
    RAG_MAX_CONTEXT_LENGTH: int = 5000

    # MMR diversity scoring (0.0 = pure relevance, 1.0 = pure diversity)
    RAG_MMR_LAMBDA: float = 0.0


class ModelConstants:
    """LLM Model configuration constants for AutoBot."""

    DEFAULT_OLLAMA_MODEL: str = FALLBACK_MODEL
    DEFAULT_OPENAI_MODEL: str = FALLBACK_OPENAI_MODEL
    DEFAULT_ANTHROPIC_MODEL: str = FALLBACK_ANTHROPIC_MODEL
    DEFAULT_GOOGLE_MODEL: str = FALLBACK_GOOGLE_MODEL

    EMBEDDING_MODEL: str = DEFAULT_EMBEDDING_MODEL
    CLASSIFICATION_MODEL: str = SSOT_CLASSIFICATION_MODEL
    LIGHT_PROCESSING_MODEL: str = SSOT_LIGHT_PROCESSING_MODEL
    INSTRUCTION_MODEL: str = SSOT_INSTRUCTION_MODEL
    SYSTEM_MODEL: str = SSOT_SYSTEM_MODEL
    REASONING_MODEL: str = SSOT_QUALITY_MODEL
    RAG_MODEL: str = SSOT_INSTRUCTION_MODEL
    CODING_MODEL: str = SSOT_QUALITY_MODEL
    ORCHESTRATOR_MODEL: str = SSOT_ROUTING_MODEL

    PROVIDER_OLLAMA: str = "ollama"
    PROVIDER_OPENAI: str = "openai"
    PROVIDER_ANTHROPIC: str = "anthropic"
    PROVIDER_GOOGLE: str = "google"
    PROVIDER_LM_STUDIO: str = "lm_studio"

    CURRENT_PROVIDER: str = "ollama"

    @staticmethod
    def get_ollama_url() -> str:
        """Get Ollama service URL (lazy import to avoid circular imports)."""
        from config.registry import ConfigRegistry  # noqa: PLC0415
        from constants.network_constants import NetworkConstants  # noqa: PLC0415

        host = ConfigRegistry.get("vm.ollama", NetworkConstants.AI_STACK_VM_IP)
        port = ConfigRegistry.get("port.ollama", str(NetworkConstants.OLLAMA_PORT))
        return f"http://{host}:{port}"

    @staticmethod
    def get_lm_studio_url() -> str:
        """Get LM Studio service URL."""
        from autobot_shared.ssot_config import config as _cfg  # noqa: PLC0415

        return _cfg.llm.lmstudio_host


# ============================================================================
# MODEL PRICING (GH#7750: missing from original GH#7440 migration)
# ============================================================================

MODEL_PRICING_PER_1M_TOKENS: Dict[str, Dict[str, float]] = {
    ANTHROPIC_CLAUDE_OPUS4: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE_HAIKU4_5: {"input": 0.80, "output": 4.00},
    ANTHROPIC_CLAUDE_SONNET4: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE35_SONNET: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE35_HAIKU: {"input": 0.80, "output": 4.00},
    ANTHROPIC_CLAUDE3_OPUS_DATED: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE3_SONNET_DATED: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE3_HAIKU_DATED: {"input": 0.25, "output": 1.25},
    OPENAI_GPT41: {"input": 2.00, "output": 8.00},
    OPENAI_GPT41_MINI: {"input": 0.40, "output": 1.60},
    OPENAI_GPT41_NANO: {"input": 0.10, "output": 0.40},
    OPENAI_GPT4O: {"input": 2.50, "output": 10.00},
    OPENAI_GPT4O_MINI: {"input": 0.15, "output": 0.60},
    OPENAI_GPT4_TURBO: {"input": 10.00, "output": 30.00},
    OPENAI_GPT4: {"input": 30.00, "output": 60.00},
    OPENAI_GPT35_TURBO: {"input": 0.50, "output": 1.50},
    OPENAI_O1: {"input": 15.00, "output": 60.00},
    OPENAI_O1_MINI: {"input": 3.00, "output": 12.00},
    OPENAI_O3: {"input": 2.00, "output": 8.00},
    OPENAI_O3_MINI: {"input": 1.10, "output": 4.40},
    OPENAI_O4_MINI: {"input": 1.10, "output": 4.40},
    GOOGLE_GEMINI25_PRO: {"input": 1.25, "output": 5.00},
    GOOGLE_GEMINI25_FLASH: {"input": 0.075, "output": 0.30},
    GOOGLE_GEMINI20_FLASH: {"input": 0.075, "output": 0.30},
    GOOGLE_GEMINI15_PRO: {"input": 1.25, "output": 5.00},
    GOOGLE_GEMINI15_FLASH: {"input": 0.075, "output": 0.30},
    DEEPSEEK_V3: {"input": 0.27, "output": 1.10},
    DEEPSEEK_R1_API: {"input": 0.55, "output": 2.19},
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

MODEL_PRICING_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    OPENAI_GPT4: {"prompt": 0.03, "completion": 0.06},
    OPENAI_GPT4_TURBO: {"prompt": 0.01, "completion": 0.03},
    OPENAI_GPT4O: {"prompt": 0.005, "completion": 0.015},
    OPENAI_GPT35_TURBO: {"prompt": 0.0015, "completion": 0.002},
    ANTHROPIC_CLAUDE3_OPUS: {"prompt": 0.015, "completion": 0.075},
    ANTHROPIC_CLAUDE3_SONNET: {"prompt": 0.003, "completion": 0.015},
    ANTHROPIC_CLAUDE3_HAIKU: {"prompt": 0.00025, "completion": 0.00125},
    ANTHROPIC_CLAUDE_SONNET4_SHORT: {"prompt": 0.003, "completion": 0.015},
    "ollama": {"prompt": 0.0, "completion": 0.0},
    "default": {"prompt": 0.001, "completion": 0.002},
}

MODEL_COSTS_PER_1M_TOKENS: Dict[str, Dict[str, float]] = {
    ANTHROPIC_CLAUDE3_OPUS: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE3_SONNET: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE3_HAIKU: {"input": 0.25, "output": 1.25},
    ANTHROPIC_CLAUDE_SONNET4_SHORT: {"input": 3.00, "output": 15.00},
    OPENAI_GPT4O: {"input": 2.50, "output": 10.00},
    OPENAI_GPT4O_MINI: {"input": 0.15, "output": 0.60},
    OPENAI_GPT4_TURBO: {"input": 10.00, "output": 30.00},
    OPENAI_GPT35_TURBO: {"input": 0.50, "output": 1.50},
    GOOGLE_GEMINI15_PRO: {"input": 1.25, "output": 5.00},
    GOOGLE_GEMINI15_FLASH: {"input": 0.075, "output": 0.30},
    LOCAL_LLAMA3: {"input": 0.0, "output": 0.0},
    LOCAL_MISTRAL: {"input": 0.0, "output": 0.0},
    LOCAL_CODELLAMA: {"input": 0.0, "output": 0.0},
}

# Singleton instances (backward compat with constants.model_constants imports)
model_constants = ModelConstants()
model_config = ModelConfig()


@lru_cache(maxsize=8)
def get_default_model(provider: str | None = None) -> str:
    """Get the default model for a specific provider or the system default."""
    if provider == ModelConstants.PROVIDER_OLLAMA:
        return ModelConstants.DEFAULT_OLLAMA_MODEL
    elif provider == ModelConstants.PROVIDER_OPENAI:
        return ModelConstants.DEFAULT_OPENAI_MODEL
    elif provider == ModelConstants.PROVIDER_ANTHROPIC:
        return ModelConstants.DEFAULT_ANTHROPIC_MODEL
    elif provider == ModelConstants.PROVIDER_GOOGLE:
        return ModelConstants.DEFAULT_GOOGLE_MODEL
    return ModelConstants.DEFAULT_OLLAMA_MODEL


@lru_cache(maxsize=8)
def get_model_endpoint(provider: str) -> str:
    """Get the endpoint URL for a specific provider."""
    if provider == ModelConstants.PROVIDER_OLLAMA:
        return ModelConstants.get_ollama_url()
    elif provider == ModelConstants.PROVIDER_LM_STUDIO:
        return ModelConstants.get_lm_studio_url()
    raise ValueError(f"Unknown provider: {provider}")


# ============================================================================
# PATH CONSTANTS
# ============================================================================


@dataclass(frozen=True)
class PathConstants:
    """Centralized path constants"""

    PROJECT_ROOT: Path = Path(__file__).parent.parent
    CONFIG_DIR: Path = PROJECT_ROOT / "infrastructure" / "shared" / "config"
    DATA_DIR: Path = PROJECT_ROOT / "data"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    DOCS_DIR: Path = PROJECT_ROOT / "docs"
    BACKEND_DIR: Path = PROJECT_ROOT / "autobot-backend"
    STATIC_DIR: Path = PROJECT_ROOT / "autobot-backend" / "static"
    FRONTEND_DIR: Path = PROJECT_ROOT / "autobot-frontend"
    TESTS_DIR: Path = PROJECT_ROOT / "autobot-backend"
    # Temp/generated-files dir cleaned by tasks.cleanup_generated_files (#10385-adjacent)
    TEMP_DIR: Path = DATA_DIR / "temp"


PATH = PathConstants()

# GH#8947: Disk-persisted Phase 1 error file written by lifespan.py before
# process exit. /run/autobot/ is created by Ansible and owned by autobot user.
STARTUP_ERROR_FILE = Path("/run/autobot/startup-error.json")


# ============================================================================
# REDIS CONSTANTS
# ============================================================================


@dataclass(frozen=True)
class RedisKeyConstants:
    """Centralized Redis key patterns"""

    NAMESPACE: str = "autobot"
    PROMPTS_FILE_STATES: str = f"{NAMESPACE}:prompts:file_states"
    SYSTEM_KNOWLEDGE_FILE_STATES: str = f"{NAMESPACE}:system_knowledge:file_states"
    WORKFLOW_CLASSIFICATION_RULES: str = f"{NAMESPACE}:workflow:classification:rules"
    CHAT_RECENT: str = "chat:recent"
    CHAT_FOLDERS: str = "chat:folders:{username}"
    LLM_MODELS_CACHE: str = "llm_models"


REDIS_KEY = RedisKeyConstants()


# ============================================================================
# SECURITY CONSTANTS
# ============================================================================


class SecurityConstants:
    """RFC-defined security constants"""

    BLOCKED_IP_RANGES: List[str] = [
        "0.0.0.0/8",
        "10.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
    ]

    # Web ports permitted for outbound/domain network validation (#10384).
    ALLOWED_WEB_PORTS: List[int] = [80, 443, 8080, 8443]

    USER_AGENT_POOL: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",  # noqa: E501
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",  # noqa: E501
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",  # noqa: E501
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",  # noqa: E501
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    ]


# ============================================================================
# TERMINAL CONSTANTS
# ============================================================================

RISKY_COMMAND_PATTERNS = [
    "rm -r",
    "sudo rm",
    "rmdir",
    "dd if=",
    "mkfs",
]

MODERATE_RISK_PATTERNS = [
    "sudo",
    "su -",
    "chmod",
    "chown",
]


# ============================================================================
# THRESHOLD CONSTANTS
# ============================================================================


class SecurityThresholds:
    """Security risk evaluation thresholds."""

    HIGH_RISK_THRESHOLD = 0.3
    BLOCK_THRESHOLD = 0.7


class AgentThresholds:
    """Agent response evaluation thresholds."""

    QUALITY_THRESHOLD = 0.7
    RELEVANCE_THRESHOLD = 0.8
    CONSENSUS_THRESHOLD = 0.8
    QUALITY_WEIGHT = 0.4
    RELEVANCE_WEIGHT = 0.3
    CONSISTENCY_WEIGHT = 0.3


class WorkflowThresholds:
    """Workflow step execution thresholds."""

    SAFETY_THRESHOLD = 0.7
    QUALITY_THRESHOLD = 0.6


class ComputerVisionThresholds:
    """Computer vision and UI element detection thresholds."""

    SEARCH_RESULT_LIMIT = 10
    SIMILARITY_THRESHOLD = 0.7


class CircuitBreakerDefaults:
    """Circuit breaker default values for service protection."""

    LLM_FAILURE_THRESHOLD = 3
    LLM_RECOVERY_TIMEOUT = 30.0
    LLM_TIMEOUT = 120.0
    DEFAULT_FAILURE_THRESHOLD = 5
    DEFAULT_RECOVERY_TIMEOUT = 60.0
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_SUCCESS_THRESHOLD = 3
    DATABASE_FAILURE_THRESHOLD = 5
    DATABASE_RECOVERY_TIMEOUT = 15.0
    DATABASE_TIMEOUT = 10.0
    DATABASE_SLOW_CALL_THRESHOLD = 2.0
    NETWORK_FAILURE_THRESHOLD = 3
    NETWORK_RECOVERY_TIMEOUT = 20.0
    NETWORK_TIMEOUT = 15.0
    SLOW_CALL_THRESHOLD = 10.0
    SLOW_CALL_RATE_THRESHOLD = 0.5
    MIN_CALLS_FOR_EVALUATION = 10
    RECENT_CALLS_WINDOW = 60.0
    PERFORMANCE_WINDOW = 300.0
    QUANTILE_SAMPLE_SIZE = 20
    MAX_HISTORY_SIZE = 100
    CONSECUTIVE_RESET_ON_SUCCESS = True


class VoiceRecognitionConfig:
    """Voice recognition system configuration."""

    ENERGY_THRESHOLD = 300
    PAUSE_THRESHOLD = 0.8
    PHRASE_THRESHOLD = 0.3


class CacheConfig:
    """Cache configuration constants."""

    EMBEDDING_CACHE_MAX_SIZE = 1000
    EMBEDDING_CACHE_TTL_SECONDS = 3600
    DATABASE_CACHE_SIZE = 10000


class KnowledgeSyncConfig:
    """Knowledge synchronization configuration."""

    MAX_CONCURRENT_FILES = 4
    CHUNK_BATCH_SIZE = 50


class TimingConstants:
    """Common timing values used throughout the codebase."""

    YIELD_INTERVAL = 0.001
    POLL_INTERVAL = 0.01
    FAST_POLL_INTERVAL = 0.02
    STREAMING_CHUNK_DELAY = 0.05
    MICRO_DELAY = 0.1
    DEBOUNCE_INTERVAL_S = 0.2
    SHORT_DELAY = 0.5
    STANDARD_DELAY = 1.0
    MEDIUM_DELAY = 5.0
    LONG_DELAY = 10.0
    SHORT_TIMEOUT = 30
    STANDARD_TIMEOUT = 60
    LONG_TIMEOUT = 120
    VERY_LONG_TIMEOUT = 300
    SESSION_CLEANUP_INTERVAL = 60
    HOURLY_INTERVAL = 3600
    ERROR_RECOVERY_DELAY = 5.0
    ERROR_RECOVERY_LONG_DELAY = 30.0
    SERVICE_STARTUP_DELAY = 2.0
    KB_INIT_DELAY = 3.0


def exponential_backoff_delay(attempt: int, base: float = 2.0, cap: float = 60.0) -> float:
    """Return capped exponential backoff delay in seconds."""
    return min(base**attempt, cap)


class RetryConfig:
    """Retry configuration constants."""

    MIN_RETRIES = 2
    DEFAULT_RETRIES = 3
    MAX_RETRIES = 5
    BACKOFF_BASE = 2.0
    BACKOFF_MAX_DELAY = 60.0


class BatchConfig:
    """Batch processing configuration."""

    DEFAULT_CONCURRENCY = 10
    HIGH_CONCURRENCY = 50
    MAX_CONCURRENCY = 100
    SMALL_BATCH = 10
    MEDIUM_BATCH = 50
    LARGE_BATCH = 100


class LLMDefaults:
    """Default values for LLM inference operations."""

    MINIMAL_MAX_TOKENS = 10
    SHORT_MAX_TOKENS = 50
    COMMAND_MAX_TOKENS = 75
    DEFAULT_MAX_TOKENS = 100
    RETRIEVAL_MAX_TOKENS = 150
    ANALYSIS_MAX_TOKENS = 200
    CONCISE_MAX_TOKENS = 256
    STANDARD_MAX_TOKENS = 500
    CHAT_MAX_TOKENS = 512
    ENRICHED_MAX_TOKENS = 1000
    SYNTHESIS_MAX_TOKENS = 1024
    EXTENDED_MAX_TOKENS = 1500
    LONG_MAX_TOKENS = 2048
    VERY_LONG_MAX_TOKENS = 4000
    KNOWLEDGE_MAX_TOKENS = 2048
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_TOP_P = 0.9
    DEFAULT_CONCURRENT_WORKERS = 3


class ResourceThresholds:
    """System resource monitoring thresholds."""

    MEMORY_WARNING_THRESHOLD = 0.8
    MEMORY_CRITICAL_THRESHOLD = 0.9
    CPU_HIGH_THRESHOLD = 0.9
    CPU_OPTIMAL_MAX = 0.2
    GPU_LOW_UTILIZATION = 0.2
    GPU_RECOMMENDATION_THRESHOLD = 0.3
    GPU_SATURATED = 0.95
    GPU_BUSY_THRESHOLD = 80.0
    GPU_MODERATE_THRESHOLD = 70.0
    GPU_AVAILABLE_THRESHOLD = 60.0
    NPU_BUSY_THRESHOLD = 80.0
    NPU_AVAILABLE_THRESHOLD = 60.0
    HIGH_CORE_COUNT = 16


class AnalyticsConfig:
    """Code analytics and bug prediction configuration constants."""

    BUG_PREDICTION_TIMEOUT = 120.0
    DUPLICATE_DETECTION_TIMEOUT = 120.0
    BUG_PREDICTION_FILE_LIMIT = 0
    DUPLICATE_DETECTION_FILE_LIMIT = 0
    DUPLICATE_MIN_SIMILARITY = 0.5
    SEMANTIC_MIN_SIMILARITY = 0.6
    TOP_HIGH_RISK_FILES_LIMIT = 10
    API_ENDPOINT_LIST_LIMIT = 20
    BUG_PREDICTION_CACHE_TTL = 1800
    DUPLICATE_DETECTION_CACHE_TTL = 3600


class HardwareAcceleratorConfig:
    """Hardware accelerator configuration constants."""

    NPU_MAX_MODEL_SIZE_MB = 2000
    NPU_MAX_RESPONSE_TIME_S = 2.0
    NPU_BASE_TEMPERATURE_C = 45.0
    NPU_TEMP_UTILIZATION_FACTOR = 0.3
    NPU_BASE_POWER_W = 2.0
    NPU_MAX_POWER_W = 10.0
    NPU_MEMORY_MB = 1024.0
    NPU_UTILIZATION_PER_MODEL = 25.0
    HARDWARE_CHECK_INTERVAL_S = 30
    UNIFIED_EMBEDDING_DIM = 512
    MINILM_OUTPUT_DIM = 384
    CLIP_OUTPUT_DIM = 512
    WAV2VEC_OUTPUT_DIM = 768
    TEXT_LIGHTWEIGHT_LENGTH = 500
    TEXT_MODERATE_LENGTH = 2000
    DOC_LIGHTWEIGHT_COUNT = 100
    DOC_MODERATE_COUNT = 1000
    PERFORMANCE_FACTOR_CAP = 2.0


class WorkflowConfig:
    """Workflow scheduler configuration constants."""

    DEFAULT_MAX_CONCURRENT = 3
    SCHEDULER_CHECK_INTERVAL_S = 10
    SCHEDULER_ERROR_BACKOFF_S = 30
    PRIORITY_BASE_MULTIPLIER = 100
    MAX_OVERDUE_BONUS = 50
    OVERDUE_BONUS_RATE = 0.1
    DEPENDENCY_PENALTY = 0.9
    DEFAULT_ESTIMATED_DURATION_MIN = 30
    DEFAULT_TIMEOUT_MIN = 120
    MIN_DURATION_FACTOR = 0.5
    COMPLEXITY_SIMPLE = 0.8
    COMPLEXITY_RESEARCH = 1.0
    COMPLEXITY_INSTALL = 1.1
    COMPLEXITY_COMPLEX = 1.2
    COMPLEXITY_SECURITY_SCAN = 1.3


class ServiceDiscoveryConfig:
    """Service discovery and health monitoring configuration."""

    HEALTH_CHECK_INTERVAL_S = 30
    CIRCUIT_BREAKER_THRESHOLD = 5
    CIRCUIT_BREAKER_CHECK_MULTIPLIER = 2
    FRONTEND_TIMEOUT = 10.0
    NPU_WORKER_TIMEOUT = 15.0
    REDIS_TIMEOUT = 5.0
    AI_STACK_TIMEOUT = 20.0
    BROWSER_SERVICE_TIMEOUT = 10.0
    BACKEND_TIMEOUT = 5.0
    OLLAMA_TIMEOUT = 10.0
    SERVICE_WAIT_INTERVAL_S = 2
    CORE_SERVICES_WAIT_INTERVAL_S = 5
    ERROR_RECOVERY_DELAY_S = 5
    DEFAULT_SERVICE_WAIT_TIMEOUT = 60.0
    CORE_SERVICES_WAIT_TIMEOUT = 120.0


class StringParsingConstants:
    """String parsing constants for boolean/truthy value detection."""

    BOOL_STRING_VALUES = frozenset({"true", "false"})
    TRUTHY_STRING_VALUES = frozenset({"true", "1", "yes", "on"})
    FALSY_STRING_VALUES = frozenset({"false", "0", "no", "off"})


class FileWatcherConfig:
    """File watcher configuration for config file monitoring."""

    CHECK_INTERVAL_S = 1.0
    ERROR_RETRY_INTERVAL_S = 5.0


class QueryDefaults:
    """Default values for search, query, and pagination operations."""

    DEFAULT_SEARCH_LIMIT: int = 10
    DEFAULT_TOP_K: int = 10
    MAX_SEARCH_LIMIT: int = 100
    EXTENDED_SEARCH_LIMIT: int = 50
    LARGE_BATCH_LIMIT: int = 100
    DEFAULT_OFFSET: int = 0
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 500
    RAG_DEFAULT_RESULTS: int = 5
    RAG_MAX_RESULTS: int = 20
    KNOWLEDGE_DEFAULT_LIMIT: int = 100


class CategoryDefaults:
    """Default category and type values for classification."""

    GENERAL: str = "general"
    IMPORTED: str = "imported"
    UNKNOWN: str = "unknown"
    SEARCH_MODE_HYBRID: str = "hybrid"
    SEARCH_MODE_SEMANTIC: str = "semantic"
    SEARCH_MODE_KEYWORD: str = "keyword"
    QUERY_TYPE_GENERAL: str = "general"
    QUERY_TYPE_TECHNICAL: str = "technical"
    QUERY_TYPE_CODE: str = "code"
    CONTEXT_TYPE_GENERAL: str = "general"
    CONTEXT_TYPE_SECURITY: str = "security"
    CONTEXT_TYPE_RESEARCH: str = "research"
    ROLE_USER: str = "user"
    ROLE_ASSISTANT: str = "assistant"
    ROLE_SYSTEM: str = "system"
    MODE_DEVELOPMENT: str = "development"
    MODE_PRODUCTION: str = "production"
    MODE_TESTING: str = "testing"


class WorkStealingConfig:
    """Work-stealing configuration for distributed agent task reassignment."""

    STALE_TASK_TIMEOUT_SECONDS: int = 300
    GRACE_PERIOD_SECONDS: int = 300
    MAX_REASSIGNMENTS: int = 3
    PROGRESS_TTL_SECONDS: int = 60


class ProtocolDefaults:
    """Default protocol and endpoint values."""

    HTTP: str = "http"
    HTTPS: str = "https"
    WS: str = "ws"
    WSS: str = "wss"
    TCP: str = "tcp"
    API_VERSION: str = "1.0"


# ============================================================================
# TTL CONSTANTS
# ============================================================================

TTL_10_SECONDS = 10
TTL_5_MINUTES = 300
TTL_1_HOUR = 3_600
TTL_24_HOURS = 86_400
TTL_7_DAYS = 86_400 * 7
TTL_30_DAYS = 86_400 * 30
TTL_90_DAYS = 86_400 * 90
TTL_365_DAYS = 86_400 * 365
TTL_WORKING_MEMORY_DEFAULT = TTL_24_HOURS

TIMEOUT_HTTP_DEFAULT: float = 60.0
TIMEOUT_HTTP_LONG: float = 120.0
TIMEOUT_TASK_ANALYSIS: float = 300.0


# ============================================================================
# CODE INTELLIGENCE SECURITY CONSTANTS
# ============================================================================

PLACEHOLDER_PATTERNS = {"example", "placeholder", "your_", "xxx", "changeme", "todo"}

HTTP_METHODS: FrozenSet[str] = frozenset({"get", "post", "put", "delete", "patch", "route"})
INSECURE_RANDOM_FUNCS: FrozenSet[str] = frozenset({"random", "randint", "choice", "shuffle"})


# ============================================================================
# VOICE PROCESSING CONSTANTS
# ============================================================================

AUTOMATION_INTENT_PATTERNS = [
    (r"(?i)click", "click_element"),
    (r"(?i)type|enter", "type_text"),
    (r"(?i)open|start", "open_application"),
    (r"(?i)scroll", "scroll_page"),
]

HIGH_RISK_INTENTS = frozenset(
    {
        "shutdown",
        "restart",
        "delete",
        "uninstall",
        "request_manual_control",
        "emergency",
    }
)

NUMBER_RE = re.compile(r"\b\d+\b")
QUOTED_TEXT_RE = re.compile(r'"([^"]*)"')
URL_RE = re.compile(r"https?://[^\s]+")


def match_intent_from_patterns(transcription: str, patterns: list, default: str) -> str:
    """Match transcription against intent patterns."""
    for pattern, intent in patterns:
        if re.search(pattern, transcription):
            return intent
    return default
