# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Analysis Package

Issue #381: Extracted from performance_analyzer.py god class refactoring.
Provides performance pattern analysis for Python code.

Package Structure:
- types.py: Core data classes (PerformanceIssue, PerformanceSeverity, PerformanceIssueType)
- patterns.py: Detection pattern constants for blocking I/O, database ops, HTTP
- ast_visitor.py: PerformanceASTVisitor for AST-based analysis
- analyzer.py: PerformanceAnalyzer main class and convenience functions
"""

# Re-export all public types for backward compatibility
from .types import (
    COMPLEXITY_LEVELS,
    PerformanceIssue,
    PerformanceIssueType,
    PerformanceSeverity,
)

# Re-export pattern constants
from .patterns import (
    BLOCKING_IO_FALSE_POSITIVES,
    BLOCKING_IO_OPERATIONS,
    BLOCKING_IO_PATTERNS_HIGH_CONFIDENCE,
    BLOCKING_IO_PATTERNS_MEDIUM_CONFIDENCE,
    DB_OBJECTS,
    DB_OPERATIONS,
    DB_OPERATIONS_CONTEXTUAL,
    DB_OPERATIONS_FALSE_POSITIVES,
    DB_OPERATIONS_HIGH_CONFIDENCE,
    HTTP_OPERATIONS,
    LEGACY_DB_OPERATIONS,
    SAFE_PATTERNS,
)

# Re-export AST visitor
from .ast_visitor import PerformanceASTVisitor

# Re-export analyzer class and convenience functions
from .analyzer import (
    PerformanceAnalyzer,
    analyze_performance,
    analyze_performance_async,
    get_performance_issue_types,
)

# Issue #554: Infrastructure availability flag
try:
    from .analyzer import HAS_ANALYTICS_INFRASTRUCTURE
except ImportError:
    HAS_ANALYTICS_INFRASTRUCTURE = False

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
    # AST visitor
    "PerformanceASTVisitor",
    # Analyzer
    "PerformanceAnalyzer",
    "analyze_performance",
    "analyze_performance_async",
    "get_performance_issue_types",
    # Issue #554: Infrastructure
    "HAS_ANALYTICS_INFRASTRUCTURE",
]
