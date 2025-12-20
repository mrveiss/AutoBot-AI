# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Architectural Analysis Types

Data classes for architectural analysis results.
Extracted from ArchitecturalPatternAnalyzer as part of Issue #394.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ArchitecturalComponent:
    """Represents an architectural component in the codebase."""

    file_path: str
    component_type: str  # class, module, function, service
    name: str
    line_number: int
    dependencies: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    is_abstract: bool = False
    coupling_score: int = 0  # Number of dependencies
    cohesion_score: float = 0.0  # Internal relationship strength
    complexity_score: int = 0
    patterns: List[str] = field(default_factory=list)  # Detected patterns

    def to_dict(self) -> dict:
        """Serialize component to dictionary."""
        return {
            "file_path": self.file_path,
            "component_type": self.component_type,
            "name": self.name,
            "line_number": self.line_number,
            "dependencies": self.dependencies,
            "interfaces": self.interfaces,
            "is_abstract": self.is_abstract,
            "coupling_score": self.coupling_score,
            "cohesion_score": self.cohesion_score,
            "complexity_score": self.complexity_score,
            "patterns": self.patterns,
        }


@dataclass
class ArchitecturalIssue:
    """Represents an architectural issue or anti-pattern."""

    issue_type: str  # tight_coupling, god_class, circular_dependency, etc.
    severity: str  # critical, high, medium, low
    description: str
    affected_components: List[ArchitecturalComponent] = field(default_factory=list)
    suggestion: str = ""
    refactoring_effort: str = "medium"  # low, medium, high
    pattern_violation: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize issue to dictionary."""
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "affected_components": [c.name for c in self.affected_components],
            "suggestion": self.suggestion,
            "refactoring_effort": self.refactoring_effort,
            "pattern_violation": self.pattern_violation,
        }


@dataclass
class ArchitecturalMetrics:
    """Architectural quality metrics."""

    total_components: int = 0
    architecture_score: float = 0.0  # 0-100
    coupling_score: float = 0.0
    cohesion_score: float = 0.0
    pattern_adherence_score: float = 0.0
    maintainability_index: float = 0.0
    abstraction_score: float = 0.0
    instability_score: float = 0.0

    def to_dict(self) -> dict:
        """Serialize metrics to dictionary."""
        return {
            "total_components": self.total_components,
            "architecture_score": self.architecture_score,
            "coupling_score": self.coupling_score,
            "cohesion_score": self.cohesion_score,
            "pattern_adherence_score": self.pattern_adherence_score,
            "maintainability_index": self.maintainability_index,
            "abstraction_score": self.abstraction_score,
            "instability_score": self.instability_score,
        }


__all__ = [
    "ArchitecturalComponent",
    "ArchitecturalIssue",
    "ArchitecturalMetrics",
]
