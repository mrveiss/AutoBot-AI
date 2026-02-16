# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Pattern Analyzer - Backward Compatibility Facade

Issue #381: God class refactoring - Original 1,311 lines reduced to ~85 line facade.

This module is a thin wrapper that re-exports from the new
src/code_intelligence/performance_analysis/ package for backward compatibility.
All functionality has been extracted to:
- src/code_intelligence/performance_analysis/types.py: Core data classes
- src/code_intelligence/performance_analysis/patterns.py: Detection patterns
- src/code_intelligence/performance_analysis/ast_visitor.py: PerformanceASTVisitor
- src/code_intelligence/performance_analysis/analyzer.py: PerformanceAnalyzer

Identifies performance anti-patterns and bottlenecks including:
- N+1 query patterns (database queries in loops)
- Nested loop complexity (O(n²) and higher)
- Synchronous operations in async context
- Memory leak patterns
- Cache misuse and invalidation issues
- Inefficient data structure usage

Part of Issue #222 - Performance Pattern Analysis
Parent Epic: #217 - Advanced Code Intelligence

DEPRECATED: Import directly from code_intelligence.performance_analysis instead.
"""

# Re-export everything from the new package for backward compatibility
from backend.code_intelligence.performance_analysis import (  # Types; Pattern constants; AST visitor; Analyzer
    BLOCKING_IO_FALSE_POSITIVES,
    BLOCKING_IO_OPERATIONS,
    BLOCKING_IO_PATTERNS_HIGH_CONFIDENCE,
    BLOCKING_IO_PATTERNS_MEDIUM_CONFIDENCE,
    COMPLEXITY_LEVELS,
    DB_OBJECTS,
    DB_OPERATIONS,
    DB_OPERATIONS_CONTEXTUAL,
    DB_OPERATIONS_FALSE_POSITIVES,
    DB_OPERATIONS_HIGH_CONFIDENCE,
    HTTP_OPERATIONS,
    LEGACY_DB_OPERATIONS,
    SAFE_PATTERNS,
    PerformanceAnalyzer,
    PerformanceASTVisitor,
    PerformanceIssue,
    PerformanceIssueType,
    PerformanceSeverity,
    analyze_performance,
    get_performance_issue_types,
)

# Issue #380: Backward compatibility aliases for module-level constants
_LEGACY_DB_OPERATIONS = LEGACY_DB_OPERATIONS
_DB_OBJECTS = DB_OBJECTS

__all__ = [
    # Types
    "PerformanceSeverity",
    "PerformanceIssueType",
    "PerformanceIssue",
    "COMPLEXITY_LEVELS",
    # Pattern constants
    "BLOCKING_IO_PATTERNS_HIGH_CONFIDENCE",
    "BLOCKING_IO_PATTERNS_MEDIUM_CONFIDENCE",
    "SAFE_PATTERNS",
    "BLOCKING_IO_OPERATIONS",
    "BLOCKING_IO_FALSE_POSITIVES",
    "DB_OPERATIONS_HIGH_CONFIDENCE",
    "DB_OPERATIONS_CONTEXTUAL",
    "DB_OPERATIONS_FALSE_POSITIVES",
    "DB_OPERATIONS",
    "HTTP_OPERATIONS",
    "LEGACY_DB_OPERATIONS",
    "DB_OBJECTS",
    "_LEGACY_DB_OPERATIONS",
    "_DB_OBJECTS",
    # AST visitor
    "PerformanceASTVisitor",
    # Analyzer
    "PerformanceAnalyzer",
    "analyze_performance",
    "get_performance_issue_types",
]
