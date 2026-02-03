# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Issue Detector Module

Detects architectural issues, calculates metrics, and generates recommendations.
Extracted from ArchitecturalPatternAnalyzer as part of Issue #394.
"""

import logging
from typing import Any, Dict, List

from .types import ArchitecturalComponent, ArchitecturalIssue, ArchitecturalMetrics
from .dependency_analyzer import DependencyAnalyzer

logger = logging.getLogger(__name__)


class IssueDetector:
    """
    Detector for architectural issues and metrics calculator.

    Identifies issues like god classes, tight coupling, and circular dependencies.

    Example:
        >>> detector = IssueDetector()
        >>> issues = await detector.identify_issues(components, dependencies)
    """

    # Thresholds for issue detection
    GOD_CLASS_COMPLEXITY_THRESHOLD = 50
    HIGH_COUPLING_THRESHOLD = 10
    LOW_COHESION_THRESHOLD = 0.3

    def __init__(self, dependency_analyzer: DependencyAnalyzer = None):
        """
        Initialize the issue detector.

        Args:
            dependency_analyzer: Dependency analyzer instance for circular detection
        """
        self._deps = dependency_analyzer or DependencyAnalyzer()

    async def identify_issues(
        self,
        components: List[ArchitecturalComponent],
        dependencies: Dict[str, List[str]],
    ) -> List[ArchitecturalIssue]:
        """
        Identify architectural issues and anti-patterns.

        Args:
            components: List of architectural components
            dependencies: Component dependency mapping

        Returns:
            List of identified ArchitecturalIssue objects
        """
        issues = []

        # Identify God classes
        god_classes = [
            c
            for c in components
            if c.component_type == "class"
            and c.complexity_score > self.GOD_CLASS_COMPLEXITY_THRESHOLD
        ]
        if god_classes:
            issues.append(
                ArchitecturalIssue(
                    issue_type="god_class",
                    severity="high",
                    description=f"Found {len(god_classes)} potential God classes with high complexity",
                    affected_components=god_classes,
                    suggestion="Break down large classes into smaller, more focused classes",
                    refactoring_effort="high",
                    pattern_violation="Single Responsibility Principle",
                )
            )

        # Identify high coupling
        high_coupling = [
            c for c in components if c.coupling_score > self.HIGH_COUPLING_THRESHOLD
        ]
        if high_coupling:
            issues.append(
                ArchitecturalIssue(
                    issue_type="tight_coupling",
                    severity="medium",
                    description=f"Found {len(high_coupling)} components with high coupling",
                    affected_components=high_coupling,
                    suggestion="Reduce dependencies through dependency injection or interfaces",
                    refactoring_effort="medium",
                    pattern_violation="Dependency Inversion Principle",
                )
            )

        # Identify low cohesion
        low_cohesion = [
            c
            for c in components
            if c.component_type == "class"
            and c.cohesion_score < self.LOW_COHESION_THRESHOLD
        ]
        if low_cohesion:
            issues.append(
                ArchitecturalIssue(
                    issue_type="low_cohesion",
                    severity="medium",
                    description=f"Found {len(low_cohesion)} classes with low cohesion",
                    affected_components=low_cohesion,
                    suggestion="Reorganize class methods to increase internal relatedness",
                    refactoring_effort="medium",
                    pattern_violation="Single Responsibility Principle",
                )
            )

        # Check for circular dependencies
        circular_deps = self._deps.detect_circular_dependencies(dependencies)
        if circular_deps:
            affected = [c for c in components if c.name in circular_deps]
            issues.append(
                ArchitecturalIssue(
                    issue_type="circular_dependency",
                    severity="high",
                    description=f"Found circular dependencies between {len(circular_deps)} components",
                    affected_components=affected,
                    suggestion="Break circular dependencies using interfaces or dependency injection",
                    refactoring_effort="high",
                    pattern_violation="Acyclic Dependencies Principle",
                )
            )

        return issues

    def calculate_metrics(
        self,
        components: List[ArchitecturalComponent],
        issues: List[ArchitecturalIssue],
    ) -> ArchitecturalMetrics:
        """
        Calculate architectural quality metrics.

        Args:
            components: List of architectural components
            issues: List of identified issues

        Returns:
            ArchitecturalMetrics with calculated values
        """
        if not components:
            return ArchitecturalMetrics()

        # Average coupling
        avg_coupling = sum(c.coupling_score for c in components) / len(components)
        coupling_score = max(0, 100 - (avg_coupling * 5))  # Lower coupling is better

        # Average cohesion
        class_components = [c for c in components if c.component_type == "class"]
        avg_cohesion = (
            sum(c.cohesion_score for c in class_components) / len(class_components)
            if class_components
            else 0
        )
        cohesion_score = avg_cohesion * 100

        # Pattern adherence (fewer issues = better adherence)
        critical_issues = len([i for i in issues if i.severity == "critical"])
        high_issues = len([i for i in issues if i.severity == "high"])
        pattern_adherence = max(0, 100 - (critical_issues * 20 + high_issues * 10))

        # Maintainability index (simplified)
        avg_complexity = sum(c.complexity_score for c in components) / len(components)
        maintainability = max(0, 100 - (avg_complexity * 2))

        # Abstraction score (ratio of abstract to concrete classes)
        abstract_classes = len(
            [c for c in components if c.component_type == "class" and c.is_abstract]
        )
        total_classes = len([c for c in components if c.component_type == "class"])
        abstraction_score = (
            (abstract_classes / total_classes * 100) if total_classes > 0 else 0
        )

        # Instability score (simplified calculation)
        instability_score = min(100, avg_coupling * 10)

        # Overall architecture score (weighted average)
        architecture_score = (
            coupling_score * 0.25
            + cohesion_score * 0.25
            + pattern_adherence * 0.3
            + maintainability * 0.2
        )

        return ArchitecturalMetrics(
            total_components=len(components),
            architecture_score=round(architecture_score, 2),
            coupling_score=round(coupling_score, 2),
            cohesion_score=round(cohesion_score, 2),
            pattern_adherence_score=round(pattern_adherence, 2),
            maintainability_index=round(maintainability, 2),
            abstraction_score=round(abstraction_score, 2),
            instability_score=round(instability_score, 2),
        )

    async def generate_recommendations(
        self, issues: List[ArchitecturalIssue]
    ) -> List[str]:
        """
        Generate architectural improvement recommendations.

        Args:
            issues: List of identified issues

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Group by issue type
        by_type: Dict[str, List[ArchitecturalIssue]] = {}
        for issue in issues:
            if issue.issue_type not in by_type:
                by_type[issue.issue_type] = []
            by_type[issue.issue_type].append(issue)

        # Generate specific recommendations
        if "god_class" in by_type:
            recommendations.append(
                "Break down God classes using Single Responsibility Principle"
            )

        if "tight_coupling" in by_type:
            recommendations.append(
                "Reduce coupling through dependency injection and interface segregation"
            )

        if "low_cohesion" in by_type:
            recommendations.append(
                "Increase cohesion by grouping related functionality together"
            )

        if "circular_dependency" in by_type:
            recommendations.append(
                "Eliminate circular dependencies using dependency inversion"
            )

        # General recommendations
        recommendations.extend(
            [
                "Apply SOLID principles consistently across the codebase",
                "Use design patterns appropriately to solve common problems",
                "Implement proper layered architecture with clear boundaries",
                "Add architectural tests to enforce design constraints",
            ]
        )

        return recommendations


__all__ = ["IssueDetector"]
