# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Security Pattern Analyzer — re-export shim.

Issue #9856: Modular package code_intelligence.security is now canonical.
This module re-exports all public names so existing import paths keep working
and security_analyzer_test.py exercises the package through this shim.

Do not add logic here; add it to code_intelligence/security/.
"""

from code_intelligence.security import (  # noqa: F401
    COMMAND_INJECTION_PATTERNS,
    OWASP_MAPPING,
    PLACEHOLDER_PATTERNS,
    SECRET_PATTERNS,
    SQL_INJECTION_PATTERNS,
    WEAK_ENCRYPTION,
    WEAK_HASH_ALGORITHMS,
    SecurityAnalyzer,
    SecurityASTVisitor,
    SecurityFinding,
    SecuritySeverity,
    VulnerabilityType,
    analyze_security,
    analyze_security_async,
    get_vulnerability_types,
)

__all__ = [
    # Enums
    "SecuritySeverity",
    "VulnerabilityType",
    # Mappings / pattern constants
    "OWASP_MAPPING",
    "WEAK_HASH_ALGORITHMS",
    "WEAK_ENCRYPTION",
    "PLACEHOLDER_PATTERNS",
    "SECRET_PATTERNS",
    "SQL_INJECTION_PATTERNS",
    "COMMAND_INJECTION_PATTERNS",
    # Classes
    "SecurityFinding",
    "SecurityASTVisitor",
    "SecurityAnalyzer",
    # Functions
    "analyze_security",
    "analyze_security_async",
    "get_vulnerability_types",
]
