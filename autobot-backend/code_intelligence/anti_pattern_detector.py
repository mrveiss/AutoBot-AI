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

# Backward compatibility: Expose commonly used regex patterns
import re

# GH#6757: canonical AntiPatternDetector + AntiPatternType live in
# code_analysis.src.  This facade re-exports them so existing callers require
# no import-path changes.  Fall back to the package-local implementations only
# when code_analysis is unavailable (e.g., isolated test environments).
try:
    from code_analysis.src.anti_pattern_detector import AntiPatternDetector  # noqa: F401
    from code_analysis.src.anti_pattern_detector import AntiPatternType  # noqa: F401  — canonical SSOT enum (GH#6757)
except ImportError:
    from .anti_pattern_detection import (  # type: ignore[assignment]
        AntiPatternDetector,
        AntiPatternType,
    )

# Re-export remaining public API from the package for backward compatibility.
# NOTE: AntiPatternType is intentionally NOT imported from here — the canonical
# version from code_analysis.src overrides it above.
from .anti_pattern_detection import (  # Types and enums; Data models; Severity utilities; Detectors; Main analyzer
    ALLOWED_MAGIC_NUMBERS,
    ALLOWED_SINGLE_LETTER_VARS,
    CAMEL_CASE_RE,
    DEFAULT_IGNORE_PATTERNS,
    SNAKE_CASE_RE,
    AnalysisReport,
    AntiPatternResult,
    AntiPatternSeverity,
    BloaterDetector,
    ClassInfo,
    CouplerDetector,
    DispensableDetector,
    FunctionInfo,
    ImportInfo,
    NamingDetector,
    Thresholds,
    analyze_codebase,
    get_complex_conditional_severity,
    get_data_clump_severity,
    get_feature_envy_severity,
    get_god_class_severity,
    get_large_file_severity,
    get_lazy_class_severity,
    get_long_method_severity,
    get_message_chain_severity,
    get_nesting_severity,
    get_param_severity,
    severity_to_numeric,
)

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
