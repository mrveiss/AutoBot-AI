# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Pattern Analysis Package

Issue #208: Implements Code Pattern Detection & Optimization System using
RAG + Knowledge Graphs for intelligent code analysis.

This package provides:
- CodePatternAnalyzer: Main orchestrator for pattern detection
- RegexPatternDetector: Detects string operations that could be optimized with regex
- ComplexityAnalyzer: Integrates with radon for complexity metrics
- RefactoringSuggestionGenerator: Generates actionable refactoring proposals
- PatternEmbedder: Creates code embeddings for similarity search

Architecture:
    ┌─────────────────────────────────────────────────────────────────────┐
    │                     CodePatternAnalyzer                              │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                      │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
    │  │   AST        │  │   Pattern    │  │   Refactoring            │  │
    │  │   Parser     │→ │   Embedder   │→ │   SuggestionGenerator    │  │
    │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
    │         ↓                  ↓                       ↑                │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
    │  │  Complexity  │  │  ChromaDB    │  │   Similarity             │  │
    │  │  Analyzer    │  │  code_patterns│ │   Search                 │  │
    │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
    │         ↓                  ↓                       ↑                │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
    │  │   Regex      │  │  Dependency  │  │   Pattern                │  │
    │  │   Detector   │  │    Graph     │  │   Clusters               │  │
    │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
    │                                                                      │
    └─────────────────────────────────────────────────────────────────────┘

Usage:
    from src.code_intelligence.pattern_analysis import (
        CodePatternAnalyzer,
        analyze_codebase_patterns,
        PatternAnalysisReport,
    )

    # Quick analysis
    report = await analyze_codebase_patterns("/path/to/code")

    # Custom analysis with options
    analyzer = CodePatternAnalyzer(
        enable_regex_detection=True,
        enable_complexity_analysis=True,
        similarity_threshold=0.8,
    )
    report = await analyzer.analyze_directory("/path/to/code")
"""

# Types and data classes
from .types import (
    PatternType,
    PatternSeverity,
    CodeLocation,
    CodePattern,
    DuplicatePattern,
    RegexOpportunity,
    ModularizationSuggestion,
    ComplexityHotspot,
    PatternCluster,
    PatternAnalysisReport,
)

# Pattern storage
from .storage import (
    get_pattern_collection,
    get_pattern_collection_async,
    store_pattern,
    store_patterns_batch,
    search_similar_patterns,
    delete_pattern,
    get_pattern_stats,
    clear_patterns,
)

# Refactoring types
from .refactoring_generator import RefactoringSuggestion

# Analyzers
from .regex_detector import RegexPatternDetector
from .complexity_analyzer import ComplexityAnalyzer
from .refactoring_generator import RefactoringSuggestionGenerator

# Main analyzer
from .analyzer import CodePatternAnalyzer, analyze_codebase_patterns

__all__ = [
    # Types
    "PatternType",
    "PatternSeverity",
    "CodeLocation",
    "CodePattern",
    "DuplicatePattern",
    "RegexOpportunity",
    "ModularizationSuggestion",
    "ComplexityHotspot",
    "PatternCluster",
    "PatternAnalysisReport",
    # Storage
    "get_pattern_collection",
    "get_pattern_collection_async",
    "store_pattern",
    "store_patterns_batch",
    "search_similar_patterns",
    "delete_pattern",
    "get_pattern_stats",
    "clear_patterns",
    # Refactoring types
    "RefactoringSuggestion",
    # Analyzers
    "RegexPatternDetector",
    "ComplexityAnalyzer",
    "RefactoringSuggestionGenerator",
    # Main analyzer
    "CodePatternAnalyzer",
    "analyze_codebase_patterns",
]
