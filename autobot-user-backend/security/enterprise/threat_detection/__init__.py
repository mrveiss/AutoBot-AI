# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Threat Detection Package

Advanced threat detection with ML-based anomaly detection, behavioral analysis,
and multiple specialized threat analyzers.

Part of Issue #381 - God Class Refactoring

Original module: 1,517 lines
New package: ~1,300 lines across multiple focused modules

Usage:
    from security.enterprise.threat_detection import (
        ThreatDetectionEngine,
        ThreatLevel,
        ThreatCategory,
    )

    # Create engine
    engine = ThreatDetectionEngine()

    # Analyze an event
    threat = await engine.analyze_event({
        "user_id": "user123",
        "action": "authentication",
        "outcome": "failure",
        "source_ip": "192.168.1.100",
        "timestamp": "2025-01-01T12:00:00",
    })

    if threat:
        # Handle detected threat
        logger.warning("Threat detected: %s", threat.threat_category.value)
"""

# Types and constants
from .types import (
    FILE_OPERATION_ACTIONS,
    SENSITIVE_RESOURCE_KEYWORDS,
    SEVERITY_PRIORITY,
    ThreatCategory,
    ThreatLevel,
    get_max_severity,
)

# Data models
from .models import (
    AnalysisContext,
    EventHistory,
    SecurityEvent,
    ThreatEvent,
    UserProfile,
)

# Analyzers
from .analyzers import (
    APIAbuseAnalyzer,
    BehavioralAnomalyAnalyzer,
    BruteForceAnalyzer,
    CommandInjectionAnalyzer,
    InsiderThreatAnalyzer,
    MaliciousFileAnalyzer,
    ThreatAnalyzer,
)

# Main engine
from .engine import ThreatDetectionEngine

# Backward compatibility for internal constants (used by existing code)
_SENSITIVE_RESOURCE_KEYWORDS = SENSITIVE_RESOURCE_KEYWORDS
_FILE_OPERATION_ACTIONS = FILE_OPERATION_ACTIONS
_SEVERITY_PRIORITY = SEVERITY_PRIORITY
_get_max_severity = get_max_severity

__all__ = [
    # Types and constants
    "ThreatLevel",
    "ThreatCategory",
    "SENSITIVE_RESOURCE_KEYWORDS",
    "FILE_OPERATION_ACTIONS",
    "SEVERITY_PRIORITY",
    "get_max_severity",
    # Backward compatibility aliases
    "_SENSITIVE_RESOURCE_KEYWORDS",
    "_FILE_OPERATION_ACTIONS",
    "_SEVERITY_PRIORITY",
    "_get_max_severity",
    # Models
    "SecurityEvent",
    "EventHistory",
    "ThreatEvent",
    "UserProfile",
    "AnalysisContext",
    # Analyzers
    "ThreatAnalyzer",
    "APIAbuseAnalyzer",
    "BehavioralAnomalyAnalyzer",
    "BruteForceAnalyzer",
    "CommandInjectionAnalyzer",
    "InsiderThreatAnalyzer",
    "MaliciousFileAnalyzer",
    # Engine
    "ThreatDetectionEngine",
]
