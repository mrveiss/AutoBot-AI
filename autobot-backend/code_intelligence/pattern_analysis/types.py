# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Type definitions for Code Pattern Analysis.

Issue #208: Data classes and enums for pattern detection system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PatternType(Enum):
    """Types of code patterns that can be detected."""

    DUPLICATE_CODE = "duplicate_code"
    SIMILAR_LOGIC = "similar_logic"
    REGEX_OPPORTUNITY = "regex_opportunity"
    MODULARIZATION = "modularization"
    COMPLEXITY_HOTSPOT = "complexity_hotspot"
    DEAD_CODE = "dead_code"
    COUPLING_ISSUE = "coupling_issue"
    ERROR_HANDLING = "error_handling"
    VALIDATION_LOGIC = "validation_logic"
    DATA_TRANSFORMATION = "data_transformation"


class PatternSeverity(Enum):
    """Severity levels for pattern analysis findings."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CodeLocation:
    """Represents a location in the codebase."""

    file_path: str
    start_line: int
    end_line: int
    function_name: Optional[str] = None
    class_name: Optional[str] = None

    @property
    def line_count(self) -> int:
        """Number of lines in this location."""
        return self.end_line - self.start_line + 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "function_name": self.function_name,
            "class_name": self.class_name,
            "line_count": self.line_count,
        }

    def __str__(self) -> str:
        """Human-readable location string."""
        loc = f"{self.file_path}:{self.start_line}"
        if self.function_name:
            loc += f" ({self.function_name})"
        return loc


@dataclass
class CodePattern:
    """Base class for detected code patterns."""

    pattern_type: PatternType
    severity: PatternSeverity
    description: str
    locations: List[CodeLocation]
    suggestion: str
    confidence: float = 0.0  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.now)

    @property
    def occurrence_count(self) -> int:
        """Number of occurrences of this pattern."""
        return len(self.locations)

    @property
    def total_lines(self) -> int:
        """Total lines affected by this pattern."""
        return sum(loc.line_count for loc in self.locations)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pattern_type": self.pattern_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "locations": [loc.to_dict() for loc in self.locations],
            "suggestion": self.suggestion,
            "confidence": self.confidence,
            "occurrence_count": self.occurrence_count,
            "total_lines": self.total_lines,
            "metadata": self.metadata,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class DuplicatePattern(CodePattern):
    """Represents duplicated code pattern."""

    similarity_score: float = 1.0
    canonical_code: str = ""
    code_reduction_potential: int = 0  # Lines that can be saved

    def __post_init__(self):
        """Set pattern type after initialization."""
        self.pattern_type = PatternType.DUPLICATE_CODE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with duplicate-specific fields."""
        base = super().to_dict()
        base.update(
            {
                "similarity_score": self.similarity_score,
                "canonical_code": self.canonical_code[:500]
                if self.canonical_code
                else "",
                "code_reduction_potential": self.code_reduction_potential,
            }
        )
        return base


@dataclass
class RegexOpportunity(CodePattern):
    """Represents an opportunity to replace string operations with regex."""

    current_code: str = ""
    suggested_regex: str = ""
    performance_gain: str = ""
    operations_replaced: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Set pattern type after initialization."""
        self.pattern_type = PatternType.REGEX_OPPORTUNITY

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with regex-specific fields."""
        base = super().to_dict()
        base.update(
            {
                "current_code": self.current_code[:500] if self.current_code else "",
                "suggested_regex": self.suggested_regex,
                "performance_gain": self.performance_gain,
                "operations_replaced": self.operations_replaced,
            }
        )
        return base


@dataclass
class ModularizationSuggestion(CodePattern):
    """Represents an opportunity to modularize repeated patterns."""

    pattern_name: str = ""
    repeated_in_files: List[str] = field(default_factory=list)
    suggested_module: str = ""
    suggested_interface: str = ""
    benefits: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Set pattern type after initialization."""
        self.pattern_type = PatternType.MODULARIZATION

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with modularization-specific fields."""
        base = super().to_dict()
        base.update(
            {
                "pattern_name": self.pattern_name,
                "repeated_in_files": self.repeated_in_files,
                "suggested_module": self.suggested_module,
                "suggested_interface": self.suggested_interface,
                "benefits": self.benefits,
            }
        )
        return base


@dataclass
class ComplexityHotspot(CodePattern):
    """Represents a complexity hotspot that needs simplification."""

    cyclomatic_complexity: int = 0
    maintainability_index: float = 0.0
    cognitive_complexity: int = 0
    halstead_difficulty: float = 0.0
    nesting_depth: int = 0
    simplification_suggestions: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Set pattern type after initialization."""
        self.pattern_type = PatternType.COMPLEXITY_HOTSPOT

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with complexity-specific fields."""
        base = super().to_dict()
        base.update(
            {
                "cyclomatic_complexity": self.cyclomatic_complexity,
                "maintainability_index": self.maintainability_index,
                "cognitive_complexity": self.cognitive_complexity,
                "halstead_difficulty": self.halstead_difficulty,
                "nesting_depth": self.nesting_depth,
                "simplification_suggestions": self.simplification_suggestions,
            }
        )
        return base


@dataclass
class PatternCluster:
    """Group of related patterns for analysis."""

    cluster_id: str
    pattern_type: PatternType
    patterns: List[CodePattern]
    representative_code: str = ""
    embedding_centroid: Optional[List[float]] = None

    @property
    def size(self) -> int:
        """Number of patterns in this cluster."""
        return len(self.patterns)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "pattern_type": self.pattern_type.value,
            "size": self.size,
            "patterns": [p.to_dict() for p in self.patterns],
            "representative_code": self.representative_code[:500]
            if self.representative_code
            else "",
        }


@dataclass
class PatternAnalysisReport:
    """Complete report from pattern analysis."""

    scan_path: str
    analysis_timestamp: datetime = field(default_factory=datetime.now)
    total_files_analyzed: int = 0
    total_lines_analyzed: int = 0
    analysis_duration_seconds: float = 0.0

    # Pattern findings
    duplicate_patterns: List[DuplicatePattern] = field(default_factory=list)
    regex_opportunities: List[RegexOpportunity] = field(default_factory=list)
    modularization_suggestions: List[ModularizationSuggestion] = field(
        default_factory=list
    )
    complexity_hotspots: List[ComplexityHotspot] = field(default_factory=list)
    other_patterns: List[CodePattern] = field(default_factory=list)

    # Metrics
    pattern_counts: Dict[str, int] = field(default_factory=dict)
    severity_distribution: Dict[str, int] = field(default_factory=dict)
    potential_loc_reduction: int = 0
    complexity_score: str = ""  # Letter grade (A, B+, etc.)

    # Clusters
    pattern_clusters: List[PatternCluster] = field(default_factory=list)

    @property
    def total_patterns(self) -> int:
        """Total number of patterns found."""
        return (
            len(self.duplicate_patterns)
            + len(self.regex_opportunities)
            + len(self.modularization_suggestions)
            + len(self.complexity_hotspots)
            + len(self.other_patterns)
        )

    def calculate_metrics(self) -> None:
        """Calculate aggregate metrics from patterns."""
        # Pattern counts
        self.pattern_counts = {
            "duplicates": len(self.duplicate_patterns),
            "regex_opportunities": len(self.regex_opportunities),
            "modularization": len(self.modularization_suggestions),
            "complexity_hotspots": len(self.complexity_hotspots),
            "other": len(self.other_patterns),
        }

        # Severity distribution
        all_patterns = (
            self.duplicate_patterns
            + self.regex_opportunities
            + self.modularization_suggestions
            + self.complexity_hotspots
            + self.other_patterns
        )
        self.severity_distribution = {}
        for pattern in all_patterns:
            severity = pattern.severity.value
            self.severity_distribution[severity] = (
                self.severity_distribution.get(severity, 0) + 1
            )

        # LOC reduction potential
        self.potential_loc_reduction = sum(
            dp.code_reduction_potential for dp in self.duplicate_patterns
        )

        # Complexity score calculation
        if self.complexity_hotspots:
            avg_complexity = sum(
                h.cyclomatic_complexity for h in self.complexity_hotspots
            ) / len(self.complexity_hotspots)
            if avg_complexity <= 5:
                self.complexity_score = "A"
            elif avg_complexity <= 10:
                self.complexity_score = "B+"
            elif avg_complexity <= 15:
                self.complexity_score = "B"
            elif avg_complexity <= 20:
                self.complexity_score = "C"
            else:
                self.complexity_score = "D"
        else:
            self.complexity_score = "A"  # No complexity issues found

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        self.calculate_metrics()
        return {
            "analysis_summary": {
                "scan_path": self.scan_path,
                "timestamp": self.analysis_timestamp.isoformat(),
                "files_analyzed": self.total_files_analyzed,
                "lines_analyzed": self.total_lines_analyzed,
                "duration_seconds": self.analysis_duration_seconds,
                "total_patterns_found": self.total_patterns,
                "potential_loc_reduction": self.potential_loc_reduction,
                "complexity_score": self.complexity_score,
            },
            "pattern_counts": self.pattern_counts,
            "severity_distribution": self.severity_distribution,
            "duplicate_patterns": [p.to_dict() for p in self.duplicate_patterns],
            "regex_opportunities": [p.to_dict() for p in self.regex_opportunities],
            "modularization_suggestions": [
                p.to_dict() for p in self.modularization_suggestions
            ],
            "complexity_hotspots": [p.to_dict() for p in self.complexity_hotspots],
            "other_patterns": [p.to_dict() for p in self.other_patterns],
            "pattern_clusters": [c.to_dict() for c in self.pattern_clusters],
        }

    def _generate_summary_section(self) -> list[str]:
        """
        Generate summary section for markdown report.

        Issue #665: Extracted from to_markdown to reduce function length.

        Returns:
            List of markdown lines for the summary section
        """
        return [
            "# Code Pattern Analysis Report",
            "",
            "## Summary",
            f"- **Path Analyzed:** `{self.scan_path}`",
            f"- **Files Analyzed:** {self.total_files_analyzed}",
            f"- **Lines Analyzed:** {self.total_lines_analyzed:,}",
            f"- **Patterns Found:** {self.total_patterns}",
            f"- **Potential LOC Reduction:** {self.potential_loc_reduction}",
            f"- **Complexity Score:** {self.complexity_score}",
            "",
        ]

    def _generate_duplicates_section(self) -> list[str]:
        """
        Generate duplicate patterns section for markdown report.

        Issue #665: Extracted from to_markdown to reduce function length.

        Returns:
            List of markdown lines for the duplicates section
        """
        if not self.duplicate_patterns:
            return []

        md = ["## Duplicate Patterns", ""]
        for i, dp in enumerate(self.duplicate_patterns[:10], 1):
            md.append(f"### {i}. {dp.description}")
            md.append(f"- **Occurrences:** {dp.occurrence_count}")
            md.append(f"- **Similarity:** {dp.similarity_score:.1%}")
            md.append(f"- **LOC Reduction:** {dp.code_reduction_potential}")
            md.append("- **Locations:**")
            for loc in dp.locations[:5]:
                md.append(f"  - `{loc}`")
            md.append(f"- **Suggestion:** {dp.suggestion}")
            md.append("")
        return md

    def _generate_regex_section(self) -> list[str]:
        """
        Generate regex opportunities section for markdown report.

        Issue #665: Extracted from to_markdown to reduce function length.

        Returns:
            List of markdown lines for the regex section
        """
        if not self.regex_opportunities:
            return []

        md = ["## Regex Optimization Opportunities", ""]
        for i, ro in enumerate(self.regex_opportunities[:10], 1):
            md.append(f"### {i}. {ro.description}")
            md.append(f"- **Location:** `{ro.locations[0]}`")
            md.append("- **Current:** Multiple string operations")
            md.append(f"- **Suggested Regex:** `{ro.suggested_regex}`")
            md.append(f"- **Performance Gain:** {ro.performance_gain}")
            md.append("")
        return md

    def _generate_complexity_section(self) -> list[str]:
        """
        Generate complexity hotspots section for markdown report.

        Issue #665: Extracted from to_markdown to reduce function length.

        Returns:
            List of markdown lines for the complexity section
        """
        if not self.complexity_hotspots:
            return []

        md = [
            "## Complexity Hotspots",
            "",
            "| Location | CC | MI | Suggestions |",
            "|----------|----|----|-------------|",
        ]
        for ch in sorted(
            self.complexity_hotspots,
            key=lambda x: x.cyclomatic_complexity,
            reverse=True,
        )[:15]:
            loc = str(ch.locations[0]) if ch.locations else "N/A"
            suggestions = "; ".join(ch.simplification_suggestions[:2])
            md.append(
                f"| `{loc}` | {ch.cyclomatic_complexity} | "
                f"{ch.maintainability_index:.1f} | {suggestions} |"
            )
        md.append("")
        return md

    def _generate_modularization_section(self) -> list[str]:
        """
        Generate modularization suggestions section for markdown report.

        Issue #665: Extracted from to_markdown to reduce function length.

        Returns:
            List of markdown lines for the modularization section
        """
        if not self.modularization_suggestions:
            return []

        md = ["## Modularization Suggestions", ""]
        for i, ms in enumerate(self.modularization_suggestions[:10], 1):
            md.append(f"### {i}. {ms.pattern_name}")
            md.append(f"- **Description:** {ms.description}")
            md.append(f"- **Repeated in:** {len(ms.repeated_in_files)} files")
            md.append(f"- **Suggested Module:** `{ms.suggested_module}`")
            md.append("- **Benefits:**")
            for benefit in ms.benefits:
                md.append(f"  - {benefit}")
            md.append("")
        return md

    def to_markdown(self) -> str:
        """
        Generate markdown report.

        Issue #665: Refactored to use extracted helpers for each section.
        """
        self.calculate_metrics()

        md = []
        md.extend(self._generate_summary_section())
        md.extend(self._generate_duplicates_section())
        md.extend(self._generate_regex_section())
        md.extend(self._generate_complexity_section())
        md.extend(self._generate_modularization_section())

        return "\n".join(md)
