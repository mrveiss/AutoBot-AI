# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared Utilities for Code Intelligence Analyzers

Issue #607: Provides centralized caching utilities to eliminate redundant
file traversals and AST parsing across multiple analyzers.

Components:
    - FileListCache: Cached file discovery (eliminates 10+ rglob calls)
    - ASTCache: Cached AST parsing (eliminates 5-10x redundant parsing)
    - FileContentCache: Cached file content reading

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

from code_intelligence.shared.ast_cache import (
    ASTCache,
    get_ast,
    get_ast_cache_stats,
    get_ast_safe,
    get_ast_with_content,
    invalidate_ast_cache,
)
from code_intelligence.shared.file_cache import (
    FileListCache,
    get_all_code_files,
    get_file_cache_stats,
    get_frontend_files,
    get_python_files,
    invalidate_file_cache,
)

# Issue #686: Scoring utilities for consistent score calculation
from code_intelligence.shared.scoring import (
    DEFAULT_DECAY_CONSTANT,
    DEFAULT_SEVERITY_WEIGHTS,
    calculate_exponential_score,
    calculate_score_from_severity_counts,
    calculate_weighted_deduction,
    get_grade_from_score,
    get_risk_level_from_score,
    get_status_message,
)

__all__ = [
    # FileListCache
    "FileListCache",
    "get_python_files",
    "get_frontend_files",
    "get_all_code_files",
    "invalidate_file_cache",
    "get_file_cache_stats",
    # ASTCache
    "ASTCache",
    "get_ast",
    "get_ast_safe",
    "get_ast_with_content",
    "invalidate_ast_cache",
    "get_ast_cache_stats",
    # Scoring utilities (Issue #686)
    "calculate_exponential_score",
    "calculate_weighted_deduction",
    "calculate_score_from_severity_counts",
    "get_grade_from_score",
    "get_risk_level_from_score",
    "get_status_message",
    "DEFAULT_SEVERITY_WEIGHTS",
    "DEFAULT_DECAY_CONSTANT",
]
