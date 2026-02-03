# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Bug Prediction System (Issue #224)

Uses historical bug data, code patterns, and risk factors to predict
where bugs are likely to occur. Provides risk scoring, prevention tips,
and targeted testing suggestions.

Part of EPIC #217 - Advanced Code Intelligence Methods

Features:
- Historical bug analysis from git history
- Code complexity metrics
- Change frequency tracking
- Risk scoring with configurable weights
- Prevention suggestions
- Targeted test recommendations
- Risk heatmap generation

Issue #554: Enhanced with Vector/Redis/LLM infrastructure:
- ChromaDB for storing bug pattern embeddings
- Redis for caching prediction results
- LLM for semantic analysis of code patterns known to cause bugs
- Historical bug pattern learning via embeddings
"""

import logging
import re
import subprocess  # nosec B404 - required for git operations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)

# Issue #554: Flag to enable semantic analysis infrastructure
SEMANTIC_ANALYSIS_AVAILABLE = False
SemanticAnalysisMixin = None

try:
    from src.code_intelligence.analytics_infrastructure import (
        SemanticAnalysisMixin as _SemanticAnalysisMixin,
    )

    SemanticAnalysisMixin = _SemanticAnalysisMixin
    SEMANTIC_ANALYSIS_AVAILABLE = True
except ImportError:
    logger.debug("SemanticAnalysisMixin not available - semantic features disabled")

# Issue #380: Module-level tuple for function definition prefixes (used in startswith)
_FUNCTION_DEF_PREFIXES = ("def ", "async def ")

# Issue #380: Pre-compiled regex for import statement counting
_IMPORT_PATTERN_RE = re.compile(r"^(?:from\s+\S+\s+)?import\s+", re.MULTILINE)


# Issue #315 - Threshold-based score calculation to reduce nesting
def _calculate_threshold_score(
    value: int, thresholds: list[tuple[int, int]], default: int = 10
) -> int:
    """Calculate score based on value thresholds (Issue #315 - extracted helper).

    Args:
        value: The value to check against thresholds
        thresholds: List of (threshold, score) tuples in descending threshold order
        default: Score to return if value is below all thresholds

    Returns:
        Score corresponding to the first matched threshold
    """
    for threshold, score in thresholds:
        if value > threshold:
            return score
    return default


# ============================================================================
# Enums and Data Classes
# ============================================================================


class RiskLevel(Enum):
    """Bug risk levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class RiskFactor(Enum):
    """Factors contributing to bug risk."""

    COMPLEXITY = "complexity"
    CHANGE_FREQUENCY = "change_frequency"
    CODE_AGE = "code_age"
    TEST_COVERAGE = "test_coverage"
    BUG_HISTORY = "bug_history"
    AUTHOR_EXPERIENCE = "author_experience"
    FILE_SIZE = "file_size"
    DEPENDENCY_COUNT = "dependency_count"
    CYCLOMATIC_COMPLEXITY = "cyclomatic_complexity"
    NESTING_DEPTH = "nesting_depth"


@dataclass
class RiskFactorScore:
    """Score for an individual risk factor."""

    factor: RiskFactor
    score: float  # 0-100
    weight: float  # 0-1
    details: str = ""

    @property
    def weighted_score(self) -> float:
        """Calculate weighted score."""
        return self.score * self.weight

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "factor": self.factor.value,
            "score": round(self.score, 1),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 1),
            "details": self.details,
        }


@dataclass
class FileRiskAssessment:
    """Bug risk assessment for a file."""

    file_path: str
    risk_score: float  # 0-100 overall risk
    risk_level: RiskLevel
    factor_scores: list[RiskFactorScore] = field(default_factory=list)
    bug_count_history: int = 0
    last_bug_date: Optional[datetime] = None
    prevention_tips: list[str] = field(default_factory=list)
    suggested_tests: list[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level.value,
            "factors": {fs.factor.value: fs.score for fs in self.factor_scores},
            "factor_details": [fs.to_dict() for fs in self.factor_scores],
            "bug_count_history": self.bug_count_history,
            "last_bug_date": (
                self.last_bug_date.isoformat() if self.last_bug_date else None
            ),
            "prevention_tips": self.prevention_tips,
            "suggested_tests": self.suggested_tests,
            "recommendation": self.recommendation,
        }


@dataclass
class PredictionResult:
    """Complete bug prediction result for codebase analysis."""

    timestamp: datetime
    total_files: int
    analyzed_files: int
    high_risk_count: int
    predicted_bugs: int
    # Issue #468: accuracy_score is Optional - None when no historical data available
    accuracy_score: Optional[float]
    risk_distribution: dict[str, int]
    file_assessments: list[FileRiskAssessment]
    top_risk_factors: list[tuple[str, float]]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_files": self.total_files,
            "analyzed_files": self.analyzed_files,
            "high_risk_count": self.high_risk_count,
            "predicted_bugs": self.predicted_bugs,
            # Issue #468: Return None if no historical accuracy data, otherwise round
            "accuracy_score": round(self.accuracy_score, 1)
            if self.accuracy_score is not None
            else None,
            "accuracy_available": self.accuracy_score is not None,
            "risk_distribution": self.risk_distribution,
            "files": [fa.to_dict() for fa in self.file_assessments],
            "top_risk_factors": [
                {"factor": f, "total_score": round(s, 1)}
                for f, s in self.top_risk_factors
            ],
        }


# ============================================================================
# Prevention Tips and Test Suggestions
# ============================================================================


PREVENTION_TIPS: dict[RiskFactor, list[str]] = {
    RiskFactor.COMPLEXITY: [
        "Break down complex functions into smaller, testable units",
        "Add inline comments explaining complex logic",
        "Consider extracting helper functions",
        "Use design patterns to reduce cyclomatic complexity",
    ],
    RiskFactor.CHANGE_FREQUENCY: [
        "Stabilize the module before adding new features",
        "Review recent changes thoroughly",
        "Add regression tests for frequently changed code",
        "Consider refactoring to reduce change coupling",
    ],
    RiskFactor.BUG_HISTORY: [
        "Review all bug fix commits in this file",
        "Add defensive programming patterns",
        "Increase test coverage significantly",
        "Consider a comprehensive code review",
    ],
    RiskFactor.TEST_COVERAGE: [
        "Add unit tests for untested functions",
        "Create integration tests for critical paths",
        "Add edge case tests",
        "Consider mutation testing to improve test quality",
    ],
    RiskFactor.FILE_SIZE: [
        "Split large file into smaller modules",
        "Extract reusable components",
        "Apply single responsibility principle",
    ],
    RiskFactor.DEPENDENCY_COUNT: [
        "Reduce coupling by using dependency injection",
        "Consider facade pattern to simplify dependencies",
        "Review if all dependencies are necessary",
    ],
    RiskFactor.CYCLOMATIC_COMPLEXITY: [
        "Reduce nested conditionals with early returns",
        "Extract complex conditions into named functions",
        "Consider using strategy pattern for complex branching",
    ],
    RiskFactor.NESTING_DEPTH: [
        "Flatten deeply nested code with guard clauses",
        "Extract nested loops into separate functions",
        "Consider using list comprehensions or map/filter",
    ],
}


# ============================================================================
# Bug Predictor Class
# ============================================================================


# Issue #554: Dynamic base class selection for semantic analysis support
_BaseClass = SemanticAnalysisMixin if SEMANTIC_ANALYSIS_AVAILABLE else object


class BugPredictor(_BaseClass):
    """
    Predicts bug risk in code files based on multiple factors.

    Uses historical data, code metrics, and pattern analysis to
    identify high-risk areas that are likely to contain bugs.

    Issue #554: Enhanced with optional Vector/Redis/LLM infrastructure:
    - use_semantic_analysis=True enables LLM-based bug pattern matching
    - Learns from historical bug fix commits to identify similar patterns
    - Results cached in Redis for performance

    Usage:
        # Standard prediction
        predictor = BugPredictor()
        result = predictor.analyze_directory()

        # With semantic analysis (requires ChromaDB + Ollama)
        predictor = BugPredictor(use_semantic_analysis=True)
        result = await predictor.analyze_directory_async()
    """

    # Default risk factor weights (must sum to 1.0)
    DEFAULT_WEIGHTS: dict[RiskFactor, float] = {
        RiskFactor.COMPLEXITY: 0.15,
        RiskFactor.CHANGE_FREQUENCY: 0.15,
        RiskFactor.BUG_HISTORY: 0.25,
        RiskFactor.TEST_COVERAGE: 0.15,
        RiskFactor.CODE_AGE: 0.05,
        RiskFactor.AUTHOR_EXPERIENCE: 0.05,
        RiskFactor.FILE_SIZE: 0.05,
        RiskFactor.DEPENDENCY_COUNT: 0.05,
        RiskFactor.CYCLOMATIC_COMPLEXITY: 0.05,
        RiskFactor.NESTING_DEPTH: 0.05,
    }

    def __init__(
        self,
        project_root: Optional[str] = None,
        weights: Optional[dict[RiskFactor, float]] = None,
        bug_keywords: Optional[list[str]] = None,
        use_semantic_analysis: bool = False,
    ):
        """
        Initialize Bug Predictor.

        Args:
            project_root: Root directory of the project (defaults to cwd)
            weights: Custom risk factor weights (defaults to DEFAULT_WEIGHTS)
            bug_keywords: Keywords to identify bug-fix commits
            use_semantic_analysis: Enable LLM-based pattern analysis (Issue #554)
        """
        # Issue #554: Initialize semantic analysis infrastructure if enabled
        self.use_semantic_analysis = (
            use_semantic_analysis and SEMANTIC_ANALYSIS_AVAILABLE
        )

        if self.use_semantic_analysis:
            super().__init__()
            self._init_infrastructure(
                collection_name="bug_pattern_vectors",
                use_llm=True,
                use_cache=True,
                redis_database="analytics",
            )

        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.bug_keywords = bug_keywords or [
            "fix",
            "bug",
            "error",
            "issue",
            "patch",
            "hotfix",
            "resolve",
        ]

        # Cache for expensive operations
        self._bug_history_cache: Optional[dict[str, list[dict]]] = None
        self._change_freq_cache: Optional[dict[str, int]] = None
        self._author_stats_cache: Optional[dict[str, dict]] = None
        # Issue #554: Cache for semantic bug pattern embeddings
        self._bug_pattern_embeddings: Optional[Dict[str, List[float]]] = None

    def _collect_complexity_factors(
        self, path: Path, complexity: dict[str, Any]
    ) -> list[RiskFactorScore]:
        """Collect complexity-related risk factor scores (Issue #281 - extracted helper)."""
        return [
            RiskFactorScore(
                factor=RiskFactor.COMPLEXITY,
                score=complexity["overall"],
                weight=self.weights[RiskFactor.COMPLEXITY],
                details=f"Lines: {complexity['lines']}, Functions: {complexity['functions']}",
            ),
            RiskFactorScore(
                factor=RiskFactor.CYCLOMATIC_COMPLEXITY,
                score=complexity["cyclomatic"],
                weight=self.weights[RiskFactor.CYCLOMATIC_COMPLEXITY],
                details=f"Cyclomatic complexity score: {complexity['cyclomatic']:.0f}",
            ),
            RiskFactorScore(
                factor=RiskFactor.NESTING_DEPTH,
                score=complexity["nesting"],
                weight=self.weights[RiskFactor.NESTING_DEPTH],
                details=f"Max nesting depth: {complexity['max_depth']}",
            ),
        ]

    def _collect_history_factors(
        self, rel_path: str
    ) -> tuple[list[RiskFactorScore], dict[str, Any]]:
        """Collect history-related risk factors (Issue #281 - extracted helper).

        Returns tuple of (factor_scores, bug_data) for use in assessment.
        """
        change_data = self._get_change_frequency(rel_path)
        bug_data = self._get_bug_history(rel_path)

        scores = [
            RiskFactorScore(
                factor=RiskFactor.CHANGE_FREQUENCY,
                score=change_data["score"],
                weight=self.weights[RiskFactor.CHANGE_FREQUENCY],
                details=f"Changes in 90 days: {change_data['count']}",
            ),
            RiskFactorScore(
                factor=RiskFactor.BUG_HISTORY,
                score=bug_data["score"],
                weight=self.weights[RiskFactor.BUG_HISTORY],
                details=f"Bug fixes: {bug_data['count']}",
            ),
        ]
        return scores, bug_data

    def _compute_prediction_stats(
        self, assessments: list[FileRiskAssessment]
    ) -> dict[str, Any]:
        """
        Compute prediction statistics from assessments (Issue #665: extracted).

        Args:
            assessments: List of file risk assessments (should be pre-sorted)

        Returns:
            Dict with high_risk_count, risk_distribution, top_factors, predicted_bugs
        """
        # High risk count
        high_risk_count = sum(
            1
            for a in assessments
            if a.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH)
        )

        # Risk distribution
        risk_dist = {level.value: 0 for level in RiskLevel}
        for a in assessments:
            risk_dist[a.risk_level.value] += 1

        # Top risk factors
        factor_totals: dict[str, float] = {}
        for a in assessments:
            for fs in a.factor_scores:
                factor_totals[fs.factor.value] = (
                    factor_totals.get(fs.factor.value, 0) + fs.score
                )
        top_factors = sorted(factor_totals.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]

        # Estimate predicted bugs (based on high risk file count)
        predicted_bugs = int(high_risk_count * 0.7)  # 70% of high risk files

        return {
            "high_risk_count": high_risk_count,
            "risk_distribution": risk_dist,
            "top_factors": top_factors,
            "predicted_bugs": predicted_bugs,
        }

    def _collect_structure_factors(self, path: Path) -> list[RiskFactorScore]:
        """Collect file structure risk factors (Issue #281 - extracted helper)."""
        size_score = self._calculate_file_size_score(path)
        dep_score = self._analyze_dependencies(path)

        return [
            RiskFactorScore(
                factor=RiskFactor.FILE_SIZE,
                score=size_score["score"],
                weight=self.weights[RiskFactor.FILE_SIZE],
                details=f"Size: {size_score['lines']} lines",
            ),
            RiskFactorScore(
                factor=RiskFactor.DEPENDENCY_COUNT,
                score=dep_score["score"],
                weight=self.weights[RiskFactor.DEPENDENCY_COUNT],
                details=f"Imports: {dep_score['count']}",
            ),
            RiskFactorScore(
                factor=RiskFactor.TEST_COVERAGE,
                score=50.0,  # Default to medium if no coverage data
                weight=self.weights[RiskFactor.TEST_COVERAGE],
                details="Coverage data not available",
            ),
        ]

    def analyze_file(self, file_path: str) -> FileRiskAssessment:
        """
        Analyze a single file for bug risk.

        Issue #281: Refactored to use extracted helpers.

        Args:
            file_path: Path to the file to analyze

        Returns:
            FileRiskAssessment with complete risk analysis
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.project_root / path

        rel_path = str(path.relative_to(self.project_root))

        # Collect all risk factors using helpers
        complexity = self._analyze_complexity(path)
        factor_scores = self._collect_complexity_factors(path, complexity)

        history_factors, bug_data = self._collect_history_factors(rel_path)
        factor_scores.extend(history_factors)

        factor_scores.extend(self._collect_structure_factors(path))

        # Calculate overall risk score and build assessment
        risk_score = sum(fs.weighted_score for fs in factor_scores)

        return FileRiskAssessment(
            file_path=rel_path,
            risk_score=risk_score,
            risk_level=self._get_risk_level(risk_score),
            factor_scores=factor_scores,
            bug_count_history=bug_data["count"],
            last_bug_date=bug_data.get("last_date"),
            prevention_tips=self._generate_prevention_tips(factor_scores),
            suggested_tests=self._generate_test_suggestions(rel_path, factor_scores),
            recommendation=self._generate_recommendation(risk_score, factor_scores),
        )

    def analyze_directory(
        self,
        directory: Optional[str] = None,
        pattern: str = "*.py",
        limit: int = 0,
    ) -> PredictionResult:
        """
        Analyze all files in a directory for bug risk.

        Args:
            directory: Directory to analyze (defaults to project root)
            pattern: Glob pattern for files to include
            limit: Maximum number of files to analyze (0 = no limit)

        Returns:
            PredictionResult with complete codebase analysis
        """
        root = Path(directory) if directory else self.project_root

        # Find files to analyze (limit=0 means no limit)
        all_files = list(root.rglob(pattern))
        total_files = len(all_files)
        files = all_files[:limit] if limit > 0 else all_files

        # Analyze each file
        assessments = []
        for file_path in files:
            try:
                assessment = self.analyze_file(str(file_path))
                assessments.append(assessment)
            except Exception as e:
                logger.warning("Failed to analyze %s: %s", file_path, e)

        # Sort and compute statistics (Issue #665: uses shared helper)
        assessments.sort(key=lambda x: x.risk_score, reverse=True)
        stats = self._compute_prediction_stats(assessments)

        return PredictionResult(
            timestamp=datetime.now(),
            total_files=total_files,
            analyzed_files=len(assessments),
            high_risk_count=stats["high_risk_count"],
            predicted_bugs=stats["predicted_bugs"],
            # Issue #468: Return None - historical accuracy tracking not yet implemented
            # To get real accuracy: store predictions, track outcomes, calculate metrics
            accuracy_score=None,
            risk_distribution=stats["risk_distribution"],
            file_assessments=assessments,
            top_risk_factors=stats["top_factors"],
        )

    def get_high_risk_files(
        self,
        directory: Optional[str] = None,
        threshold: float = 60.0,
        limit: int = 20,
    ) -> list[FileRiskAssessment]:
        """
        Get files with risk score above threshold.

        Args:
            directory: Directory to analyze
            threshold: Minimum risk score
            limit: Maximum files to return

        Returns:
            List of high-risk file assessments
        """
        result = self.analyze_directory(directory)
        high_risk = [a for a in result.file_assessments if a.risk_score >= threshold]
        return high_risk[:limit]

    def generate_heatmap(
        self,
        directory: Optional[str] = None,
        grouping: str = "directory",
    ) -> dict[str, Any]:
        """
        Generate risk heatmap data for visualization.

        Args:
            directory: Directory to analyze
            grouping: How to group files ('directory', 'module', 'flat')

        Returns:
            Heatmap data structure
        """
        result = self.analyze_directory(directory)

        if grouping == "flat":
            return {
                "grouping": "flat",
                "data": [
                    {
                        "name": a.file_path,
                        "value": a.risk_score,
                        "risk_level": a.risk_level.value,
                    }
                    for a in result.file_assessments
                ],
                "legend": self._get_heatmap_legend(),
            }

        # Group by directory
        groups: dict[str, list[FileRiskAssessment]] = {}
        for a in result.file_assessments:
            parts = a.file_path.split("/")
            group = parts[0] if len(parts) > 1 else "root"
            if group not in groups:
                groups[group] = []
            groups[group].append(a)

        heatmap_data = []
        for group_name, assessments in groups.items():
            avg_risk = sum(a.risk_score for a in assessments) / len(assessments)
            heatmap_data.append(
                {
                    "name": group_name,
                    "value": round(avg_risk, 1),
                    "file_count": len(assessments),
                    "risk_level": self._get_risk_level(avg_risk).value,
                    "files": [
                        {"path": a.file_path, "risk": a.risk_score} for a in assessments
                    ],
                }
            )

        return {
            "grouping": grouping,
            "data": sorted(heatmap_data, key=lambda x: x["value"], reverse=True),
            "legend": self._get_heatmap_legend(),
        }

    # =========================================================================
    # Private Analysis Methods
    # =========================================================================

    # Issue #281 - Thresholds for complexity scoring
    _LINE_COUNT_THRESHOLDS: list[tuple[int, int]] = [
        (500, 30),  # > 500 lines = +30
        (300, 20),  # > 300 lines = +20
        (100, 10),  # > 100 lines = +10
    ]

    _FUNC_COUNT_THRESHOLDS: list[tuple[int, int]] = [
        (20, 25),  # > 20 functions = +25
        (10, 15),  # > 10 functions = +15
        (5, 5),  # > 5 functions = +5
    ]

    # Keywords for cyclomatic complexity approximation
    _CONTROL_FLOW_KEYWORDS: tuple[str, ...] = (
        "if ",
        "elif ",
        "else:",
        "for ",
        "while ",
        "try:",
        "except:",
        "and ",
        "or ",
    )

    def _get_default_complexity_result(self) -> dict[str, Any]:
        """Return default complexity result for missing/failed files (Issue #281)."""
        return {
            "overall": 30.0,
            "cyclomatic": 30.0,
            "nesting": 30.0,
            "lines": 0,
            "functions": 0,
            "max_depth": 0,
        }

    def _count_code_metrics(self, lines: list[str]) -> dict[str, int]:
        """Count basic code metrics (Issue #281 - extracted helper)."""
        func_count = sum(
            1 for line in lines if line.strip().startswith(_FUNCTION_DEF_PREFIXES)
        )

        max_depth = 0
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                max_depth = max(max_depth, indent // 4)

        conditionals = sum(
            1 for line in lines if any(kw in line for kw in self._CONTROL_FLOW_KEYWORDS)
        )

        return {
            "func_count": func_count,
            "max_depth": max_depth,
            "conditionals": conditionals,
        }

    def _calculate_complexity_scores(
        self, line_count: int, metrics: dict[str, int]
    ) -> dict[str, float]:
        """Calculate complexity scores from metrics (Issue #281 - extracted helper)."""
        complexity_score = _calculate_threshold_score(
            line_count, self._LINE_COUNT_THRESHOLDS, 0
        ) + _calculate_threshold_score(
            metrics["func_count"], self._FUNC_COUNT_THRESHOLDS, 0
        )

        nesting_score = min(100, metrics["max_depth"] * 15)
        cyclomatic_score = min(100, metrics["conditionals"] * 2)

        return {
            "overall": min(100, complexity_score + (cyclomatic_score * 0.3)),
            "cyclomatic": cyclomatic_score,
            "nesting": nesting_score,
        }

    def _analyze_complexity(self, path: Path) -> dict[str, Any]:
        """Analyze code complexity metrics (Issue #281 - refactored)."""
        try:
            if not path.exists():
                return self._get_default_complexity_result()

            content = path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
            line_count = len(lines)

            metrics = self._count_code_metrics(lines)
            scores = self._calculate_complexity_scores(line_count, metrics)

            return {
                **scores,
                "lines": line_count,
                "functions": metrics["func_count"],
                "max_depth": metrics["max_depth"],
            }

        except Exception as e:
            logger.warning("Failed to analyze complexity for %s: %s", path, e)
            return self._get_default_complexity_result()

    def _get_change_frequency(self, file_path: str) -> dict[str, Any]:
        """Get change frequency for a file in the last 90 days."""
        if self._change_freq_cache is None:
            self._build_change_frequency_cache()

        count = self._change_freq_cache.get(file_path, 0)
        # Score: More changes = higher risk (up to 100)
        score = min(100, count * 8)

        return {"count": count, "score": score}

    def _build_change_frequency_cache(self) -> None:
        """Build cache of change frequency from git."""
        self._change_freq_cache = {}
        try:
            result = subprocess.run(  # nosec B607 - git is safe
                [
                    "git",
                    "log",
                    "--since=90 days ago",
                    "--name-only",
                    "--pretty=format:",
                ],
                capture_output=True,
                text=True,
                timeout=TimingConstants.SHORT_TIMEOUT,
                encoding="utf-8",
                cwd=self.project_root,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        self._change_freq_cache[line] = (
                            self._change_freq_cache.get(line, 0) + 1
                        )
        except Exception as e:
            logger.warning("Failed to get change frequency: %s", e)

    def _get_bug_history(self, file_path: str) -> dict[str, Any]:
        """Get bug fix history for a file."""
        if self._bug_history_cache is None:
            self._build_bug_history_cache()

        bugs = self._bug_history_cache.get(file_path, [])
        count = len(bugs)
        # Score: More bugs = higher risk
        score = min(100, count * 12)

        last_date = None
        if bugs:
            try:
                last_date = datetime.fromisoformat(bugs[0].get("date", ""))
            except Exception:
                pass  # nosec B110 - intentional fallback for invalid dates

        return {"count": count, "score": score, "last_date": last_date}

    def _parse_commit_line(self, line: str) -> Optional[dict]:
        """Parse a commit info line (Issue #335 - extracted helper)."""
        if "|" not in line:
            return None
        parts = line.split("|", 2)
        return {
            "hash": parts[0],
            "date": parts[1].strip() if len(parts) > 1 else "",
            "message": parts[2] if len(parts) > 2 else "",
        }

    def _add_file_to_bug_cache(self, file_path: str, commit: dict) -> None:
        """Add a file entry to bug history cache (Issue #335 - extracted helper)."""
        if file_path not in self._bug_history_cache:
            self._bug_history_cache[file_path] = []
        self._bug_history_cache[file_path].append(commit.copy())

    def _build_bug_history_cache(self) -> None:
        """Build cache of bug history from git."""
        self._bug_history_cache = {}
        try:
            # Get bug-related commits
            grep_args = []
            for kw in self.bug_keywords:
                grep_args.extend(["--grep", kw])

            result = subprocess.run(  # nosec B607 - git is safe
                [
                    "git",
                    "log",
                    "--since=1 year ago",
                    *grep_args,
                    "--all-match",
                    "--name-only",
                    "--format=%H|%ad|%s",
                    "--date=iso",
                ],
                capture_output=True,
                text=True,
                timeout=TimingConstants.STANDARD_TIMEOUT,
                encoding="utf-8",
                cwd=self.project_root,
            )

            if result.returncode != 0:
                return

            current_commit = None
            for line in result.stdout.strip().split("\n"):
                parsed = self._parse_commit_line(line)
                if parsed:
                    current_commit = parsed
                elif line and current_commit:
                    self._add_file_to_bug_cache(line, current_commit)

        except Exception as e:
            logger.warning("Failed to get bug history: %s", e)

    # Issue #315 - File size thresholds for risk scoring
    _FILE_SIZE_THRESHOLDS: list[tuple[int, int]] = [
        (1000, 100),  # > 1000 lines = score 100
        (500, 75),  # > 500 lines = score 75
        (300, 50),  # > 300 lines = score 50
        (100, 25),  # > 100 lines = score 25
    ]

    def _calculate_file_size_score(self, path: Path) -> dict[str, Any]:
        """Calculate risk score based on file size (Issue #315 - refactored)."""
        try:
            if not path.exists():
                return {"lines": 0, "score": 0}

            content = path.read_text(encoding="utf-8", errors="ignore")
            lines = len(content.split("\n"))
            score = _calculate_threshold_score(lines, self._FILE_SIZE_THRESHOLDS)

            return {"lines": lines, "score": score}

        except Exception:
            return {"lines": 0, "score": 30}

    # Issue #315 - Import count thresholds for coupling risk
    _DEPENDENCY_THRESHOLDS: list[tuple[int, int]] = [
        (30, 100),  # > 30 imports = score 100
        (20, 75),  # > 20 imports = score 75
        (10, 50),  # > 10 imports = score 50
        (5, 25),  # > 5 imports = score 25
    ]

    def _analyze_dependencies(self, path: Path) -> dict[str, Any]:
        """Analyze import/dependency count (Issue #315 - refactored)."""
        try:
            if not path.exists():
                return {"count": 0, "score": 0}

            content = path.read_text(encoding="utf-8", errors="ignore")

            # Count import statements (Issue #380: use pre-compiled pattern)
            imports = len(_IMPORT_PATTERN_RE.findall(content))
            score = _calculate_threshold_score(imports, self._DEPENDENCY_THRESHOLDS)

            return {"count": imports, "score": score}

        except Exception:
            return {"count": 0, "score": 30}

    def _get_risk_level(self, score: float) -> RiskLevel:
        """Convert risk score to level."""
        if score >= 80:
            return RiskLevel.CRITICAL
        if score >= 60:
            return RiskLevel.HIGH
        if score >= 40:
            return RiskLevel.MEDIUM
        if score >= 20:
            return RiskLevel.LOW
        return RiskLevel.MINIMAL

    def _generate_prevention_tips(
        self, factor_scores: list[RiskFactorScore]
    ) -> list[str]:
        """Generate prevention tips based on highest risk factors."""
        tips = []
        sorted_factors = sorted(factor_scores, key=lambda x: x.score, reverse=True)

        for fs in sorted_factors[:3]:
            if fs.score > 50:
                factor_tips = PREVENTION_TIPS.get(fs.factor, [])
                tips.extend(factor_tips[:2])

        return tips[:5]

    def _generate_test_suggestions(
        self, file_path: str, factor_scores: list[RiskFactorScore]
    ) -> list[str]:
        """Generate test suggestions based on risk factors."""
        suggestions = []
        basename = Path(file_path).stem

        # Build factor dict for easy lookup
        factors = {fs.factor: fs.score for fs in factor_scores}

        if factors.get(RiskFactor.COMPLEXITY, 0) > 50:
            suggestions.append(f"Add boundary condition tests for {basename}")
            suggestions.append(f"Test error handling paths in {basename}")

        if factors.get(RiskFactor.CHANGE_FREQUENCY, 0) > 50:
            suggestions.append(f"Add regression tests for recent changes in {basename}")

        if factors.get(RiskFactor.BUG_HISTORY, 0) > 50:
            suggestions.append(
                f"Create tests covering previous bug scenarios in {basename}"
            )

        if factors.get(RiskFactor.TEST_COVERAGE, 0) > 50:
            suggestions.append(f"Increase unit test coverage for {basename}")
            suggestions.append(f"Add integration tests for {basename}")

        if factors.get(RiskFactor.CYCLOMATIC_COMPLEXITY, 0) > 60:
            suggestions.append(f"Add branch coverage tests for {basename}")

        return suggestions[:4]

    def _generate_recommendation(
        self, risk_score: float, factor_scores: list[RiskFactorScore]
    ) -> str:
        """Generate a recommendation based on risk analysis."""
        if risk_score >= 80:
            return (
                "CRITICAL: Immediate attention required. "
                "Consider comprehensive code review and refactoring."
            )
        if risk_score >= 60:
            return (
                "HIGH RISK: Prioritize testing and code review. "
                "Add monitoring for this file."
            )
        if risk_score >= 40:
            return (
                "MODERATE: Regular monitoring recommended. "
                "Consider improving test coverage."
            )
        if risk_score >= 20:
            return "LOW RISK: Standard maintenance practices sufficient."
        return "MINIMAL RISK: File is well-maintained with low bug probability."

    def _get_heatmap_legend(self) -> dict[str, dict[str, Any]]:
        """Get heatmap color legend."""
        return {
            "critical": {"min": 80, "color": "#ef4444"},
            "high": {"min": 60, "color": "#f97316"},
            "medium": {"min": 40, "color": "#eab308"},
            "low": {"min": 20, "color": "#22c55e"},
            "minimal": {"min": 0, "color": "#3b82f6"},
        }

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._bug_history_cache = None
        self._change_freq_cache = None
        self._author_stats_cache = None
        self._bug_pattern_embeddings = None

    # =========================================================================
    # Issue #554: Async Semantic Analysis Methods
    # =========================================================================

    async def _learn_bug_patterns_async(self) -> None:
        """
        Learn bug patterns from historical bug fix commits.

        Issue #554: Extracts code patterns from bug fix commits
        and stores their embeddings in ChromaDB for similarity matching.
        """
        if not self.use_semantic_analysis:
            return

        if self._bug_history_cache is None:
            self._build_bug_history_cache()

        # Collect code snippets from bug fixes
        bug_patterns = []
        for file_path, bugs in (self._bug_history_cache or {}).items():
            for bug in bugs[:5]:  # Limit per file for performance
                pattern_id = f"{file_path}:{bug.get('hash', 'unknown')}"
                message = bug.get("message", "")
                bug_patterns.append(
                    {
                        "id": pattern_id,
                        "file": file_path,
                        "message": message,
                    }
                )

        if not bug_patterns:
            logger.debug("No bug patterns found to learn from")
            return

        # Store patterns in vector DB
        texts = [f"Bug fix in {p['file']}: {p['message']}" for p in bug_patterns]
        embeddings = await self._get_embeddings_batch(texts)

        # Filter out failed embeddings and store valid ones
        valid_ids = []
        valid_embeddings = []
        valid_texts = []
        valid_metadata = []
        for i, emb in enumerate(embeddings):
            if emb is not None:
                valid_ids.append(bug_patterns[i]["id"])
                valid_embeddings.append(emb)
                valid_texts.append(texts[i])
                valid_metadata.append({"file": bug_patterns[i]["file"]})

        if valid_embeddings:
            await self._store_vectors(
                ids=valid_ids,
                embeddings=valid_embeddings,
                documents=valid_texts,
                metadatas=valid_metadata,
            )
        logger.info(
            "Learned %d bug patterns for semantic analysis", len(valid_embeddings)
        )

    def _create_semantic_disabled_score(self) -> RiskFactorScore:
        """
        Create a RiskFactorScore when semantic analysis is disabled.

        Returns a zero-weighted score indicating semantic analysis is not
        enabled for this predictor instance. Issue #620.
        """
        return RiskFactorScore(
            factor=RiskFactor.BUG_HISTORY,
            score=0.0,
            weight=0.0,
            details="Semantic analysis not enabled",
        )

    def _create_semantic_error_score(
        self, details: str, score: float = 30.0
    ) -> RiskFactorScore:
        """
        Create a RiskFactorScore for semantic analysis errors or fallback cases.

        Args:
            details: Description of the error or condition
            score: Risk score to assign (default 30.0 for errors)

        Returns a low-weighted score with the error details. Issue #620.
        """
        return RiskFactorScore(
            factor=RiskFactor.BUG_HISTORY,
            score=score,
            weight=0.05,
            details=details,
        )

    def _create_semantic_success_score(
        self, similar_count: int, avg_similarity: float
    ) -> RiskFactorScore:
        """
        Create a RiskFactorScore from successful semantic similarity analysis.

        Args:
            similar_count: Number of similar bug patterns found
            avg_similarity: Average similarity score (0.0-1.0)

        Returns a weighted score based on similarity to bug patterns. Issue #620.
        """
        score = avg_similarity * 100  # Convert to 0-100 scale
        return RiskFactorScore(
            factor=RiskFactor.BUG_HISTORY,
            score=score,
            weight=0.10,
            details=f"Similar to {similar_count} historical bug patterns ({avg_similarity:.1%} avg)",
        )

    async def _analyze_file_semantic_async(
        self,
        file_path: str,
    ) -> RiskFactorScore:
        """
        Analyze file for similarity to known bug patterns.

        Issue #554: Uses LLM embeddings to find semantic similarity
        between current code and historical bug-prone patterns.

        Args:
            file_path: Path to the file to analyze

        Returns:
            RiskFactorScore for semantic bug pattern similarity
        """
        if not self.use_semantic_analysis:
            return self._create_semantic_disabled_score()

        path = Path(file_path)
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            content_sample = content[:1000]

            embedding = await self._get_embedding(content_sample)
            if not embedding:
                return self._create_semantic_error_score(
                    "Could not generate embedding for file", score=10.0
                )

            similar = await self._query_similar(
                embedding, n_results=5, min_similarity=0.6
            )

            if not similar:
                return RiskFactorScore(
                    factor=RiskFactor.BUG_HISTORY,
                    score=10.0,
                    weight=0.10,
                    details="No similar bug patterns found",
                )

            avg_similarity = sum(s["similarity"] for s in similar) / len(similar)
            return self._create_semantic_success_score(len(similar), avg_similarity)

        except Exception as e:
            logger.warning("Semantic analysis failed for %s: %s", file_path, e)
            return self._create_semantic_error_score(f"Semantic analysis error: {e}")

    async def analyze_file_async(self, file_path: str) -> FileRiskAssessment:
        """
        Analyze a single file for bug risk with semantic analysis.

        Issue #554: Async version that includes LLM-based pattern matching.

        Args:
            file_path: Path to the file to analyze

        Returns:
            FileRiskAssessment with complete risk analysis
        """
        # Get base assessment using synchronous method
        assessment = self.analyze_file(file_path)

        # Add semantic analysis if enabled
        if self.use_semantic_analysis:
            semantic_factor = await self._analyze_file_semantic_async(file_path)
            if semantic_factor.score > 0:
                assessment.factor_scores.append(semantic_factor)
                # Recalculate total risk score
                assessment.risk_score = sum(
                    fs.weighted_score for fs in assessment.factor_scores
                )
                assessment.risk_level = self._get_risk_level(assessment.risk_score)

        return assessment

    async def analyze_directory_async(
        self,
        directory: Optional[str] = None,
        pattern: str = "*.py",
        limit: int = 0,
    ) -> PredictionResult:
        """
        Analyze all files in a directory with semantic analysis.

        Issue #554: Async version that includes LLM-based bug pattern
        matching and caches results in Redis.

        Args:
            directory: Directory to analyze (defaults to project root)
            pattern: Glob pattern for files to include
            limit: Maximum number of files to analyze (0 = no limit)

        Returns:
            PredictionResult with complete codebase analysis
        """
        root = Path(directory) if directory else self.project_root

        # Check for cached results
        cache_key = f"bug_pred:{root}:{pattern}:{limit}"
        if self.use_semantic_analysis:
            cached = await self._get_cached_result(cache_key, prefix="bug_predictor")
            if cached:
                logger.info("Returning cached bug prediction")
                return PredictionResult(**cached)

        # Learn from historical bug patterns
        await self._learn_bug_patterns_async()

        # Find files to analyze (limit=0 means no limit)
        all_files = list(root.rglob(pattern))
        total_files = len(all_files)
        files = all_files[:limit] if limit > 0 else all_files

        # Analyze each file with semantic analysis
        assessments = []
        for file_path in files:
            try:
                assessment = await self.analyze_file_async(str(file_path))
                assessments.append(assessment)
            except Exception as e:
                logger.warning("Failed to analyze %s: %s", file_path, e)

        # Sort and compute statistics (Issue #665: uses shared helper)
        assessments.sort(key=lambda x: x.risk_score, reverse=True)
        stats = self._compute_prediction_stats(assessments)

        result = PredictionResult(
            timestamp=datetime.now(),
            total_files=total_files,
            analyzed_files=len(assessments),
            high_risk_count=stats["high_risk_count"],
            predicted_bugs=stats["predicted_bugs"],
            accuracy_score=None,
            risk_distribution=stats["risk_distribution"],
            file_assessments=assessments,
            top_risk_factors=stats["top_factors"],
        )

        # Cache results
        if self.use_semantic_analysis:
            await self._cache_result(
                cache_key,
                result.to_dict(),
                prefix="bug_predictor",
                ttl=1800,  # 30 minute cache
            )

        return result

    def get_infrastructure_metrics(self) -> Dict[str, Any]:
        """
        Get infrastructure metrics for monitoring.

        Issue #554: Returns cache hits, embeddings generated, etc.
        """
        if self.use_semantic_analysis:
            return self._get_infrastructure_metrics()
        return {}


# ============================================================================
# Convenience Functions
# ============================================================================


def predict_bugs(
    directory: Optional[str] = None,
    pattern: str = "*.py",
    limit: int = 100,
) -> PredictionResult:
    """
    Predict bugs in a directory.

    Args:
        directory: Directory to analyze
        pattern: File pattern to include
        limit: Maximum files to analyze

    Returns:
        PredictionResult with analysis
    """
    predictor = BugPredictor(project_root=directory)
    return predictor.analyze_directory(pattern=pattern, limit=limit)


async def predict_bugs_async(
    directory: Optional[str] = None,
    pattern: str = "*.py",
    limit: int = 100,
    use_semantic_analysis: bool = True,
) -> PredictionResult:
    """
    Predict bugs in a directory with semantic analysis.

    Issue #554: Async version with LLM-based bug pattern matching.

    Args:
        directory: Directory to analyze
        pattern: File pattern to include
        limit: Maximum files to analyze
        use_semantic_analysis: Enable semantic analysis (default True)

    Returns:
        PredictionResult with analysis including semantic patterns
    """
    predictor = BugPredictor(
        project_root=directory,
        use_semantic_analysis=use_semantic_analysis,
    )
    return await predictor.analyze_directory_async(pattern=pattern, limit=limit)


def get_file_risk(file_path: str) -> FileRiskAssessment:
    """
    Get risk assessment for a single file.

    Args:
        file_path: Path to the file

    Returns:
        FileRiskAssessment for the file
    """
    predictor = BugPredictor()
    return predictor.analyze_file(file_path)


def get_high_risk_files(
    directory: Optional[str] = None,
    threshold: float = 60.0,
    limit: int = 20,
) -> list[FileRiskAssessment]:
    """
    Get files with high bug risk.

    Args:
        directory: Directory to analyze
        threshold: Minimum risk score
        limit: Maximum files to return

    Returns:
        List of high-risk file assessments
    """
    predictor = BugPredictor(project_root=directory)
    return predictor.get_high_risk_files(threshold=threshold, limit=limit)


def get_risk_factors() -> list[dict[str, Any]]:
    """
    Get all risk factors and their default weights.

    Returns:
        List of risk factor definitions
    """
    descriptions = {
        RiskFactor.COMPLEXITY: (
            "Code complexity measured by nesting depth, conditionals, and function count"
        ),
        RiskFactor.CHANGE_FREQUENCY: (
            "How often the file has been modified in the last 90 days"
        ),
        RiskFactor.BUG_HISTORY: (
            "Number of bug fixes historically associated with this file"
        ),
        RiskFactor.TEST_COVERAGE: (
            "Inverse of test coverage - higher score means less coverage"
        ),
        RiskFactor.CODE_AGE: "Age of the code since last major refactor",
        RiskFactor.AUTHOR_EXPERIENCE: "Experience level of recent contributors",
        RiskFactor.FILE_SIZE: "File size in lines of code",
        RiskFactor.DEPENDENCY_COUNT: "Number of imports and dependencies",
        RiskFactor.CYCLOMATIC_COMPLEXITY: (
            "Number of independent paths through the code"
        ),
        RiskFactor.NESTING_DEPTH: "Maximum depth of nested blocks",
    }

    return [
        {
            "name": factor.value,
            "display_name": factor.value.replace("_", " ").title(),
            "weight": weight,
            "weight_percentage": f"{weight * 100:.0f}%",
            "description": descriptions.get(factor, ""),
        }
        for factor, weight in BugPredictor.DEFAULT_WEIGHTS.items()
    ]


def get_risk_levels() -> list[dict[str, Any]]:
    """
    Get risk level definitions.

    Returns:
        List of risk level definitions
    """
    return [
        {
            "level": RiskLevel.CRITICAL.value,
            "min_score": 80,
            "description": "Immediate attention required",
        },
        {
            "level": RiskLevel.HIGH.value,
            "min_score": 60,
            "description": "Prioritize for review",
        },
        {
            "level": RiskLevel.MEDIUM.value,
            "min_score": 40,
            "description": "Monitor regularly",
        },
        {
            "level": RiskLevel.LOW.value,
            "min_score": 20,
            "description": "Standard maintenance",
        },
        {
            "level": RiskLevel.MINIMAL.value,
            "min_score": 0,
            "description": "Low priority",
        },
    ]
