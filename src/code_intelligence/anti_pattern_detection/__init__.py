# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Detection Package

Provides comprehensive anti-pattern detection for Python codebases.

This package refactors the original monolithic anti_pattern_detector.py
into focused, single-responsibility modules.

Part of Issue #381 - God Class Refactoring

Usage:
    from src.code_intelligence.anti_pattern_detection import (
        AntiPatternDetector,
        AntiPatternType,
        AntiPatternSeverity,
        AntiPatternResult,
        AnalysisReport,
        analyze_codebase,
    )

    # Quick analysis
    report = analyze_codebase("/path/to/code")

    # Custom analysis
    detector = AntiPatternDetector()
    report = detector.analyze_directory("/path/to/code")
"""

# Types and enums
from .types import (
    AntiPatternSeverity,
    AntiPatternType,
    Thresholds,
    SNAKE_CASE_RE,
    CAMEL_CASE_RE,
    DEFAULT_IGNORE_PATTERNS,
    ALLOWED_SINGLE_LETTER_VARS,
    ALLOWED_MAGIC_NUMBERS,
)

# Data models
from .models import (
    AntiPatternResult,
    AnalysisReport,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
)

# Severity utilities
from .severity_utils import (
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
)

# Detectors
from .detectors import (
    BloaterDetector,
    CouplerDetector,
    DispensableDetector,
    NamingDetector,
)

# Main analyzer
from .analyzer import AntiPatternDetector, analyze_codebase, analyze_codebase_async

# Issue #554: Infrastructure availability flag
try:
    from .analyzer import HAS_ANALYTICS_INFRASTRUCTURE
except ImportError:
    HAS_ANALYTICS_INFRASTRUCTURE = False

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
    "analyze_codebase_async",
    # Issue #554: Infrastructure
    "HAS_ANALYTICS_INFRASTRUCTURE",
]
