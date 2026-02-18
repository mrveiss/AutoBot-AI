# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Threat Detection Types and Constants

Enums and constants for the threat detection system.

Part of Issue #381 - God Class Refactoring
"""

from enum import Enum

# Issue #380: Module-level frozensets to avoid repeated list creation in detection methods
SENSITIVE_RESOURCE_KEYWORDS = frozenset(
    {"admin", "config", "secret", "key", "password"}
)
FILE_OPERATION_ACTIONS = frozenset(
    {"file_read", "file_write", "file_delete", "file_upload"}
)

# Issue #315 - Severity priority ordering for comparison
SEVERITY_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class ThreatLevel(Enum):
    """Threat severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatCategory(Enum):
    """Categories of security threats"""

    COMMAND_INJECTION = "command_injection"
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"
    BRUTE_FORCE = "brute_force"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    MALICIOUS_UPLOAD = "malicious_upload"
    INSIDER_THREAT = "insider_threat"
    API_ABUSE = "api_abuse"
    RECONNAISSANCE = "reconnaissance"
    LATERAL_MOVEMENT = "lateral_movement"


def get_max_severity(current: str, new: str) -> str:
    """Return the higher severity between two values (Issue #315 - extracted helper)."""
    if SEVERITY_PRIORITY.get(new, 0) > SEVERITY_PRIORITY.get(current, 0):
        return new
    return current
