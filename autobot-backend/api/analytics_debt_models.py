# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Debt categories, items and weights for the technical-debt calculator (split from analytics_debt.py)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.status_enums import Severity as DebtSeverity  # #6689 consolidation


class DebtCategory(str, Enum):
    """Categories of technical debt"""

    CODE_COMPLEXITY = "code_complexity"
    CODE_DUPLICATION = "code_duplication"
    MISSING_TESTS = "missing_tests"
    MISSING_DOCS = "missing_docs"
    ANTI_PATTERNS = "anti_patterns"
    SECURITY_ISSUES = "security_issues"
    PERFORMANCE_ISSUES = "performance_issues"
    OUTDATED_DEPS = "outdated_dependencies"
    HARDCODED_VALUES = "hardcoded_values"
    DEAD_CODE = "dead_code"


@dataclass
class DebtItem:
    """Individual technical debt item"""

    category: DebtCategory
    severity: DebtSeverity
    file_path: str
    line_number: int | None
    description: str
    estimated_hours: float
    fix_complexity: str  # easy, medium, hard
    business_impact: str  # high, medium, low
    recommendation: str
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert technical debt item to serializable dictionary."""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "description": self.description,
            "estimated_hours": self.estimated_hours,
            "fix_complexity": self.fix_complexity,
            "business_impact": self.business_impact,
            "recommendation": self.recommendation,
            "tags": self.tags,
        }


# Debt calculation weights
SEVERITY_WEIGHTS = {
    DebtSeverity.CRITICAL: 4.0,
    DebtSeverity.HIGH: 2.0,
    DebtSeverity.MEDIUM: 1.0,
    DebtSeverity.LOW: 0.5,
}

# Estimated hours per debt type
DEBT_HOURS_ESTIMATE = {
    DebtCategory.CODE_COMPLEXITY: 2.0,
    DebtCategory.CODE_DUPLICATION: 1.5,
    DebtCategory.MISSING_TESTS: 1.0,
    DebtCategory.MISSING_DOCS: 0.5,
    DebtCategory.ANTI_PATTERNS: 3.0,
    DebtCategory.SECURITY_ISSUES: 4.0,
    DebtCategory.PERFORMANCE_ISSUES: 2.5,
    DebtCategory.OUTDATED_DEPS: 1.0,
    DebtCategory.HARDCODED_VALUES: 0.5,
    DebtCategory.DEAD_CODE: 0.5,
}
