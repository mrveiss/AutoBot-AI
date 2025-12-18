# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Analysis Types and Data Classes

Issue #381: Extracted from performance_analyzer.py god class refactoring.
Contains core data structures for performance analysis.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class PerformanceSeverity(Enum):
    """Severity levels for performance issues."""

    INFO = "info"  # Minor optimization opportunity
    LOW = "low"  # Small performance impact
    MEDIUM = "medium"  # Moderate performance impact
    HIGH = "high"  # Significant performance impact
    CRITICAL = "critical"  # Severe bottleneck


class PerformanceIssueType(Enum):
    """Types of performance issues detected."""

    # Query patterns
    N_PLUS_ONE_QUERY = "n_plus_one_query"
    QUERY_IN_LOOP = "query_in_loop"
    MISSING_INDEX_HINT = "missing_index_hint"
    UNBATCHED_INSERTS = "unbatched_inserts"

    # Loop complexity
    NESTED_LOOP_COMPLEXITY = "nested_loop_complexity"
    INEFFICIENT_LOOP = "inefficient_loop"
    LOOP_INVARIANT_COMPUTATION = "loop_invariant_computation"
    QUADRATIC_COMPLEXITY = "quadratic_complexity"

    # Async/sync issues
    SYNC_IN_ASYNC = "sync_in_async"
    BLOCKING_IO_IN_ASYNC = "blocking_io_in_async"
    MISSING_AWAIT = "missing_await"
    SEQUENTIAL_AWAITS = "sequential_awaits"

    # Memory patterns
    UNBOUNDED_COLLECTION = "unbounded_collection"
    LARGE_OBJECT_CREATION = "large_object_creation"
    MEMORY_LEAK_RISK = "memory_leak_risk"
    EXCESSIVE_STRING_CONCAT = "excessive_string_concat"

    # Cache patterns
    REPEATED_COMPUTATION = "repeated_computation"
    MISSING_CACHE = "missing_cache"
    CACHE_STAMPEDE_RISK = "cache_stampede_risk"
    INEFFICIENT_CACHE_KEY = "inefficient_cache_key"

    # Data structure issues
    LIST_FOR_LOOKUP = "list_for_lookup"
    INEFFICIENT_DICT_ACCESS = "inefficient_dict_access"
    REPEATED_LIST_APPEND = "repeated_list_append"

    # I/O patterns
    REPEATED_FILE_OPEN = "repeated_file_open"
    MISSING_CONTEXT_MANAGER = "missing_context_manager"
    INEFFICIENT_FILE_READ = "inefficient_file_read"

    # Network patterns
    UNBATCHED_API_CALLS = "unbatched_api_calls"
    MISSING_CONNECTION_POOL = "missing_connection_pool"
    REPEATED_HTTP_REQUESTS = "repeated_http_requests"


# Complexity estimation for Big-O notation
COMPLEXITY_LEVELS = {
    1: "O(1)",
    2: "O(n)",
    3: "O(n²)",
    4: "O(n³)",
    5: "O(n⁴+)",
}


@dataclass
class PerformanceIssue:
    """Result of performance analysis for a single finding."""

    issue_type: PerformanceIssueType
    severity: PerformanceSeverity
    file_path: str
    line_start: int
    line_end: int
    description: str
    recommendation: str
    estimated_complexity: str
    estimated_impact: str
    current_code: str = ""
    optimized_code: str = ""
    confidence: float = 1.0
    # Issue #385: Flag potential false positives for user review
    potential_false_positive: bool = False
    false_positive_reason: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "issue_type": self.issue_type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "description": self.description,
            "recommendation": self.recommendation,
            "estimated_complexity": self.estimated_complexity,
            "estimated_impact": self.estimated_impact,
            "current_code": self.current_code,
            "optimized_code": self.optimized_code,
            "confidence": self.confidence,
            "potential_false_positive": self.potential_false_positive,
            "false_positive_reason": self.false_positive_reason,
            "metrics": self.metrics,
        }
