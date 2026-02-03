# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Architectural Pattern Analyzer using Redis and NPU acceleration

Analyzes codebase for architectural patterns, design issues, and structural improvements.

Refactoring History:
- Issue #394: Extracted to architectural_analysis package
  Reduced from 46 methods to 7 methods (85% reduction)
  Extracted: ComponentDiscovery, DependencyAnalyzer, CohesionCalculator,
  ComplexityCalculator, PatternDetector, IssueDetector
"""

import json
import logging
import time
from typing import Any, Dict, List

from src.utils.redis_client import get_redis_client
from src.config import UnifiedConfig

# Issue #394: Import from architectural_analysis package
from .architectural_analysis import (
    ArchitecturalComponent,
    ArchitecturalIssue,
    ArchitecturalMetrics,
    ComponentDiscovery,
    DependencyAnalyzer,
    IssueDetector,
    PatternDetector,
)

# Initialize unified config
config = UnifiedConfig()
logger = logging.getLogger(__name__)


class ArchitecturalPatternAnalyzer:
    """
    Analyzes architectural patterns and design quality.

    Issue #394: This class was refactored from 46 methods to 7 methods (85%
    reduction) by extracting ComponentDiscovery, DependencyAnalyzer,
    CohesionCalculator, ComplexityCalculator, PatternDetector, and
    IssueDetector into separate classes in the architectural_analysis package.

    Example:
        >>> analyzer = ArchitecturalPatternAnalyzer()
        >>> results = await analyzer.analyze_architecture(".", ["**/*.py"])
    """

    def __init__(self, redis_client=None):
        """
        Initialize the architectural pattern analyzer.

        Args:
            redis_client: Optional Redis client for caching
        """
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config

        # Caching keys
        self.ARCHITECTURE_KEY = "architecture_analysis:components"
        self.ISSUES_KEY = "architecture_analysis:issues"

        # Issue #394: Delegate to extracted classes
        self._component_discovery = ComponentDiscovery()
        self._dependency_analyzer = DependencyAnalyzer()
        self._pattern_detector = PatternDetector()
        self._issue_detector = IssueDetector(self._dependency_analyzer)

        logger.info("Architectural Pattern Analyzer initialized")

    async def analyze_architecture(
        self, root_path: str = ".", patterns: List[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze architectural patterns and design quality.

        Args:
            root_path: Root directory to analyze
            patterns: Glob patterns for files to include

        Returns:
            Dictionary containing analysis results
        """
        start_time = time.time()
        patterns = patterns or ["**/*.py"]

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Analyzing architectural patterns in {root_path}")

        # Discover architectural components
        logger.info("Discovering architectural components")
        components = await self._component_discovery.discover_components(
            root_path, patterns
        )
        logger.info(f"Found {len(components)} architectural components")

        # Analyze dependencies and relationships
        logger.info("Analyzing dependencies and relationships")
        dependencies = await self._analyze_dependencies(components)

        # Detect design patterns
        logger.info("Detecting design patterns")
        detected_patterns = await self._pattern_detector.detect_patterns(
            root_path, patterns, self._component_discovery._should_skip_file
        )

        # Identify architectural issues
        logger.info("Identifying architectural issues")
        issues = await self._issue_detector.identify_issues(components, dependencies)

        # Calculate architectural metrics
        metrics = self._issue_detector.calculate_metrics(components, issues)

        # Generate improvement recommendations
        recommendations = await self._issue_detector.generate_recommendations(issues)

        analysis_time = time.time() - start_time

        results = {
            "total_components": len(components),
            "architectural_issues": len(issues),
            "design_patterns_found": len(detected_patterns),
            "architecture_score": metrics.architecture_score,
            "analysis_time_seconds": analysis_time,
            "components": [c.to_dict() for c in components],
            "architectural_issues": [issue.to_dict() for issue in issues],
            "detected_patterns": detected_patterns,
            "recommendations": recommendations,
            "metrics": metrics.to_dict(),
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Architectural analysis complete in {analysis_time:.2f}s")
        return results

    async def _analyze_dependencies(
        self, components: List[ArchitecturalComponent]
    ) -> Dict[str, List[str]]:
        """Analyze dependencies between components."""
        return {component.name: component.dependencies for component in components}

    async def _cache_results(self, results: Dict[str, Any]) -> None:
        """Cache analysis results in Redis."""
        if self.redis_client:
            try:
                key = self.ARCHITECTURE_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, 3600, value)
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self) -> None:
        """Clear analysis cache."""
        if self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match="architecture_analysis:*", count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")


# Re-export types for backward compatibility
__all__ = [
    "ArchitecturalPatternAnalyzer",
    "ArchitecturalComponent",
    "ArchitecturalIssue",
    "ArchitecturalMetrics",
]


async def main():
    """Example usage of architectural pattern analyzer."""
    analyzer = ArchitecturalPatternAnalyzer()

    # Analyze architectural patterns
    results = await analyzer.analyze_architecture(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    # Print summary
    print("\n=== Architectural Pattern Analysis Results ===")
    print(f"Total components: {results['total_components']}")
    print(f"Architectural issues: {results['architectural_issues']}")
    print(f"Design patterns found: {results['design_patterns_found']}")
    print(f"Architecture score: {results['architecture_score']}/100")
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")

    # Print detailed metrics
    metrics = results["metrics"]
    print("\n=== Architectural Metrics ===")
    print(f"Coupling score: {metrics['coupling_score']}/100 (lower is better)")
    print(f"Cohesion score: {metrics['cohesion_score']}/100")
    print(f"Pattern adherence: {metrics['pattern_adherence_score']}/100")
    print(f"Maintainability index: {metrics['maintainability_index']}/100")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
