# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Architectural Analysis Package

This package contains the architectural pattern analyzer system for analyzing
codebase architecture, design patterns, and structural quality.

Package Structure:
- types.py: Data classes (ArchitecturalComponent, ArchitecturalIssue, ArchitecturalMetrics)
- component_discovery.py: Component discovery and extraction
- dependency_analyzer.py: Dependency extraction and analysis
- cohesion_calculator.py: Cohesion calculation
- complexity_calculator.py: Complexity calculation
- pattern_detector.py: Design pattern detection
- issue_detector.py: Architectural issue detection and recommendations

Part of Issue #394 god class refactoring initiative.
"""

from .types import (
    ArchitecturalComponent,
    ArchitecturalIssue,
    ArchitecturalMetrics,
)
from .component_discovery import ComponentDiscovery
from .dependency_analyzer import DependencyAnalyzer
from .cohesion_calculator import CohesionCalculator
from .complexity_calculator import ComplexityCalculator
from .pattern_detector import PatternDetector
from .issue_detector import IssueDetector

__all__ = [
    # Data classes
    "ArchitecturalComponent",
    "ArchitecturalIssue",
    "ArchitecturalMetrics",
    # Analyzer classes
    "ComponentDiscovery",
    "DependencyAnalyzer",
    "CohesionCalculator",
    "ComplexityCalculator",
    "PatternDetector",
    "IssueDetector",
]
