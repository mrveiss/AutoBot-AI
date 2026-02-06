# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Pattern Detection Utilities

Reusable pre-compiled regex patterns for detecting hardcoded values,
security issues, and sensitive data in code.

Performance Optimizations:
- Patterns are pre-compiled at module load time (O(1) access)
- Combined alternation patterns reduce regex engine overhead
- finditer() recommended for memory-efficient iteration

Usage:
    from utils.security_patterns import HARDCODED_PATTERNS, find_hardcoded_values

    # Direct pattern access
    for category, pattern in HARDCODED_PATTERNS.items():
        for match in pattern.finditer(text):
            value = extract_match_value(match)

    # High-level API
    findings = find_hardcoded_values(text, doc_id="file.py")
"""

import re
from typing import Any, Callable, Iterator


# Pre-compiled regex patterns for hardcoded value detection
# Each pattern combines multiple sub-patterns using alternation for efficiency
HARDCODED_PATTERNS: dict[str, re.Pattern[str]] = {
    "ip_addresses": re.compile(
        r'\b(?:(?:\d{1,3}\.){3}\d{1,3}|localhost|127\.0\.0\.1|0\.0\.0\.0)\b',
        re.IGNORECASE | re.MULTILINE
    ),
    "urls": re.compile(
        r'(?:https?|ftp|wss?)://[^\s"\'<>]+',
        re.IGNORECASE | re.MULTILINE
    ),
    "passwords": re.compile(
        r'(?:password|pwd|secret)\s*[:=]\s*["\']([^"\']+)["\']',
        re.IGNORECASE | re.MULTILINE
    ),
    "api_keys": re.compile(
        r'(?:api[_-]?key|access[_-]?token)\s*[:=]\s*["\']([^"\']+)["\']|bearer\s+([a-zA-Z0-9_-]{20,})',
        re.IGNORECASE | re.MULTILINE
    ),
    "database_connections": re.compile(
        r'(?:mongodb|postgresql|mysql|redis)://[^\s"\'<>]+',
        re.IGNORECASE | re.MULTILINE
    ),
    "file_paths": re.compile(
        r'(?:(?:/[^/\s"\'<>]+){2,}|[C-Z]:\\[^\s"\'<>\\]+(?:\\[^\s"\'<>\\]+)+|~/[^\s"\'<>]+)',
        re.IGNORECASE | re.MULTILINE
    ),
    "private_keys": re.compile(
        r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
        re.IGNORECASE | re.MULTILINE
    ),
    "aws_credentials": re.compile(
        r'(?:AKIA[0-9A-Z]{16}|aws[_-]?(?:access|secret)[_-]?key\s*[:=]\s*["\']([^"\']+)["\'])',
        re.IGNORECASE | re.MULTILINE
    ),
    "jwt_tokens": re.compile(
        r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',
        re.MULTILINE
    ),
    "email_addresses": re.compile(
        r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
        re.IGNORECASE | re.MULTILINE
    )
}

# Severity mappings for different categories
SEVERITY_MAP: dict[str, str] = {
    "passwords": "critical",
    "api_keys": "critical",
    "private_keys": "critical",
    "aws_credentials": "critical",
    "jwt_tokens": "high",
    "database_connections": "high",
    "ip_addresses": "medium",
    "urls": "low",
    "file_paths": "low",
    "email_addresses": "low"
}

# False positive patterns to exclude
FALSE_POSITIVE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "ip_addresses": [
        re.compile(r'^0\.0\.0\.0$'),  # Bind all interfaces (common in configs)
        re.compile(r'^255\.255\.255\.\d+$'),  # Subnet masks
    ],
    "urls": [
        re.compile(r'example\.com'),
        re.compile(r'localhost'),
        re.compile(r'placeholder'),
    ],
    "file_paths": [
        re.compile(r'^/dev/'),  # Device paths
        re.compile(r'^/proc/'),  # Proc filesystem
        re.compile(r'^/sys/'),  # Sys filesystem
    ]
}


def extract_match_value(match: re.Match[str]) -> str:
    """Extract the actual value from a regex match, handling groups.

    Args:
        match: Regex match object

    Returns:
        The matched value (from groups if present, otherwise full match)
    """
    groups = match.groups()
    return next((g for g in groups if g), None) or match.group(0)


def is_false_positive(category: str, value: str) -> bool:
    """Check if a matched value is a known false positive.

    Args:
        category: The pattern category (ip_addresses, urls, etc.)
        value: The matched value to check

    Returns:
        True if the value is likely a false positive
    """
    if category not in FALSE_POSITIVE_PATTERNS:
        return False

    for pattern in FALSE_POSITIVE_PATTERNS[category]:
        if pattern.search(value):
            return True

    return False


def get_severity(category: str, value: str) -> str:
    """Get the severity level for a hardcoded value.

    Args:
        category: The pattern category
        value: The matched value

    Returns:
        Severity level (critical, high, medium, low)
    """
    return SEVERITY_MAP.get(category, "medium")


def find_hardcoded_values(
    text: str,
    doc_id: str = "unknown",
    categories: list[str] | None = None,
    exclude_false_positives: bool = True,
    is_likely_hardcoded: Callable[[str, str], bool] | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Find all hardcoded values in text using pre-compiled patterns.

    This is the high-level API for hardcoded value detection, optimized
    from O(n × c × p × m) to O(n × c × m) using pre-compiled patterns.

    Args:
        text: The source code text to analyze
        doc_id: Document identifier for reporting
        categories: Optional list of categories to check (default: all)
        exclude_false_positives: Whether to filter known false positives
        is_likely_hardcoded: Optional custom filter function

    Returns:
        Dictionary mapping categories to lists of findings
    """
    results: dict[str, list[dict[str, Any]]] = {cat: [] for cat in HARDCODED_PATTERNS}

    # Filter to requested categories if specified
    patterns_to_check = HARDCODED_PATTERNS
    if categories:
        patterns_to_check = {k: v for k, v in HARDCODED_PATTERNS.items() if k in categories}

    for category, pattern in patterns_to_check.items():
        for match in pattern.finditer(text):
            value = extract_match_value(match)

            # Skip false positives
            if exclude_false_positives and is_false_positive(category, value):
                continue

            # Apply custom filter if provided
            if is_likely_hardcoded and not is_likely_hardcoded(category, value):
                continue

            match_pos = match.start()
            results[category].append({
                "value": value,
                "file": doc_id,
                "context": text[max(0, match_pos - 50):match_pos + 100],
                "severity": get_severity(category, value),
                "line": text[:match_pos].count('\n') + 1,
                "column": match_pos - text.rfind('\n', 0, match_pos)
            })

    return results


def iter_hardcoded_values(
    text: str,
    categories: list[str] | None = None
) -> Iterator[tuple[str, re.Match[str]]]:
    """Memory-efficient iterator for hardcoded value matches.

    Yields (category, match) tuples for each finding.

    Args:
        text: The source code text to analyze
        categories: Optional list of categories to check

    Yields:
        Tuples of (category_name, match_object)
    """
    patterns_to_check = HARDCODED_PATTERNS
    if categories:
        patterns_to_check = {k: v for k, v in HARDCODED_PATTERNS.items() if k in categories}

    for category, pattern in patterns_to_check.items():
        for match in pattern.finditer(text):
            yield category, match
