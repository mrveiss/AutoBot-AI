# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared Scoring Utilities for Code Intelligence Analyzers

Issue #686: Provides centralized scoring calculations using exponential decay
to prevent score overflow (scores collapsing to 0 with many issues).

The exponential decay formula ensures:
- Scores degrade gracefully as issues increase
- Score of 0 is reserved for truly catastrophic cases
- Meaningful differentiation across all severity levels

Formula: score = 100 * exp(-weighted_deduction / decay_constant)

Example scores with decay_constant=150:
- 50 weighted points  -> ~72 score
- 100 weighted points -> ~51 score
- 200 weighted points -> ~26 score
- 500 weighted points -> ~4 score
- 1000+ points        -> ~1 score

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import math
from typing import Any, Dict, Optional

# Default severity weights for score calculation
DEFAULT_SEVERITY_WEIGHTS: Dict[str, float] = {
    "critical": 25.0,
    "high": 10.0,
    "medium": 3.0,
    "low": 1.0,
    "info": 0.5,
}

# Decay constant controls how quickly scores degrade
# Lower = faster decay, Higher = slower decay
# 150 provides good distribution across typical issue counts
DEFAULT_DECAY_CONSTANT: float = 150.0


def calculate_exponential_score(
    weighted_deduction: float,
    decay_constant: float = DEFAULT_DECAY_CONSTANT,
    min_score: float = 1.0,
) -> float:
    """
    Calculate a score using exponential decay.

    Issue #686: Prevents score overflow by using exponential decay instead
    of linear deduction. This ensures scores degrade gracefully and never
    immediately collapse to 0.

    Args:
        weighted_deduction: Total weighted penalty points
        decay_constant: Controls decay rate (default 150)
        min_score: Minimum score to return (default 1.0)

    Returns:
        Score from min_score to 100, rounded to 1 decimal place
    """
    if weighted_deduction <= 0:
        return 100.0

    # Exponential decay formula: score = 100 * e^(-deduction/constant)
    raw_score = 100.0 * math.exp(-weighted_deduction / decay_constant)

    # Ensure minimum score (truly catastrophic cases still get > 0)
    score = max(min_score, raw_score)

    return round(score, 1)


def calculate_weighted_deduction(
    severity_counts: Dict[str, int],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Calculate weighted deduction from severity counts.

    Args:
        severity_counts: Dict mapping severity level to count
            e.g., {"critical": 5, "high": 10, "medium": 20}
        weights: Optional custom weights (uses DEFAULT_SEVERITY_WEIGHTS if None)

    Returns:
        Total weighted deduction points
    """
    if weights is None:
        weights = DEFAULT_SEVERITY_WEIGHTS

    total = 0.0
    for severity, count in severity_counts.items():
        weight = weights.get(severity.lower(), 1.0)
        total += count * weight

    return total


def calculate_score_from_severity_counts(
    severity_counts: Dict[str, int],
    weights: Optional[Dict[str, float]] = None,
    decay_constant: float = DEFAULT_DECAY_CONSTANT,
) -> float:
    """
    Calculate score directly from severity counts.

    Convenience function that combines weighted deduction calculation
    with exponential score calculation.

    Args:
        severity_counts: Dict mapping severity level to count
        weights: Optional custom weights
        decay_constant: Controls decay rate

    Returns:
        Score from 1 to 100
    """
    deduction = calculate_weighted_deduction(severity_counts, weights)
    return calculate_exponential_score(deduction, decay_constant)


def get_grade_from_score(score: float) -> str:
    """
    Get letter grade from numeric score.

    Args:
        score: Numeric score from 0-100

    Returns:
        Letter grade: A, B, C, D, or F
    """
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def get_risk_level_from_score(score: float) -> str:
    """
    Get risk level from score.

    Args:
        score: Numeric score from 0-100

    Returns:
        Risk level: low, medium, high, or critical
    """
    if score >= 80:
        return "low"
    if score >= 60:
        return "medium"
    if score >= 40:
        return "high"
    return "critical"


def get_status_message(
    score: float,
    category: str = "general",
) -> str:
    """
    Get human-readable status message based on score.

    Args:
        score: Numeric score from 0-100
        category: Category for context-specific messages
            Options: "security", "performance", "redis", "general"

    Returns:
        Human-readable status message
    """
    messages = {
        "security": {
            90: "Excellent security posture",
            80: "Good security with minor issues",
            60: "Fair security - several vulnerabilities to address",
            40: "Poor security - significant vulnerabilities present",
            0: "Critical security issues - immediate attention required",
        },
        "performance": {
            90: "Excellent performance - minimal issues",
            80: "Good performance with minor optimizations possible",
            60: "Fair performance - several optimizations recommended",
            40: "Performance issues detected - optimization needed",
            0: "Critical performance problems - immediate action required",
        },
        "redis": {
            90: "Excellent Redis usage patterns",
            80: "Good Redis usage with minor improvements possible",
            60: "Fair Redis usage - several optimizations recommended",
            40: "Poor Redis usage - significant optimization needed",
            0: "Critical Redis usage issues - immediate attention required",
        },
        "general": {
            90: "Excellent - minimal issues detected",
            80: "Good - minor improvements possible",
            60: "Fair - several issues to address",
            40: "Poor - significant issues present",
            0: "Critical - immediate attention required",
        },
    }

    category_messages = messages.get(category, messages["general"])

    for threshold in sorted(category_messages.keys(), reverse=True):
        if score >= threshold:
            return category_messages[threshold]

    return category_messages[0]


# Pre-calculated score examples for documentation/testing
SCORE_EXAMPLES: Dict[str, Dict[str, Any]] = {
    "clean_codebase": {
        "severity_counts": {"critical": 0, "high": 0, "medium": 5, "low": 10},
        "expected_score": 83.5,  # 25 weighted points
        "grade": "B",
    },
    "minor_issues": {
        "severity_counts": {"critical": 0, "high": 5, "medium": 10, "low": 20},
        "expected_score": 51.3,  # 100 weighted points
        "grade": "F",
    },
    "significant_issues": {
        "severity_counts": {"critical": 5, "high": 20, "medium": 50, "low": 100},
        "expected_score": 8.2,  # 475 weighted points
        "grade": "F",
    },
    "severe_issues": {
        "severity_counts": {"critical": 23, "high": 65, "medium": 100, "low": 200},
        "expected_score": 1.0,  # 1525 weighted points (capped at min)
        "grade": "F",
    },
}
