# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Intelligence Module for AutoBot

Provides advanced code analysis capabilities including:
- Anti-pattern detection
- Code smell identification
- Circular dependency detection
- Redis operation optimization
- Security vulnerability detection
- Metrics and severity scoring

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

from .anti_pattern_detector import AntiPatternDetector, AntiPatternResult
from .redis_optimizer import (
    OptimizationResult,
    OptimizationSeverity,
    OptimizationType,
    RedisOptimizer,
    analyze_redis_usage,
)
from .security_analyzer import (
    SecurityAnalyzer,
    SecurityFinding,
    SecuritySeverity,
    VulnerabilityType,
    analyze_security,
    get_vulnerability_types,
)

__all__ = [
    # Anti-pattern detection (Issue #221)
    "AntiPatternDetector",
    "AntiPatternResult",
    # Redis optimization (Issue #220)
    "RedisOptimizer",
    "OptimizationResult",
    "OptimizationType",
    "OptimizationSeverity",
    "analyze_redis_usage",
    # Security analysis (Issue #219)
    "SecurityAnalyzer",
    "SecurityFinding",
    "SecuritySeverity",
    "VulnerabilityType",
    "analyze_security",
    "get_vulnerability_types",
]
