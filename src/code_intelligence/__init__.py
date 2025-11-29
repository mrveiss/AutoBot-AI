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
- Performance pattern analysis
- Pre-commit hook analysis
- Bug prediction and risk scoring
- Metrics and severity scoring

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

from .anti_pattern_detector import AntiPatternDetector, AntiPatternResult
from .bug_predictor import (
    BugPredictor,
    FileRiskAssessment,
    PredictionResult,
    RiskFactor,
    RiskFactorScore,
    RiskLevel,
    get_file_risk,
    get_high_risk_files,
    get_risk_factors,
    get_risk_levels,
    predict_bugs,
)
from .precommit_analyzer import (
    CheckCategory,
    CheckDefinition,
    CheckResult,
    CheckSeverity,
    CommitCheckResult,
    PrecommitAnalyzer,
    analyze_precommit,
    get_check_categories,
    get_precommit_checks,
)
from .performance_analyzer import (
    PerformanceAnalyzer,
    PerformanceIssue,
    PerformanceIssueType,
    PerformanceSeverity,
    analyze_performance,
    get_performance_issue_types,
)
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
    # Performance analysis (Issue #222)
    "PerformanceAnalyzer",
    "PerformanceIssue",
    "PerformanceIssueType",
    "PerformanceSeverity",
    "analyze_performance",
    "get_performance_issue_types",
    # Pre-commit analysis (Issue #223)
    "PrecommitAnalyzer",
    "CheckCategory",
    "CheckDefinition",
    "CheckResult",
    "CheckSeverity",
    "CommitCheckResult",
    "analyze_precommit",
    "get_precommit_checks",
    "get_check_categories",
    # Bug prediction (Issue #224)
    "BugPredictor",
    "FileRiskAssessment",
    "PredictionResult",
    "RiskFactor",
    "RiskFactorScore",
    "RiskLevel",
    "get_file_risk",
    "get_high_risk_files",
    "get_risk_factors",
    "get_risk_levels",
    "predict_bugs",
]
