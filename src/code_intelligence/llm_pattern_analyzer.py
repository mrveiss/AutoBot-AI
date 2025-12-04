# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Integration Pattern Analyzer - Cost Optimization Engine

This module provides comprehensive analysis of LLM usage patterns in AutoBot
to optimize performance and reduce costs through:
- Prompt template analysis and optimization suggestions
- Token usage tracking and efficiency metrics
- Caching opportunity detection
- Batch processing pattern identification
- Cost estimation and savings calculation
- Retry pattern analysis
- Parallel call optimization

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #229)
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class TokenUsage:
    """Token usage statistics for an LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class PromptTemplate:
    """Information about a detected prompt template."""

    template_id: str
    template_text: str
    variable_count: int
    usage_count: int = 0
    avg_token_count: int = 0
    file_path: Optional[str] = None
    line_number: int = 0
    issues: List[PromptIssueType] = field(default_factory=list)


@dataclass
class CacheOpportunity:
    """A detected caching opportunity."""

    opportunity_id: str
    cache_type: CacheOpportunityType
    description: str
    estimated_hit_rate: float
    estimated_savings_percent: float
    affected_calls_per_hour: int = 0
    implementation_effort: str = "medium"
    priority: OptimizationPriority = OptimizationPriority.MEDIUM


@dataclass
class UsagePattern:
    """A detected LLM usage pattern."""

    pattern_id: str
    pattern_type: UsagePatternType
    file_path: str
    line_number: int
    code_snippet: str
    model_used: Optional[str] = None
    frequency: str = "unknown"
    token_estimate: int = 0
    optimization_potential: float = 0.0


@dataclass
class RetryPattern:
    """Information about retry patterns in LLM calls."""

    pattern_id: str
    file_path: str
    line_number: int
    max_retries: int
    backoff_strategy: str  # exponential, linear, fixed, none
    retry_conditions: List[str] = field(default_factory=list)
    has_timeout: bool = False
    timeout_value: Optional[float] = None
    issues: List[str] = field(default_factory=list)


@dataclass
class BatchingOpportunity:
    """A detected batching opportunity."""

    opportunity_id: str
    file_path: str
    related_calls: List[Tuple[int, str]]  # (line_number, call_description)
    estimated_speedup: float
    estimated_token_savings: int
    priority: OptimizationPriority = OptimizationPriority.MEDIUM


@dataclass
class CostEstimate:
    """Cost estimation for LLM usage."""

    model: str
    daily_calls: int
    avg_prompt_tokens: int
    avg_completion_tokens: int
    cost_per_1k_prompt: float
    cost_per_1k_completion: float
    daily_cost_usd: float
    monthly_cost_usd: float
    optimization_potential_percent: float = 0.0
    optimized_monthly_cost_usd: float = 0.0


@dataclass
class OptimizationRecommendation:
    """A specific optimization recommendation."""

    recommendation_id: str
    category: OptimizationCategory
    priority: OptimizationPriority
    title: str
    description: str
    impact: str
    implementation_steps: List[str]
    estimated_savings_percent: float
    effort: str  # low, medium, high
    affected_files: List[str] = field(default_factory=list)
    code_examples: Dict[str, str] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Complete result of LLM pattern analysis."""

    analysis_id: str
    analysis_timestamp: datetime
    files_analyzed: int
    patterns_found: List[UsagePattern]
    prompt_templates: List[PromptTemplate]
    cache_opportunities: List[CacheOpportunity]
    batching_opportunities: List[BatchingOpportunity]
    retry_patterns: List[RetryPattern]
    cost_estimates: List[CostEstimate]
    recommendations: List[OptimizationRecommendation]
    total_estimated_savings_percent: float = 0.0
    summary: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Token Tracker
# =============================================================================


class TokenTracker:
    """
    Tracks token usage across LLM calls for cost analysis.

    Provides real-time tracking and historical analysis of token consumption
    to identify optimization opportunities.
    """

    # Token cost estimates per 1K tokens (based on common pricing)
    DEFAULT_COSTS = {
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002},
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        "ollama": {"prompt": 0.0, "completion": 0.0},  # Local, no API cost
        "default": {"prompt": 0.001, "completion": 0.002},
    }

    def __init__(self):
        """Initialize the token tracker."""
        self.usage_history: List[TokenUsage] = []
        self.model_usage: Dict[str, TokenUsage] = {}
        self.hourly_usage: Dict[str, int] = {}
        self.total_cost: float = 0.0

    def track_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> TokenUsage:
        """
        Track token usage for an LLM call.

        Args:
            model: The model used for the call
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion

        Returns:
            TokenUsage record with cost estimation
        """
        total_tokens = prompt_tokens + completion_tokens
        cost = self._calculate_cost(model, prompt_tokens, completion_tokens)

        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
        )

        self.usage_history.append(usage)
        self.total_cost += cost

        # Update model-specific tracking
        if model not in self.model_usage:
            self.model_usage[model] = TokenUsage()
        self.model_usage[model].prompt_tokens += prompt_tokens
        self.model_usage[model].completion_tokens += completion_tokens
        self.model_usage[model].total_tokens += total_tokens
        self.model_usage[model].estimated_cost_usd += cost

        # Update hourly tracking
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
        self.hourly_usage[hour_key] = self.hourly_usage.get(hour_key, 0) + total_tokens

        return usage

    def _calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calculate cost for token usage."""
        model_lower = model.lower()
        costs = self.DEFAULT_COSTS.get("default")

        for model_key, model_costs in self.DEFAULT_COSTS.items():
            if model_key in model_lower:
                costs = model_costs
                break

        prompt_cost = (prompt_tokens / 1000) * costs["prompt"]
        completion_cost = (completion_tokens / 1000) * costs["completion"]

        return prompt_cost + completion_cost

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get a summary of token usage."""
        if not self.usage_history:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_tokens_per_call": 0,
            }

        total_tokens = sum(u.total_tokens for u in self.usage_history)
        return {
            "total_calls": len(self.usage_history),
            "total_tokens": total_tokens,
            "total_cost_usd": self.total_cost,
            "avg_tokens_per_call": total_tokens // len(self.usage_history),
            "model_breakdown": {
                model: {
                    "tokens": usage.total_tokens,
                    "cost_usd": usage.estimated_cost_usd,
                }
                for model, usage in self.model_usage.items()
            },
        }


# =============================================================================
# Prompt Analyzer
# =============================================================================


class PromptAnalyzer:
    """
    Analyzes prompt templates for optimization opportunities.

    Detects issues like redundant instructions, excessive context,
    and suggests improvements for token efficiency.
    """

    # Patterns that indicate potential issues
    REDUNDANT_PATTERNS = [
        r"please\s+please",
        r"make\s+sure\s+to\s+make\s+sure",
        r"you\s+must\s+always\s+you\s+must",
        r"important:\s*important",
    ]

    EXCESSIVE_CONTEXT_MARKERS = [
        r"here\s+is\s+the\s+entire",
        r"the\s+complete\s+history",
        r"all\s+previous\s+messages",
        r"full\s+conversation\s+log",
    ]

    FORMAT_INEFFICIENCIES = [
        (r"```[\s\S]{5000,}```", "Large code blocks could be summarized"),
        (r"\n{4,}", "Excessive whitespace"),
        (r"#{5,}\s", "Too many header levels"),
    ]

    @classmethod
    def analyze_prompt(cls, prompt: str) -> List[PromptIssueType]:
        """
        Analyze a prompt for potential issues.

        Args:
            prompt: The prompt text to analyze

        Returns:
            List of detected issues
        """
        issues = []

        # Check for redundant patterns
        for pattern in cls.REDUNDANT_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                issues.append(PromptIssueType.REDUNDANT_INSTRUCTIONS)
                break

        # Check for excessive context
        for pattern in cls.EXCESSIVE_CONTEXT_MARKERS:
            if re.search(pattern, prompt, re.IGNORECASE):
                issues.append(PromptIssueType.EXCESSIVE_CONTEXT)
                break

        # Check for format inefficiencies
        for pattern, _ in cls.FORMAT_INEFFICIENCIES:
            if re.search(pattern, prompt):
                issues.append(PromptIssueType.INEFFICIENT_FORMAT)
                break

        # Check for repetitive content
        words = prompt.lower().split()
        if len(words) > 50:
            word_freq = {}
            for word in words:
                if len(word) > 4:
                    word_freq[word] = word_freq.get(word, 0) + 1
            # If any word appears more than 10% of time, consider repetitive
            for word, count in word_freq.items():
                if count > len(words) * 0.1 and count > 5:
                    issues.append(PromptIssueType.REPETITIVE_CONTENT)
                    break

        return issues

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """
        Estimate token count for text.

        Uses a simple heuristic: ~4 characters per token for English text.
        More accurate counting would require the actual tokenizer.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4 + 1

    @classmethod
    def extract_variables(cls, template: str) -> List[str]:
        """
        Extract variable placeholders from a prompt template.

        Args:
            template: The template text

        Returns:
            List of variable names found
        """
        # Match {variable}, {{variable}}, ${variable}, etc.
        patterns = [
            r"\{(\w+)\}",
            r"\{\{(\w+)\}\}",
            r"\$\{(\w+)\}",
            r"\$(\w+)",
        ]

        variables = set()
        for pattern in patterns:
            matches = re.findall(pattern, template)
            variables.update(matches)

        return list(variables)

    @classmethod
    def suggest_improvements(
        cls, prompt: str, issues: List[PromptIssueType]
    ) -> List[str]:
        """
        Suggest improvements for detected issues.

        Args:
            prompt: The original prompt
            issues: List of detected issues

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        if PromptIssueType.REDUNDANT_INSTRUCTIONS in issues:
            suggestions.append(
                "Remove redundant instructions and consolidate repeated phrases"
            )

        if PromptIssueType.EXCESSIVE_CONTEXT in issues:
            suggestions.append(
                "Consider summarizing or limiting context to relevant portions"
            )

        if PromptIssueType.INEFFICIENT_FORMAT in issues:
            suggestions.append("Optimize formatting: reduce whitespace and simplify")

        if PromptIssueType.REPETITIVE_CONTENT in issues:
            suggestions.append("Remove repeated content and consolidate similar ideas")

        # General suggestions based on length
        estimated_tokens = cls.estimate_tokens(prompt)
        if estimated_tokens > 2000:
            suggestions.append(
                f"Consider reducing prompt length (~{estimated_tokens} tokens)"
            )

        return suggestions


# =============================================================================
# Cache Opportunity Detector
# =============================================================================


class CacheOpportunityDetector:
    """
    Detects opportunities for caching LLM responses.

    Analyzes code patterns to identify where caching could reduce
    redundant API calls and save costs.
    """

    @classmethod
    def detect_opportunities(
        cls,
        patterns: List[UsagePattern],
    ) -> List[CacheOpportunity]:
        """
        Detect caching opportunities from usage patterns.

        Args:
            patterns: List of detected usage patterns

        Returns:
            List of caching opportunities
        """
        opportunities = []

        # Group patterns by type and analyze
        patterns_by_type: Dict[UsagePatternType, List[UsagePattern]] = {}
        for pattern in patterns:
            if pattern.pattern_type not in patterns_by_type:
                patterns_by_type[pattern.pattern_type] = []
            patterns_by_type[pattern.pattern_type].append(pattern)

        # Embedding caching opportunity
        embeddings = patterns_by_type.get(UsagePatternType.EMBEDDING, [])
        if embeddings:
            opportunity = CacheOpportunity(
                opportunity_id=cls._generate_id("embed"),
                cache_type=CacheOpportunityType.EMBEDDING_CACHE,
                description="Cache embedding results for repeated text",
                estimated_hit_rate=0.60,
                estimated_savings_percent=40.0,
                affected_calls_per_hour=len(embeddings) * 10,
                implementation_effort="low",
                priority=OptimizationPriority.HIGH,
            )
            opportunities.append(opportunity)

        # Static prompt caching
        static_prompts = [
            p
            for p in patterns
            if p.optimization_potential > 0.5
            and p.pattern_type == UsagePatternType.CHAT_COMPLETION
        ]
        if static_prompts:
            opportunity = CacheOpportunity(
                opportunity_id=cls._generate_id("static"),
                cache_type=CacheOpportunityType.STATIC_PROMPT,
                description="Cache responses for frequently-used static prompts",
                estimated_hit_rate=0.30,
                estimated_savings_percent=25.0,
                affected_calls_per_hour=len(static_prompts) * 5,
                implementation_effort="medium",
                priority=OptimizationPriority.MEDIUM,
            )
            opportunities.append(opportunity)

        # Response caching for analysis tasks
        analysis = patterns_by_type.get(UsagePatternType.ANALYSIS, [])
        if analysis:
            opportunity = CacheOpportunity(
                opportunity_id=cls._generate_id("analysis"),
                cache_type=CacheOpportunityType.RESPONSE_CACHE,
                description="Cache analysis results with content-based keys",
                estimated_hit_rate=0.45,
                estimated_savings_percent=35.0,
                affected_calls_per_hour=len(analysis) * 8,
                implementation_effort="medium",
                priority=OptimizationPriority.HIGH,
            )
            opportunities.append(opportunity)

        return opportunities

    @classmethod
    def _generate_id(cls, prefix: str) -> str:
        """Generate a unique opportunity ID."""
        timestamp = str(time.time()).replace(".", "")[:10]
        return f"cache_{prefix}_{timestamp}"


# =============================================================================
# Code Pattern Scanner
# =============================================================================


class CodePatternScanner:
    """
    Scans Python code for LLM usage patterns.

    Uses AST analysis and regex patterns to detect LLM API calls,
    prompt templates, and usage patterns in the codebase.
    """

    # Patterns to detect LLM API calls
    LLM_CALL_PATTERNS = [
        (r"\.chat\.completions\.create", UsagePatternType.CHAT_COMPLETION),
        (r"\.completions\.create", UsagePatternType.TEXT_GENERATION),
        (r"\.embeddings\.create", UsagePatternType.EMBEDDING),
        (r"ollama\.generate", UsagePatternType.TEXT_GENERATION),
        (r"ollama\.chat", UsagePatternType.CHAT_COMPLETION),
        (r"anthropic\.\w+\.messages", UsagePatternType.CHAT_COMPLETION),
        (r"stream=True", UsagePatternType.STREAMING),
    ]

    # Patterns to detect retry logic
    RETRY_PATTERNS = [
        r"@retry\(",
        r"tenacity\.retry",
        r"for\s+\w+\s+in\s+range\([^)]+\):.*(?:try|except)",
        r"while\s+.*retry",
        r"max_retries\s*=",
        r"backoff\.",
    ]

    @classmethod
    def scan_file(cls, file_path: Path) -> Tuple[List[UsagePattern], List[RetryPattern]]:
        """
        Scan a Python file for LLM patterns.

        Args:
            file_path: Path to the Python file

        Returns:
            Tuple of (usage_patterns, retry_patterns)
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return [], []

        usage_patterns = []
        retry_patterns = []

        # Scan for LLM calls using regex
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for pattern, pattern_type in cls.LLM_CALL_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    usage_pattern = UsagePattern(
                        pattern_id=cls._generate_pattern_id(file_path, line_num),
                        pattern_type=pattern_type,
                        file_path=str(file_path),
                        line_number=line_num,
                        code_snippet=line.strip()[:200],
                        optimization_potential=cls._estimate_optimization(line),
                    )
                    usage_patterns.append(usage_pattern)

        # Scan for retry patterns
        for line_num, line in enumerate(lines, 1):
            for pattern in cls.RETRY_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    retry_pattern = RetryPattern(
                        pattern_id=cls._generate_pattern_id(file_path, line_num, "retry"),
                        file_path=str(file_path),
                        line_number=line_num,
                        max_retries=cls._extract_retry_count(content, line_num),
                        backoff_strategy=cls._detect_backoff_strategy(content, line_num),
                    )
                    retry_patterns.append(retry_pattern)
                    break  # Only one retry pattern per line

        return usage_patterns, retry_patterns

    @classmethod
    def _generate_pattern_id(
        cls,
        file_path: Path,
        line_num: int,
        prefix: str = "usage",
    ) -> str:
        """Generate a unique pattern ID."""
        content = f"{file_path}:{line_num}"
        hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"{prefix}_{hash_val}"

    @classmethod
    def _estimate_optimization(cls, line: str) -> float:
        """Estimate optimization potential for a line of code."""
        potential = 0.3  # Base potential

        # Higher potential if no streaming
        if "stream" not in line.lower():
            potential += 0.2

        # Higher potential if it looks like a simple call
        if "temperature" in line.lower() and "0" in line:
            potential += 0.2

        # Higher potential if there's a hardcoded model
        if any(model in line.lower() for model in ["gpt-3.5", "haiku", "llama"]):
            potential += 0.1

        return min(potential, 1.0)

    @classmethod
    def _extract_retry_count(cls, content: str, line_num: int) -> int:
        """Extract retry count from nearby code."""
        lines = content.split("\n")
        start = max(0, line_num - 5)
        end = min(len(lines), line_num + 5)
        context = "\n".join(lines[start:end])

        # Look for retry count patterns
        patterns = [
            r"max_retries\s*=\s*(\d+)",
            r"retries\s*=\s*(\d+)",
            r"tries\s*=\s*(\d+)",
            r"range\((\d+)\)",
        ]

        for pattern in patterns:
            match = re.search(pattern, context)
            if match:
                return int(match.group(1))

        return 3  # Default assumption

    @classmethod
    def _detect_backoff_strategy(cls, content: str, line_num: int) -> str:
        """Detect backoff strategy from nearby code."""
        lines = content.split("\n")
        start = max(0, line_num - 10)
        end = min(len(lines), line_num + 10)
        context = "\n".join(lines[start:end]).lower()

        if "exponential" in context or "expo" in context:
            return "exponential"
        if "linear" in context:
            return "linear"
        if "fixed" in context or "constant" in context:
            return "fixed"

        return "unknown"


# =============================================================================
# Batching Opportunity Analyzer
# =============================================================================


class BatchingAnalyzer:
    """
    Analyzes code for batching opportunities.

    Identifies sequences of similar LLM calls that could be batched
    together for improved efficiency.
    """

    @staticmethod
    def _group_patterns_by_file(
        patterns: List[UsagePattern],
    ) -> Dict[str, List[UsagePattern]]:
        """Group patterns by file path (Issue #335 - extracted helper)."""
        file_patterns: Dict[str, List[UsagePattern]] = {}
        for pattern in patterns:
            if pattern.file_path not in file_patterns:
                file_patterns[pattern.file_path] = []
            file_patterns[pattern.file_path].append(pattern)
        return file_patterns

    @staticmethod
    def _group_by_pattern_type(
        patterns: List[UsagePattern],
    ) -> Dict[UsagePatternType, List[UsagePattern]]:
        """Group patterns by type (Issue #335 - extracted helper)."""
        type_groups: Dict[UsagePatternType, List[UsagePattern]] = {}
        for pat in patterns:
            if pat.pattern_type not in type_groups:
                type_groups[pat.pattern_type] = []
            type_groups[pat.pattern_type].append(pat)
        return type_groups

    @staticmethod
    def _find_close_pair_opportunity(
        file_path: str, sorted_pats: List[UsagePattern]
    ) -> Optional[BatchingOpportunity]:
        """Find batching opportunity from close patterns (Issue #335 - extracted helper)."""
        for i in range(len(sorted_pats) - 1):
            line_diff = sorted_pats[i + 1].line_number - sorted_pats[i].line_number
            if line_diff >= 50:
                continue
            return BatchingOpportunity(
                opportunity_id=f"batch_{hash(file_path)%10000:04d}",
                file_path=file_path,
                related_calls=[
                    (p.line_number, p.code_snippet[:50])
                    for p in sorted_pats[i : i + 2]
                ],
                estimated_speedup=1.5,
                estimated_token_savings=100,
                priority=OptimizationPriority.MEDIUM,
            )
        return None

    @classmethod
    def find_opportunities(
        cls,
        patterns: List[UsagePattern],
    ) -> List[BatchingOpportunity]:
        """
        Find batching opportunities from usage patterns.

        Args:
            patterns: List of detected usage patterns

        Returns:
            List of batching opportunities
        """
        opportunities = []
        file_patterns = cls._group_patterns_by_file(patterns)

        for file_path, file_pats in file_patterns.items():
            if len(file_pats) < 2:
                continue

            type_groups = cls._group_by_pattern_type(file_pats)

            for pat_type, group_patterns in type_groups.items():
                if len(group_patterns) < 2:
                    continue

                sorted_pats = sorted(group_patterns, key=lambda p: p.line_number)
                opportunity = cls._find_close_pair_opportunity(file_path, sorted_pats)
                if opportunity:
                    opportunities.append(opportunity)

        return opportunities


# =============================================================================
# Cost Calculator
# =============================================================================


class CostCalculator:
    """
    Calculates and estimates LLM usage costs.

    Provides cost projections and optimization potential analysis.
    """

    # Model pricing per 1K tokens (USD)
    MODEL_PRICING = {
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "gpt-4o": {"prompt": 0.005, "completion": 0.015},
        "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002},
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        "claude-sonnet-4": {"prompt": 0.003, "completion": 0.015},
        "ollama": {"prompt": 0.0, "completion": 0.0},
    }

    @classmethod
    def estimate_costs(
        cls,
        patterns: List[UsagePattern],
        daily_call_multiplier: int = 100,
    ) -> List[CostEstimate]:
        """
        Estimate costs based on detected patterns.

        Args:
            patterns: List of usage patterns
            daily_call_multiplier: Estimated daily calls per pattern

        Returns:
            List of cost estimates by model
        """
        estimates = []

        # Group by detected model or use default
        model_patterns: Dict[str, List[UsagePattern]] = {}
        for pattern in patterns:
            model = pattern.model_used or "unknown"
            if model not in model_patterns:
                model_patterns[model] = []
            model_patterns[model].append(pattern)

        for model, model_pats in model_patterns.items():
            # Get pricing
            pricing = cls.MODEL_PRICING.get(
                model,
                cls.MODEL_PRICING.get("gpt-3.5-turbo"),  # Default
            )

            # Estimate daily calls
            daily_calls = len(model_pats) * daily_call_multiplier

            # Estimate average tokens (based on pattern type)
            avg_prompt = 500
            avg_completion = 300

            for pat in model_pats:
                if pat.pattern_type == UsagePatternType.EMBEDDING:
                    avg_prompt = 200
                    avg_completion = 0
                elif pat.pattern_type == UsagePatternType.CODE_GENERATION:
                    avg_prompt = 800
                    avg_completion = 600

            # Calculate costs
            daily_prompt_cost = (daily_calls * avg_prompt / 1000) * pricing["prompt"]
            daily_completion_cost = (
                daily_calls * avg_completion / 1000
            ) * pricing["completion"]
            daily_cost = daily_prompt_cost + daily_completion_cost

            estimate = CostEstimate(
                model=model,
                daily_calls=daily_calls,
                avg_prompt_tokens=avg_prompt,
                avg_completion_tokens=avg_completion,
                cost_per_1k_prompt=pricing["prompt"],
                cost_per_1k_completion=pricing["completion"],
                daily_cost_usd=daily_cost,
                monthly_cost_usd=daily_cost * 30,
                optimization_potential_percent=25.0,  # Conservative estimate
                optimized_monthly_cost_usd=daily_cost * 30 * 0.75,
            )
            estimates.append(estimate)

        return estimates


# =============================================================================
# Recommendation Engine
# =============================================================================


class RecommendationEngine:
    """
    Generates optimization recommendations based on analysis results.

    Combines insights from all analyzers to produce actionable recommendations.
    """

    @classmethod
    def generate_recommendations(
        cls,
        patterns: List[UsagePattern],
        cache_opportunities: List[CacheOpportunity],
        batching_opportunities: List[BatchingOpportunity],
        retry_patterns: List[RetryPattern],
        cost_estimates: List[CostEstimate],
    ) -> List[OptimizationRecommendation]:
        """
        Generate optimization recommendations.

        Args:
            patterns: Usage patterns found
            cache_opportunities: Caching opportunities
            batching_opportunities: Batching opportunities
            retry_patterns: Retry patterns
            cost_estimates: Cost estimates

        Returns:
            List of optimization recommendations
        """
        recommendations = []

        # Caching recommendations
        for cache_opp in cache_opportunities:
            if cache_opp.priority in [OptimizationPriority.HIGH, OptimizationPriority.CRITICAL]:
                rec = OptimizationRecommendation(
                    recommendation_id=f"rec_{cache_opp.opportunity_id}",
                    category=OptimizationCategory.CACHING,
                    priority=cache_opp.priority,
                    title=f"Implement {cache_opp.cache_type.value} caching",
                    description=cache_opp.description,
                    impact=f"~{cache_opp.estimated_savings_percent:.0f}% cost reduction",
                    implementation_steps=[
                        "Add Redis/in-memory cache layer",
                        "Generate cache keys from prompt content hash",
                        "Set appropriate TTL based on content freshness needs",
                        "Add cache hit/miss metrics",
                    ],
                    estimated_savings_percent=cache_opp.estimated_savings_percent,
                    effort=cache_opp.implementation_effort,
                )
                recommendations.append(rec)

        # Batching recommendations
        if batching_opportunities:
            files = list(set(b.file_path for b in batching_opportunities))
            rec = OptimizationRecommendation(
                recommendation_id="rec_batching_001",
                category=OptimizationCategory.BATCHING,
                priority=OptimizationPriority.MEDIUM,
                title="Batch similar LLM calls",
                description=f"Found {len(batching_opportunities)} opportunities to batch LLM calls",
                impact="~1.5x throughput improvement, reduced latency",
                implementation_steps=[
                    "Collect similar requests into batches",
                    "Use async parallel processing",
                    "Implement request deduplication",
                    "Add batch size limits",
                ],
                estimated_savings_percent=20.0,
                effort="medium",
                affected_files=files[:5],
            )
            recommendations.append(rec)

        # Retry strategy recommendations
        suboptimal_retries = [
            r for r in retry_patterns
            if r.backoff_strategy == "unknown" or r.max_retries > 5
        ]
        if suboptimal_retries:
            rec = OptimizationRecommendation(
                recommendation_id="rec_retry_001",
                category=OptimizationCategory.RETRY_STRATEGY,
                priority=OptimizationPriority.HIGH,
                title="Optimize retry strategies",
                description=f"Found {len(suboptimal_retries)} suboptimal retry patterns",
                impact="Reduced latency, better error handling",
                implementation_steps=[
                    "Implement exponential backoff with jitter",
                    "Limit max retries to 3",
                    "Add circuit breaker pattern",
                    "Log retry attempts for analysis",
                ],
                estimated_savings_percent=10.0,
                effort="low",
                affected_files=list(set(r.file_path for r in suboptimal_retries))[:5],
            )
            recommendations.append(rec)

        # Token optimization recommendations
        high_token_patterns = [p for p in patterns if p.token_estimate > 1000]
        if high_token_patterns:
            rec = OptimizationRecommendation(
                recommendation_id="rec_tokens_001",
                category=OptimizationCategory.TOKEN_OPTIMIZATION,
                priority=OptimizationPriority.MEDIUM,
                title="Reduce token usage in prompts",
                description=f"Found {len(high_token_patterns)} high-token patterns",
                impact="15-30% cost reduction per call",
                implementation_steps=[
                    "Review and compress system prompts",
                    "Remove redundant instructions",
                    "Use structured output formats",
                    "Implement context window management",
                ],
                estimated_savings_percent=25.0,
                effort="medium",
            )
            recommendations.append(rec)

        # Model selection recommendations
        expensive_models = [
            e for e in cost_estimates
            if "gpt-4" in e.model.lower() or "opus" in e.model.lower()
        ]
        if expensive_models and len(patterns) > 5:
            rec = OptimizationRecommendation(
                recommendation_id="rec_model_001",
                category=OptimizationCategory.MODEL_SELECTION,
                priority=OptimizationPriority.HIGH,
                title="Use appropriate models for task complexity",
                description="Consider cheaper models for simple tasks",
                impact="50-80% cost reduction for eligible tasks",
                implementation_steps=[
                    "Classify tasks by complexity",
                    "Route simple tasks to smaller models",
                    "Implement model fallback chain",
                    "A/B test quality vs cost tradeoffs",
                ],
                estimated_savings_percent=40.0,
                effort="high",
            )
            recommendations.append(rec)

        # Sort by priority
        priority_order = {
            OptimizationPriority.CRITICAL: 0,
            OptimizationPriority.HIGH: 1,
            OptimizationPriority.MEDIUM: 2,
            OptimizationPriority.LOW: 3,
            OptimizationPriority.INFO: 4,
        }
        recommendations.sort(key=lambda r: priority_order[r.priority])

        return recommendations


# =============================================================================
# Main Analyzer Class
# =============================================================================


class LLMPatternAnalyzer:
    """
    Main LLM Pattern Analyzer for cost optimization.

    Coordinates all analysis components to provide comprehensive
    insights into LLM usage patterns and optimization opportunities.
    """

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize the analyzer.

        Args:
            project_root: Root directory of the project to analyze
        """
        self.project_root = project_root or Path.cwd()
        self.token_tracker = TokenTracker()
        self.analysis_history: List[AnalysisResult] = []

    def analyze(
        self,
        directories: Optional[List[Path]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> AnalysisResult:
        """
        Analyze the codebase for LLM patterns.

        Args:
            directories: Specific directories to analyze (default: src/)
            exclude_patterns: Glob patterns to exclude

        Returns:
            Complete analysis result
        """
        start_time = time.time()
        analysis_id = f"analysis_{int(start_time)}"

        # Default directories
        if directories is None:
            directories = [self.project_root / "src"]

        # Default exclusions
        if exclude_patterns is None:
            exclude_patterns = ["**/test*", "**/__pycache__", "**/venv"]

        # Collect all Python files
        python_files = self._collect_files(directories, exclude_patterns)

        # Scan all files
        all_patterns: List[UsagePattern] = []
        all_retry_patterns: List[RetryPattern] = []
        prompt_templates: List[PromptTemplate] = []

        for file_path in python_files:
            patterns, retries = CodePatternScanner.scan_file(file_path)
            all_patterns.extend(patterns)
            all_retry_patterns.extend(retries)

        # Detect opportunities
        cache_opportunities = CacheOpportunityDetector.detect_opportunities(all_patterns)
        batching_opportunities = BatchingAnalyzer.find_opportunities(all_patterns)

        # Calculate costs
        cost_estimates = CostCalculator.estimate_costs(all_patterns)

        # Generate recommendations
        recommendations = RecommendationEngine.generate_recommendations(
            patterns=all_patterns,
            cache_opportunities=cache_opportunities,
            batching_opportunities=batching_opportunities,
            retry_patterns=all_retry_patterns,
            cost_estimates=cost_estimates,
        )

        # Calculate total savings potential
        total_savings = sum(r.estimated_savings_percent for r in recommendations) / max(
            len(recommendations), 1
        )

        # Build result
        result = AnalysisResult(
            analysis_id=analysis_id,
            analysis_timestamp=datetime.now(),
            files_analyzed=len(python_files),
            patterns_found=all_patterns,
            prompt_templates=prompt_templates,
            cache_opportunities=cache_opportunities,
            batching_opportunities=batching_opportunities,
            retry_patterns=all_retry_patterns,
            cost_estimates=cost_estimates,
            recommendations=recommendations,
            total_estimated_savings_percent=total_savings,
            summary={
                "analysis_time_seconds": time.time() - start_time,
                "total_patterns": len(all_patterns),
                "total_opportunities": len(cache_opportunities) + len(batching_opportunities),
                "total_recommendations": len(recommendations),
                "estimated_monthly_cost": sum(c.monthly_cost_usd for c in cost_estimates),
                "estimated_optimized_cost": sum(
                    c.optimized_monthly_cost_usd for c in cost_estimates
                ),
            },
        )

        self.analysis_history.append(result)
        logger.info(
            f"Analysis complete: {len(all_patterns)} patterns, "
            f"{len(recommendations)} recommendations"
        )

        return result

    def _collect_files(
        self,
        directories: List[Path],
        exclude_patterns: List[str],
    ) -> List[Path]:
        """Collect Python files from directories."""
        files = []

        for directory in directories:
            if not directory.exists():
                continue

            for file_path in directory.rglob("*.py"):
                # Check exclusions
                excluded = False
                for pattern in exclude_patterns:
                    if file_path.match(pattern):
                        excluded = True
                        break

                if not excluded:
                    files.append(file_path)

        return files

    def get_summary_report(self, result: AnalysisResult) -> str:
        """
        Generate a human-readable summary report.

        Args:
            result: Analysis result to summarize

        Returns:
            Formatted summary string
        """
        lines = [
            "=" * 60,
            "LLM PATTERN ANALYSIS REPORT",
            "=" * 60,
            "",
            f"Analysis ID: {result.analysis_id}",
            f"Timestamp: {result.analysis_timestamp.isoformat()}",
            f"Files Analyzed: {result.files_analyzed}",
            "",
            "FINDINGS SUMMARY",
            "-" * 40,
            f"  Usage Patterns Found: {len(result.patterns_found)}",
            f"  Cache Opportunities: {len(result.cache_opportunities)}",
            f"  Batching Opportunities: {len(result.batching_opportunities)}",
            f"  Retry Patterns: {len(result.retry_patterns)}",
            "",
            "COST ANALYSIS",
            "-" * 40,
        ]

        for estimate in result.cost_estimates:
            lines.append(f"  Model: {estimate.model}")
            lines.append(f"    Daily Calls: {estimate.daily_calls}")
            lines.append(f"    Monthly Cost: ${estimate.monthly_cost_usd:.2f}")
            lines.append(f"    Optimized Cost: ${estimate.optimized_monthly_cost_usd:.2f}")
            lines.append("")

        lines.extend([
            "TOP RECOMMENDATIONS",
            "-" * 40,
        ])

        for rec in result.recommendations[:5]:
            lines.append(f"  [{rec.priority.value.upper()}] {rec.title}")
            lines.append(f"    Impact: {rec.impact}")
            lines.append(f"    Effort: {rec.effort}")
            lines.append("")

        lines.extend([
            "ESTIMATED SAVINGS",
            "-" * 40,
            f"  Total Savings Potential: {result.total_estimated_savings_percent:.1f}%",
            "",
            "=" * 60,
        ])

        return "\n".join(lines)


# =============================================================================
# Convenience Functions
# =============================================================================


def analyze_llm_patterns(
    project_root: Optional[Path] = None,
    directories: Optional[List[Path]] = None,
) -> AnalysisResult:
    """
    Convenience function to analyze LLM patterns.

    Args:
        project_root: Project root directory
        directories: Specific directories to analyze

    Returns:
        Analysis result
    """
    analyzer = LLMPatternAnalyzer(project_root)
    return analyzer.analyze(directories)


def get_optimization_categories() -> List[str]:
    """Get all optimization category values."""
    return [cat.value for cat in OptimizationCategory]


def get_optimization_priorities() -> List[str]:
    """Get all optimization priority values."""
    return [priority.value for priority in OptimizationPriority]


def get_cache_opportunity_types() -> List[str]:
    """Get all cache opportunity type values."""
    return [cache_type.value for cache_type in CacheOpportunityType]


def get_usage_pattern_types() -> List[str]:
    """Get all usage pattern type values."""
    return [pattern_type.value for pattern_type in UsagePatternType]


def get_prompt_issue_types() -> List[str]:
    """Get all prompt issue type values."""
    return [issue_type.value for issue_type in PromptIssueType]


def estimate_prompt_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    return PromptAnalyzer.estimate_tokens(text)


def analyze_prompt(prompt: str) -> Dict[str, Any]:
    """
    Analyze a prompt for issues.

    Args:
        prompt: Prompt text to analyze

    Returns:
        Analysis result with issues and suggestions
    """
    issues = PromptAnalyzer.analyze_prompt(prompt)
    suggestions = PromptAnalyzer.suggest_improvements(prompt, issues)
    tokens = PromptAnalyzer.estimate_tokens(prompt)

    return {
        "issues": [issue.value for issue in issues],
        "suggestions": suggestions,
        "estimated_tokens": tokens,
        "variables": PromptAnalyzer.extract_variables(prompt),
    }
