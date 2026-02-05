# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Pattern Scanners Module

Contains classes for scanning code and detecting patterns:
- CodePatternScanner: Scans Python files for LLM API call patterns
- CacheOpportunityDetector: Detects caching opportunities
- BatchingAnalyzer: Identifies batching opportunities

Extracted from llm_pattern_analyzer.py as part of Issue #381 refactoring.
"""

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.code_intelligence.llm_pattern_analysis.data_models import (
    BatchingOpportunity,
    CacheOpportunity,
    RetryPattern,
    UsagePattern,
)
from src.code_intelligence.llm_pattern_analysis.types import (
    RETRY_COUNT_PATTERNS,
    RETRY_LOGIC_PATTERNS,
    SIMPLE_LLM_MODELS,
    CacheOpportunityType,
    OptimizationPriority,
    UsagePatternType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Code Pattern Scanner
# =============================================================================


class CodePatternScanner:
    """
    Scans Python code for LLM usage patterns.

    Uses AST analysis and regex patterns to detect LLM API calls,
    prompt templates, and usage patterns in the codebase.
    """

    # Issue #380: Pre-compiled patterns to detect LLM API calls
    LLM_CALL_PATTERNS = [
        (
            re.compile(r"\.chat\.completions\.create", re.IGNORECASE),
            UsagePatternType.CHAT_COMPLETION,
        ),
        (
            re.compile(r"\.completions\.create", re.IGNORECASE),
            UsagePatternType.TEXT_GENERATION,
        ),
        (
            re.compile(r"\.embeddings\.create", re.IGNORECASE),
            UsagePatternType.EMBEDDING,
        ),
        (
            re.compile(r"ollama\.generate", re.IGNORECASE),
            UsagePatternType.TEXT_GENERATION,
        ),
        (
            re.compile(r"ollama\.chat", re.IGNORECASE),
            UsagePatternType.CHAT_COMPLETION,
        ),
        (
            re.compile(r"anthropic\.\w+\.messages", re.IGNORECASE),
            UsagePatternType.CHAT_COMPLETION,
        ),
        (
            re.compile(r"stream=True", re.IGNORECASE),
            UsagePatternType.STREAMING,
        ),
    ]

    # Issue #380: Reference pre-compiled patterns for retry logic
    RETRY_PATTERNS = RETRY_LOGIC_PATTERNS

    @classmethod
    def _scan_for_llm_patterns(
        cls, file_path: Path, lines: List[str]
    ) -> List[UsagePattern]:
        """
        Scan lines for LLM API call patterns.

        Args:
            file_path: Path to the source file
            lines: List of source code lines

        Returns:
            List of detected UsagePattern objects

        Issue #620.
        """
        usage_patterns = []
        for line_num, line in enumerate(lines, 1):
            for pattern, pattern_type in cls.LLM_CALL_PATTERNS:
                if pattern.search(line):
                    usage_patterns.append(
                        UsagePattern(
                            pattern_id=cls._generate_pattern_id(file_path, line_num),
                            pattern_type=pattern_type,
                            file_path=str(file_path),
                            line_number=line_num,
                            code_snippet=line.strip()[:200],
                            optimization_potential=cls._estimate_optimization(line),
                        )
                    )
        return usage_patterns

    @classmethod
    def _scan_for_retry_patterns(
        cls, file_path: Path, lines: List[str], content: str
    ) -> List[RetryPattern]:
        """
        Scan lines for retry logic patterns.

        Args:
            file_path: Path to the source file
            lines: List of source code lines
            content: Full file content for context analysis

        Returns:
            List of detected RetryPattern objects

        Issue #620.
        """
        retry_patterns = []
        for line_num, line in enumerate(lines, 1):
            for pattern in cls.RETRY_PATTERNS:
                if pattern.search(line):
                    retry_patterns.append(
                        RetryPattern(
                            pattern_id=cls._generate_pattern_id(
                                file_path, line_num, "retry"
                            ),
                            file_path=str(file_path),
                            line_number=line_num,
                            max_retries=cls._extract_retry_count(content, line_num),
                            backoff_strategy=cls._detect_backoff_strategy(
                                content, line_num
                            ),
                        )
                    )
                    break  # Only one retry pattern per line
        return retry_patterns

    @classmethod
    def scan_file(
        cls, file_path: Path
    ) -> Tuple[List[UsagePattern], List[RetryPattern]]:
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
            logger.warning("Could not read %s: %s", file_path, e)
            return [], []

        lines = content.split("\n")
        usage_patterns = cls._scan_for_llm_patterns(file_path, lines)
        retry_patterns = cls._scan_for_retry_patterns(file_path, lines, content)
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
        hash_val = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:8]
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
        # O(1) lookup (Issue #326)
        if any(model in line.lower() for model in SIMPLE_LLM_MODELS):
            potential += 0.1

        return min(potential, 1.0)

    @classmethod
    def _extract_retry_count(cls, content: str, line_num: int) -> int:
        """Extract retry count from nearby code."""
        lines = content.split("\n")
        start = max(0, line_num - 5)
        end = min(len(lines), line_num + 5)
        context = "\n".join(lines[start:end])

        # Issue #380: Use pre-compiled patterns for retry count extraction
        for pattern in RETRY_COUNT_PATTERNS:
            match = pattern.search(context)
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
# Cache Opportunity Detector
# =============================================================================


class CacheOpportunityDetector:
    """
    Detects opportunities for caching LLM responses.

    Analyzes code patterns to identify where caching could reduce
    redundant API calls and save costs.
    """

    @classmethod
    def _create_embedding_opportunity(
        cls, embeddings: List[UsagePattern]
    ) -> Optional[CacheOpportunity]:
        """
        Create embedding cache opportunity if embeddings exist.

        Issue #620.
        """
        if not embeddings:
            return None
        return CacheOpportunity(
            opportunity_id=cls._generate_id("embed"),
            cache_type=CacheOpportunityType.EMBEDDING_CACHE,
            description="Cache embedding results for repeated text",
            estimated_hit_rate=0.60,
            estimated_savings_percent=40.0,
            affected_calls_per_hour=len(embeddings) * 10,
            implementation_effort="low",
            priority=OptimizationPriority.HIGH,
        )

    @classmethod
    def _create_static_prompt_opportunity(
        cls, patterns: List[UsagePattern]
    ) -> Optional[CacheOpportunity]:
        """
        Create static prompt cache opportunity if cacheable prompts exist.

        Issue #620.
        """
        static_prompts = [
            p
            for p in patterns
            if p.is_cacheable() and p.pattern_type == UsagePatternType.CHAT_COMPLETION
        ]
        if not static_prompts:
            return None
        return CacheOpportunity(
            opportunity_id=cls._generate_id("static"),
            cache_type=CacheOpportunityType.STATIC_PROMPT,
            description="Cache responses for frequently-used static prompts",
            estimated_hit_rate=0.30,
            estimated_savings_percent=25.0,
            affected_calls_per_hour=len(static_prompts) * 5,
            implementation_effort="medium",
            priority=OptimizationPriority.MEDIUM,
        )

    @classmethod
    def _create_analysis_opportunity(
        cls, analysis: List[UsagePattern]
    ) -> Optional[CacheOpportunity]:
        """
        Create analysis response cache opportunity if analysis patterns exist.

        Issue #620.
        """
        if not analysis:
            return None
        return CacheOpportunity(
            opportunity_id=cls._generate_id("analysis"),
            cache_type=CacheOpportunityType.RESPONSE_CACHE,
            description="Cache analysis results with content-based keys",
            estimated_hit_rate=0.45,
            estimated_savings_percent=35.0,
            affected_calls_per_hour=len(analysis) * 8,
            implementation_effort="medium",
            priority=OptimizationPriority.HIGH,
        )

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
        embed_opp = cls._create_embedding_opportunity(embeddings)
        if embed_opp:
            opportunities.append(embed_opp)

        # Static prompt caching
        static_opp = cls._create_static_prompt_opportunity(patterns)
        if static_opp:
            opportunities.append(static_opp)

        # Response caching for analysis tasks
        analysis = patterns_by_type.get(UsagePatternType.ANALYSIS, [])
        analysis_opp = cls._create_analysis_opportunity(analysis)
        if analysis_opp:
            opportunities.append(analysis_opp)

        return opportunities

    @classmethod
    def _generate_id(cls, prefix: str) -> str:
        """Generate a unique opportunity ID."""
        timestamp = str(time.time()).replace(".", "")[:10]
        return f"cache_{prefix}_{timestamp}"


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
                    (p.line_number, p.code_snippet[:50]) for p in sorted_pats[i : i + 2]
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
