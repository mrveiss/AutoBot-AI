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
- AI-powered code review automation
- Dynamic log pattern mining
- Conversation flow analysis
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
from .code_review_engine import (
    CodeReviewEngine,
    DiffFile,
    DiffHunk,
    ReviewCategory,
    ReviewComment,
    ReviewPattern,
    ReviewResult,
    ReviewSeverity,
    get_review_categories,
    get_review_patterns,
    get_review_severities,
    review_commit,
    review_diff,
    review_file,
    review_staged,
)
from .log_pattern_miner import (
    Anomaly,
    AnomalyType,
    LogEntry,
    LogLevel,
    LogPattern,
    LogPatternMiner,
    MiningResult,
    PatternType,
    SessionFlow,
    analyze_logs,
    get_anomaly_types,
    get_log_levels,
    get_pattern_types,
)
from .conversation_flow_analyzer import (
    AnalysisResult,
    Bottleneck,
    BottleneckType,
    ConversationFlow,
    ConversationFlowAnalyzer,
    ConversationMessage,
    FlowPattern,
    FlowState,
    IntentCategory,
    IntentClassifier,
    Optimization,
    OptimizationType as ConversationOptimizationType,
    ResponseClassifier,
    ResponseType,
    analyze_conversations,
    classify_intent,
    classify_response,
    get_bottleneck_types,
    get_intent_categories,
    get_optimization_types,
    get_response_types,
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
    # Code review automation (Issue #225)
    "CodeReviewEngine",
    "DiffFile",
    "DiffHunk",
    "ReviewCategory",
    "ReviewComment",
    "ReviewPattern",
    "ReviewResult",
    "ReviewSeverity",
    "get_review_categories",
    "get_review_patterns",
    "get_review_severities",
    "review_commit",
    "review_diff",
    "review_file",
    "review_staged",
    # Log pattern mining (Issue #226)
    "Anomaly",
    "AnomalyType",
    "LogEntry",
    "LogLevel",
    "LogPattern",
    "LogPatternMiner",
    "MiningResult",
    "PatternType",
    "SessionFlow",
    "analyze_logs",
    "get_anomaly_types",
    "get_log_levels",
    "get_pattern_types",
    # Conversation flow analysis (Issue #227)
    "AnalysisResult",
    "Bottleneck",
    "BottleneckType",
    "ConversationFlow",
    "ConversationFlowAnalyzer",
    "ConversationMessage",
    "FlowPattern",
    "FlowState",
    "IntentCategory",
    "IntentClassifier",
    "Optimization",
    "ConversationOptimizationType",
    "ResponseClassifier",
    "ResponseType",
    "analyze_conversations",
    "classify_intent",
    "classify_response",
    "get_bottleneck_types",
    "get_intent_categories",
    "get_optimization_types",
    "get_response_types",
]
