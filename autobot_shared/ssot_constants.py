#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import os
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, FrozenSet

# ============================================================================
# API CONSTANTS
# ============================================================================

PATH_HEALTH = "/health"
PATH_API_HEALTH = "/api/health"
PATH_OLLAMA_GENERATE = "/api/generate"
PATH_OLLAMA_CHAT = "/api/chat"
PATH_OLLAMA_TAGS = "/api/tags"


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
ERR_INVALID_TOKEN = "Invalid token"


# ============================================================================
# MODEL CONSTANTS (imported from ssot_config)
# ============================================================================

from autobot_shared.ssot_config import (
    CLASSIFICATION_MODEL as SSOT_CLASSIFICATION_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    INSTRUCTION_MODEL as SSOT_INSTRUCTION_MODEL,
    LIGHT_PROCESSING_MODEL as SSOT_LIGHT_PROCESSING_MODEL,
    QUALITY_MODEL as SSOT_QUALITY_MODEL,
    ROUTING_MODEL as SSOT_ROUTING_MODEL,
    SYSTEM_MODEL as SSOT_SYSTEM_MODEL,
    config,
)

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
    """Model configuration settings"""

    DEFAULT_CONTEXT_LENGTH: int = 8192
    MAX_CONTEXT_LENGTH: int = 32768
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 0.9


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
    FRONTEND_DIR: Path = PROJECT_ROOT / "autobot-frontend"


PATH = PathConstants()


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


# ============================================================================
# TTL CONSTANTS
# ============================================================================

TTL_5_MINUTES = 300
TTL_1_HOUR = 3_600
TTL_24_HOURS = 86_400
TTL_7_DAYS = 86_400 * 7
TTL_30_DAYS = 86_400 * 30

TIMEOUT_HTTP_DEFAULT: float = 60.0
TIMEOUT_HTTP_LONG: float = 120.0


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

HIGH_RISK_INTENTS = frozenset({
    "shutdown",
    "restart",
    "delete",
    "uninstall",
    "request_manual_control",
    "emergency",
})

NUMBER_RE = re.compile(r"\b\d+\b")
QUOTED_TEXT_RE = re.compile(r'"([^"]*)"')
URL_RE = re.compile(r"https?://[^\s]+")


def match_intent_from_patterns(transcription: str, patterns: list, default: str) -> str:
    """Match transcription against intent patterns."""
    for pattern, intent in patterns:
        if re.search(pattern, transcription):
            return intent
    return default
