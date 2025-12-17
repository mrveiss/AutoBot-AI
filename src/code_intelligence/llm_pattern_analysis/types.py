# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Pattern Analyzer Types Module

Contains enums, constants, and pre-compiled regex patterns for LLM pattern analysis.

Extracted from llm_pattern_analyzer.py as part of Issue #381 refactoring.
"""

import re
from enum import Enum
from typing import FrozenSet, List, Pattern


# =============================================================================
# Module-level Constants
# =============================================================================

# Performance optimization: O(1) lookup for LLM patterns (Issue #326)
SIMPLE_LLM_MODELS: FrozenSet[str] = frozenset({"gpt-3.5", "haiku", "llama"})

# Issue #380: Module-level frozenset for backoff strategy validation
VALID_BACKOFF_STRATEGIES: FrozenSet[str] = frozenset({"exponential", "linear"})


# =============================================================================
# Pre-compiled Regex Patterns (Issue #380)
# =============================================================================

# Patterns for prompt analysis - redundant instructions
REDUNDANT_PATTERNS: List[Pattern[str]] = [
    re.compile(r"please\s+please", re.IGNORECASE),
    re.compile(r"make\s+sure\s+to\s+make\s+sure", re.IGNORECASE),
    re.compile(r"you\s+must\s+always\s+you\s+must", re.IGNORECASE),
    re.compile(r"important:\s*important", re.IGNORECASE),
]

# Patterns for excessive context detection
EXCESSIVE_CONTEXT_PATTERNS: List[Pattern[str]] = [
    re.compile(r"here\s+is\s+the\s+entire", re.IGNORECASE),
    re.compile(r"the\s+complete\s+history", re.IGNORECASE),
    re.compile(r"all\s+previous\s+messages", re.IGNORECASE),
    re.compile(r"full\s+conversation\s+log", re.IGNORECASE),
]

# Patterns for format inefficiency detection
FORMAT_INEFFICIENCY_PATTERNS: List[Pattern[str]] = [
    re.compile(r"```[\s\S]{5000,}```"),
    re.compile(r"\n{4,}"),
    re.compile(r"#{5,}\s"),
]

# Patterns for template variable extraction
TEMPLATE_VAR_PATTERNS: List[Pattern[str]] = [
    re.compile(r"\{(\w+)\}"),
    re.compile(r"\{\{(\w+)\}\}"),
    re.compile(r"\$\{(\w+)\}"),
    re.compile(r"\$(\w+)"),
]

# Patterns for retry count extraction
RETRY_COUNT_PATTERNS: List[Pattern[str]] = [
    re.compile(r"max_retries\s*=\s*(\d+)"),
    re.compile(r"retries\s*=\s*(\d+)"),
    re.compile(r"tries\s*=\s*(\d+)"),
    re.compile(r"range\((\d+)\)"),
]

# Patterns for retry logic detection
RETRY_LOGIC_PATTERNS: List[Pattern[str]] = [
    re.compile(r"@retry\(", re.IGNORECASE),
    re.compile(r"tenacity\.retry", re.IGNORECASE),
    re.compile(r"for\s+\w+\s+in\s+range\([^)]+\):.*(?:try|except)", re.IGNORECASE),
    re.compile(r"while\s+.*retry", re.IGNORECASE),
    re.compile(r"max_retries\s*=", re.IGNORECASE),
    re.compile(r"backoff\.", re.IGNORECASE),
]


# =============================================================================
# Enums
# =============================================================================


class OptimizationCategory(Enum):
    """Categories of LLM optimization opportunities."""

    PROMPT_ENGINEERING = "prompt_engineering"
    CACHING = "caching"
    BATCHING = "batching"
    TOKEN_OPTIMIZATION = "token_optimization"
    MODEL_SELECTION = "model_selection"
    RETRY_STRATEGY = "retry_strategy"
    PARALLEL_PROCESSING = "parallel_processing"
    FALLBACK_STRATEGY = "fallback_strategy"


class OptimizationPriority(Enum):
    """Priority levels for optimization recommendations."""

    CRITICAL = "critical"  # Immediate action needed
    HIGH = "high"  # Significant cost savings
    MEDIUM = "medium"  # Moderate improvements
    LOW = "low"  # Minor enhancements
    INFO = "info"  # Informational only


# Performance optimization: O(1) lookup for priority levels (Issue #326)
HIGH_PRIORITY_LEVELS: FrozenSet[OptimizationPriority] = frozenset(
    {OptimizationPriority.HIGH, OptimizationPriority.CRITICAL}
)


class CacheOpportunityType(Enum):
    """Types of caching opportunities."""

    STATIC_PROMPT = "static_prompt"
    TEMPLATE_RESULT = "template_result"
    EMBEDDING_CACHE = "embedding_cache"
    RESPONSE_CACHE = "response_cache"
    SEMANTIC_CACHE = "semantic_cache"


class UsagePatternType(Enum):
    """Types of LLM usage patterns detected."""

    CHAT_COMPLETION = "chat_completion"
    TEXT_GENERATION = "text_generation"
    EMBEDDING = "embedding"
    CODE_GENERATION = "code_generation"
    ANALYSIS = "analysis"
    STREAMING = "streaming"
    BATCH_PROCESSING = "batch_processing"


class PromptIssueType(Enum):
    """Types of prompt issues detected."""

    REDUNDANT_INSTRUCTIONS = "redundant_instructions"
    EXCESSIVE_CONTEXT = "excessive_context"
    MISSING_CONSTRAINTS = "missing_constraints"
    INEFFICIENT_FORMAT = "inefficient_format"
    REPETITIVE_CONTENT = "repetitive_content"
    UNCLEAR_INTENT = "unclear_intent"

    def get_suggestion(self) -> str:
        """
        Get improvement suggestion for this issue type.

        Fixes Feature Envy: Move suggestion logic to where data lives (Issue #312)
        """
        suggestions = {
            PromptIssueType.REDUNDANT_INSTRUCTIONS: (
                "Remove redundant instructions and consolidate repeated phrases"
            ),
            PromptIssueType.EXCESSIVE_CONTEXT: (
                "Consider summarizing or limiting context to relevant portions"
            ),
            PromptIssueType.INEFFICIENT_FORMAT: (
                "Optimize formatting: reduce whitespace and simplify"
            ),
            PromptIssueType.REPETITIVE_CONTENT: (
                "Remove repeated content and consolidate similar ideas"
            ),
            PromptIssueType.MISSING_CONSTRAINTS: (
                "Add explicit constraints and requirements"
            ),
            PromptIssueType.UNCLEAR_INTENT: (
                "Clarify the intended goal and expected output"
            ),
        }
        return suggestions.get(self, "Review and optimize this section")
