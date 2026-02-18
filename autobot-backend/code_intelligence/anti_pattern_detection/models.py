# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Detection Data Models

Contains dataclasses for anti-pattern detection results and analysis reports.

Part of Issue #381 - God Class Refactoring
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .types import AntiPatternSeverity, AntiPatternType


@dataclass
class AntiPatternResult:
    """Result of anti-pattern detection for a single finding."""

    pattern_type: AntiPatternType
    severity: AntiPatternSeverity
    file_path: str
    line_number: int
    entity_name: str
    description: str
    suggestion: str
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pattern_type": self.pattern_type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "entity_name": self.entity_name,
            "description": self.description,
            "suggestion": self.suggestion,
            "metrics": self.metrics,
        }


@dataclass
class AnalysisReport:
    """Complete analysis report for a codebase scan."""

    scan_path: str
    total_files: int
    total_classes: int
    total_functions: int
    anti_patterns: List[AntiPatternResult]
    summary: Dict[str, int]
    severity_distribution: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scan_path": self.scan_path,
            "total_files": self.total_files,
            "total_classes": self.total_classes,
            "total_functions": self.total_functions,
            "anti_patterns": [p.to_dict() for p in self.anti_patterns],
            "summary": self.summary,
            "severity_distribution": self.severity_distribution,
            "total_issues": len(self.anti_patterns),
        }

    @property
    def has_critical_issues(self) -> bool:
        """Check if report contains any critical severity issues."""
        return any(
            p.severity == AntiPatternSeverity.CRITICAL for p in self.anti_patterns
        )

    @property
    def has_high_issues(self) -> bool:
        """Check if report contains any high severity issues."""
        return any(
            p.severity in (AntiPatternSeverity.CRITICAL, AntiPatternSeverity.HIGH)
            for p in self.anti_patterns
        )

    def filter_by_severity(
        self, min_severity: AntiPatternSeverity
    ) -> List[AntiPatternResult]:
        """Filter anti-patterns by minimum severity level."""
        severity_order = [
            AntiPatternSeverity.INFO,
            AntiPatternSeverity.LOW,
            AntiPatternSeverity.MEDIUM,
            AntiPatternSeverity.HIGH,
            AntiPatternSeverity.CRITICAL,
        ]
        min_index = severity_order.index(min_severity)
        return [
            p
            for p in self.anti_patterns
            if severity_order.index(p.severity) >= min_index
        ]

    def filter_by_type(
        self, pattern_types: List[AntiPatternType]
    ) -> List[AntiPatternResult]:
        """Filter anti-patterns by type."""
        type_set = set(pattern_types)
        return [p for p in self.anti_patterns if p.pattern_type in type_set]

    def get_by_file(self, file_path: str) -> List[AntiPatternResult]:
        """Get all anti-patterns for a specific file."""
        return [p for p in self.anti_patterns if p.file_path == file_path]


@dataclass
class ClassInfo:
    """Information about an analyzed class."""

    name: str
    file_path: str
    line_number: int
    method_count: int
    line_count: int
    attribute_count: int = 0
    base_classes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "method_count": self.method_count,
            "line_count": self.line_count,
            "attribute_count": self.attribute_count,
            "base_classes": self.base_classes,
        }


@dataclass
class FunctionInfo:
    """Information about an analyzed function."""

    name: str
    file_path: str
    line_number: int
    parameter_count: int
    line_count: int
    nesting_depth: int = 0
    is_async: bool = False
    class_name: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "parameter_count": self.parameter_count,
            "line_count": self.line_count,
            "nesting_depth": self.nesting_depth,
            "is_async": self.is_async,
            "class_name": self.class_name,
        }

    @property
    def full_name(self) -> str:
        """Get fully qualified name including class if applicable."""
        if self.class_name:
            return f"{self.class_name}.{self.name}"
        return self.name


@dataclass
class ImportInfo:
    """Information about imports in a file."""

    file_path: str
    module: str
    imported_names: List[str] = field(default_factory=list)
    is_from_import: bool = False
    line_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "module": self.module,
            "imported_names": self.imported_names,
            "is_from_import": self.is_from_import,
            "line_number": self.line_number,
        }
