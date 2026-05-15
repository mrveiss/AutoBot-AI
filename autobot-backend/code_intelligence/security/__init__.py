# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Analysis Package - Modularized from security_analyzer.py

Issue #712: Split large file into focused modules for maintainability.

Package Structure:
- constants.py: Enums, OWASP mappings, pattern constants
- finding.py: SecurityFinding dataclass
- patterns.py: Regex patterns for detection
- ast_visitor.py: SecurityASTVisitor class
- analyzer.py: Main SecurityAnalyzer class
- utils.py: Convenience functions
"""

from .analyzer import SecurityAnalyzer
from .ast_visitor import SecurityASTVisitor
from .constants import (
    OWASP_MAPPING,
    PLACEHOLDER_PATTERNS,
    WEAK_ENCRYPTION,
    WEAK_HASH_ALGORITHMS,
    SecuritySeverity,
    VulnerabilityType,
)
from .finding import SecurityFinding
from .patterns import (
    COMMAND_INJECTION_PATTERNS,
    SECRET_PATTERNS,
    SQL_INJECTION_PATTERNS,
)
from .utils import analyze_security, analyze_security_async, get_vulnerability_types

__all__ = [
    # Enums
    "SecuritySeverity",
    "VulnerabilityType",
    # Mappings
    "OWASP_MAPPING",
    "WEAK_HASH_ALGORITHMS",
    "WEAK_ENCRYPTION",
    "PLACEHOLDER_PATTERNS",
    # Patterns
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
