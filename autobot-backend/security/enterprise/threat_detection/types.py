# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Threat Detection Types and Constants

Enums and constants for the threat detection system.

Part of Issue #381 - God Class Refactoring
"""

from enum import Enum

from autobot_shared.status_enums import Severity

# Issue #380: Module-level frozensets to avoid repeated list creation in detection methods
SENSITIVE_RESOURCE_KEYWORDS = frozenset({"admin", "config", "secret", "key", "password"})
FILE_OPERATION_ACTIONS = frozenset({"file_read", "file_write", "file_delete", "file_upload"})

# Issue #315 - Severity priority ordering for comparison
SEVERITY_PRIORITY = {
    level.value: priority
    for priority, level in enumerate((Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL), start=1)
}


# #18098: this was a four-rung fork of the canonical ladder with identical values.
# Callers only read ``.value`` and construct from the four strings (SEVERITY_PRIORITY,
# get_max_severity, threats_by_level), so the alias is wire-neutral.
ThreatLevel = Severity


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
