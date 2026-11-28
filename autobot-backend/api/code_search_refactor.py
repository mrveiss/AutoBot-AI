# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The static refactoring advice of the code-search analytics, split out of ``code_search.py`` (#20402).

``code_search.py`` is grandfathered at its ceiling and may not grow; moving this data makes room for the
per-source scoping its routes now carry.
"""

# Issue #665: Module-level constant for refactoring suggestions
REFACTOR_SUGGESTIONS = (
    {
        "type": "Extract Utility Functions",
        "priority": "high",
        "description": ("Functions with high usage but multiple definitions " "can be centralized"),
        "impact": "Reduces code duplication and improves maintainability",
        "effort": "medium",
    },
    {
        "type": "Create Base Classes",
        "priority": "medium",
        "description": ("Similar classes can be refactored to use inheritance " "or composition"),
        "impact": "Improves code organization and reduces repetition",
        "effort": "high",
    },
    {
        "type": "Standardize Error Handling",
        "priority": "high",
        "description": "Inconsistent error handling patterns detected",
        "impact": "Improves reliability and debugging experience",
        "effort": "medium",
    },
    {
        "type": "Configuration Centralization",
        "priority": "medium",
        "description": "Multiple configuration loading patterns found",
        "impact": "Simplifies configuration management",
        "effort": "low",
    },
)

# Issue #665: Module-level constant for next steps
REFACTOR_NEXT_STEPS = (
    "Review high-priority suggestions first",
    "Use duplicate detection to identify specific refactoring targets",
    "Run declaration analysis to understand usage patterns",
    "Test thoroughly after any refactoring changes",
)


def build_refactor_response(root_path: str, suggestions: list) -> dict:
    """
    Build refactor suggestions response.

    Issue #665: Extracted from get_refactor_suggestions to reduce function length.

    Args:
        root_path: The analyzed codebase path
        suggestions: List of suggestion dicts

    Returns:
        Response content dictionary
    """
    return {
        "refactor_suggestions": suggestions,
        "analysis_summary": {
            "root_path": root_path,
            "suggestion_count": len(suggestions),
            "high_priority_count": sum(1 for s in suggestions if s["priority"] == "high"),
        },
        "next_steps": list(REFACTOR_NEXT_STEPS),
    }
