# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Pattern Analysis Package

This package contains the LLM pattern analyzer system for cost optimization.
It was split from the monolithic llm_pattern_analyzer.py as part of Issue #381.

Package Structure:
- types.py: Enums, constants, and pre-compiled regex patterns
- data_models.py: Data classes (TokenUsage, UsagePattern, etc.)
- prompt_analyzer.py: PromptAnalyzer class
- scanners.py: CodePatternScanner, CacheOpportunityDetector, BatchingAnalyzer
- calculators.py: TokenTracker, CostCalculator
- recommendation_engine.py: RecommendationEngine class

Usage:
    from code_intelligence.llm_pattern_analysis import (
        # Enums
        OptimizationCategory, OptimizationPriority, CacheOpportunityType,
        UsagePatternType, PromptIssueType,
        # Data classes
        TokenUsage, PromptAnalysisResult, PromptTemplate, CacheOpportunity,
        UsagePattern, RetryPattern, BatchingOpportunity, CostEstimate,
        OptimizationRecommendation, AnalysisResult,
        # Classes
        TokenTracker, PromptAnalyzer, CodePatternScanner,
        CacheOpportunityDetector, BatchingAnalyzer, CostCalculator,
        RecommendationEngine,
    )

For backward compatibility, the original llm_pattern_analyzer.py module
still exports all classes directly.
"""

# Types and constants
from code_intelligence.llm_pattern_analysis.types import (
    CacheOpportunityType,
    EXCESSIVE_CONTEXT_PATTERNS,
    FORMAT_INEFFICIENCY_PATTERNS,
    HIGH_PRIORITY_LEVELS,
    OptimizationCategory,
    OptimizationPriority,
    PromptIssueType,
    REDUNDANT_PATTERNS,
    RETRY_COUNT_PATTERNS,
    RETRY_LOGIC_PATTERNS,
    SIMPLE_LLM_MODELS,
    TEMPLATE_VAR_PATTERNS,
    UsagePatternType,
    VALID_BACKOFF_STRATEGIES,
)

# Data models
from code_intelligence.llm_pattern_analysis.data_models import (
    AnalysisResult,
    BatchingOpportunity,
    CacheOpportunity,
    CostEstimate,
    OptimizationRecommendation,
    PromptAnalysisResult,
    PromptTemplate,
    RetryPattern,
    TokenUsage,
    UsagePattern,
)

# Analyzers and scanners
from code_intelligence.llm_pattern_analysis.prompt_analyzer import PromptAnalyzer
from code_intelligence.llm_pattern_analysis.scanners import (
    BatchingAnalyzer,
    CacheOpportunityDetector,
    CodePatternScanner,
)
from code_intelligence.llm_pattern_analysis.calculators import (
    CostCalculator,
    TokenTracker,
)
from code_intelligence.llm_pattern_analysis.recommendation_engine import (
    RecommendationEngine,
)

# Re-export for convenience
__all__ = [
    # Enums
    "OptimizationCategory",
    "OptimizationPriority",
    "CacheOpportunityType",
    "UsagePatternType",
    "PromptIssueType",
    # Constants
    "HIGH_PRIORITY_LEVELS",
    "SIMPLE_LLM_MODELS",
    "VALID_BACKOFF_STRATEGIES",
    "REDUNDANT_PATTERNS",
    "EXCESSIVE_CONTEXT_PATTERNS",
    "FORMAT_INEFFICIENCY_PATTERNS",
    "TEMPLATE_VAR_PATTERNS",
    "RETRY_COUNT_PATTERNS",
    "RETRY_LOGIC_PATTERNS",
    # Data classes
    "TokenUsage",
    "PromptAnalysisResult",
    "PromptTemplate",
    "CacheOpportunity",
    "UsagePattern",
    "RetryPattern",
    "BatchingOpportunity",
    "CostEstimate",
    "OptimizationRecommendation",
    "AnalysisResult",
    # Classes
    "TokenTracker",
    "PromptAnalyzer",
    "CodePatternScanner",
    "CacheOpportunityDetector",
    "BatchingAnalyzer",
    "CostCalculator",
    "RecommendationEngine",
]
