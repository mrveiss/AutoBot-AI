# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Detection System - Facade Module

Identifies code anti-patterns and smells including:
- God classes (>20 methods)
- Feature envy
- Circular dependencies
- Long parameter lists
- Dead code
- Duplicate abstraction

Part of Issue #221 - Anti-Pattern Detection System
Parent Epic: #217 - Advanced Code Intelligence

Refactored as part of Issue #381 - God Class Refactoring
This module now serves as a facade that re-exports from the
anti_pattern_detection package for backward compatibility.

Original module: 1,294 lines
New facade: ~100 lines (92% reduction)
"""

# Re-export all public API from the package for backward compatibility
from .anti_pattern_detection import (
    # Types and enums
    AntiPatternSeverity,
    AntiPatternType,
    Thresholds,
    SNAKE_CASE_RE,
    CAMEL_CASE_RE,
    DEFAULT_IGNORE_PATTERNS,
    ALLOWED_SINGLE_LETTER_VARS,
    ALLOWED_MAGIC_NUMBERS,
    # Data models
    AntiPatternResult,
    AnalysisReport,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    # Severity utilities
    get_god_class_severity,
    get_param_severity,
    get_large_file_severity,
    get_long_method_severity,
    get_nesting_severity,
    get_message_chain_severity,
    get_complex_conditional_severity,
    get_lazy_class_severity,
    get_feature_envy_severity,
    get_data_clump_severity,
    severity_to_numeric,
    # Detectors
    BloaterDetector,
    CouplerDetector,
    DispensableDetector,
    NamingDetector,
    # Main analyzer
    AntiPatternDetector,
    analyze_codebase,
)

# Backward compatibility: Expose commonly used regex patterns
import re
_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CAMEL_CASE_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")

# Backward compatibility: Expose AST node type tuples
import ast
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_EXIT_STMT_TYPES = (ast.Return, ast.Raise)

__all__ = [
    # Types and enums
    "AntiPatternSeverity",
    "AntiPatternType",
    "Thresholds",
    "SNAKE_CASE_RE",
    "CAMEL_CASE_RE",
    "DEFAULT_IGNORE_PATTERNS",
    "ALLOWED_SINGLE_LETTER_VARS",
    "ALLOWED_MAGIC_NUMBERS",
    # Data models
    "AntiPatternResult",
    "AnalysisReport",
    "ClassInfo",
    "FunctionInfo",
    "ImportInfo",
    # Severity utilities
    "get_god_class_severity",
    "get_param_severity",
    "get_large_file_severity",
    "get_long_method_severity",
    "get_nesting_severity",
    "get_message_chain_severity",
    "get_complex_conditional_severity",
    "get_lazy_class_severity",
    "get_feature_envy_severity",
    "get_data_clump_severity",
    "severity_to_numeric",
    # Detectors
    "BloaterDetector",
    "CouplerDetector",
    "DispensableDetector",
    "NamingDetector",
    # Main analyzer
    "AntiPatternDetector",
    "analyze_codebase",
    # Backward compatibility
    "_SNAKE_CASE_RE",
    "_CAMEL_CASE_RE",
    "_FUNCTION_DEF_TYPES",
    "_EXIT_STMT_TYPES",
]
