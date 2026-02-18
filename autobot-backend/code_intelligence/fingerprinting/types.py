# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Fingerprinting Types Module

Contains enums and data classes for the code fingerprinting system.
Extracted from code_fingerprinting.py as part of Issue #381 refactoring.
"""

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# Enums and Constants
# =============================================================================


class CloneType(Enum):
    """Classification of code clone types."""

    TYPE_1 = "type_1"  # Exact clones (identical code)
    TYPE_2 = "type_2"  # Renamed clones (variable/function names changed)
    TYPE_3 = "type_3"  # Near-miss clones (statements modified)
    TYPE_4 = "type_4"  # Semantic clones (functionally equivalent)


class FingerprintType(Enum):
    """Types of fingerprints generated."""

    AST_STRUCTURAL = "ast_structural"  # Based on AST structure
    AST_NORMALIZED = "ast_normalized"  # Normalized identifiers
    SEMANTIC = "semantic"  # Based on data/control flow
    TOKEN_SEQUENCE = "token_sequence"  # Based on token patterns


class CloneSeverity(Enum):
    """Severity levels for detected clones."""

    INFO = "info"  # Single occurrence, just documentation
    LOW = "low"  # 2-3 occurrences, minor duplication
    MEDIUM = "medium"  # 4-6 occurrences, should be refactored
    HIGH = "high"  # 7+ occurrences, significant technical debt
    CRITICAL = "critical"  # Large clones, urgent refactoring needed


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CodeFragment:
    """Represents a code fragment that can be fingerprinted."""

    file_path: str
    start_line: int
    end_line: int
    source_code: str
    ast_node: Optional[ast.AST] = None
    fragment_type: str = "unknown"  # function, class, block, etc.
    entity_name: str = ""

    def __hash__(self) -> int:
        """
        Generate hash for use in sets and dictionaries.

        Returns:
            Hash value based on file path and line numbers
        """
        return hash((self.file_path, self.start_line, self.end_line))

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another CodeFragment.

        Args:
            other: Object to compare with

        Returns:
            True if fragments have same file path and line range
        """
        if not isinstance(other, CodeFragment):
            return False
        return (
            self.file_path == other.file_path
            and self.start_line == other.start_line
            and self.end_line == other.end_line
        )

    @property
    def line_count(self) -> int:
        """Get the number of lines in this fragment."""
        return self.end_line - self.start_line + 1


@dataclass
class Fingerprint:
    """A fingerprint representing code structure or semantics."""

    hash_value: str
    fingerprint_type: FingerprintType
    fragment: CodeFragment
    normalized_tokens: List[str] = field(default_factory=list)
    structural_features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hash_value": self.hash_value,
            "fingerprint_type": self.fingerprint_type.value,
            "file_path": self.fragment.file_path,
            "start_line": self.fragment.start_line,
            "end_line": self.fragment.end_line,
            "entity_name": self.fragment.entity_name,
            "line_count": self.fragment.line_count,
            "structural_features": self.structural_features,
        }


@dataclass
class CloneInstance:
    """Represents a single instance of a clone."""

    fragment: CodeFragment
    fingerprint: Fingerprint
    similarity_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.fragment.file_path,
            "start_line": self.fragment.start_line,
            "end_line": self.fragment.end_line,
            "entity_name": self.fragment.entity_name,
            "line_count": self.fragment.line_count,
            "similarity_score": self.similarity_score,
            "source_preview": self._get_source_preview(),
        }

    def _get_source_preview(self, max_lines: int = 5) -> str:
        """
        Get a preview of the source code.

        Args:
            max_lines: Maximum number of lines to include in preview

        Returns:
            Source code preview with ellipsis if truncated
        """
        lines = self.fragment.source_code.split("\n")[:max_lines]
        if len(self.fragment.source_code.split("\n")) > max_lines:
            lines.append("...")
        return "\n".join(lines)


@dataclass
class CloneGroup:
    """A group of code fragments that are clones of each other."""

    clone_type: CloneType
    severity: CloneSeverity
    instances: List[CloneInstance]
    canonical_fingerprint: str
    similarity_range: Tuple[float, float]  # (min, max) similarity
    total_duplicated_lines: int
    refactoring_suggestion: str = ""
    estimated_effort: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "clone_type": self.clone_type.value,
            "severity": self.severity.value,
            "instance_count": len(self.instances),
            "instances": [i.to_dict() for i in self.instances],
            "canonical_fingerprint": self.canonical_fingerprint,
            "similarity_range": {
                "min": self.similarity_range[0],
                "max": self.similarity_range[1],
            },
            "total_duplicated_lines": self.total_duplicated_lines,
            "refactoring_suggestion": self.refactoring_suggestion,
            "estimated_effort": self.estimated_effort,
        }


@dataclass
class CloneDetectionReport:
    """Complete report of clone detection analysis."""

    scan_path: str
    total_files: int
    total_fragments: int
    clone_groups: List[CloneGroup]
    clone_type_distribution: Dict[str, int]
    severity_distribution: Dict[str, int]
    total_duplicated_lines: int
    duplication_percentage: float
    top_cloned_files: List[Dict[str, Any]]
    refactoring_priorities: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scan_path": self.scan_path,
            "total_files": self.total_files,
            "total_fragments": self.total_fragments,
            "total_clone_groups": len(self.clone_groups),
            "clone_groups": [g.to_dict() for g in self.clone_groups],
            "clone_type_distribution": self.clone_type_distribution,
            "severity_distribution": self.severity_distribution,
            "total_duplicated_lines": self.total_duplicated_lines,
            "duplication_percentage": round(self.duplication_percentage, 2),
            "top_cloned_files": self.top_cloned_files,
            "refactoring_priorities": self.refactoring_priorities,
        }
