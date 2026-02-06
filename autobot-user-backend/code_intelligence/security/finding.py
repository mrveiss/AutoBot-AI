# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SecurityFinding dataclass for security analysis results.

Issue #712: Extracted from security_analyzer.py for modularity.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constants import SecuritySeverity, VulnerabilityType


@dataclass
class SecurityFinding:
    """Result of security analysis for a single finding."""

    vulnerability_type: VulnerabilityType
    severity: SecuritySeverity
    file_path: str
    line_start: int
    line_end: int
    description: str
    recommendation: str
    owasp_category: str
    cwe_id: Optional[str] = None
    current_code: str = ""
    secure_alternative: str = ""
    confidence: float = 1.0
    false_positive_risk: str = "low"
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to dictionary for API responses."""
        return {
            "vulnerability_type": self.vulnerability_type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "description": self.description,
            "recommendation": self.recommendation,
            "owasp_category": self.owasp_category,
            "cwe_id": self.cwe_id,
            "current_code": self.current_code,
            "secure_alternative": self.secure_alternative,
            "confidence": self.confidence,
            "false_positive_risk": self.false_positive_risk,
            "references": self.references,
        }
