# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multi-Language Code Scanner

Issue #386: Provides a unified interface for scanning codebases across
all supported languages (Python, TypeScript, JavaScript, Vue, Shell).

Combines all language-specific analyzers and the existing Python performance
analyzer into a single scanning interface.

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.code_intelligence.base_analyzer import (
    AnalysisIssue,
    AnalysisResult,
    Language,
    MultiLanguageAnalyzer,
)
from src.code_intelligence.shell_analyzer import ShellAnalyzer
from src.code_intelligence.typescript_analyzer import TypeScriptAnalyzer
from src.code_intelligence.vue_analyzer import VueAnalyzer

logger = logging.getLogger(__name__)


def create_multi_language_scanner() -> MultiLanguageAnalyzer:
    """Create a MultiLanguageAnalyzer with all available analyzers registered.

    Returns:
        MultiLanguageAnalyzer configured with TypeScript, Vue, and Shell analyzers.
    """
    scanner = MultiLanguageAnalyzer()

    # Register all analyzers
    scanner.register_analyzer(TypeScriptAnalyzer())
    scanner.register_analyzer(VueAnalyzer())
    scanner.register_analyzer(ShellAnalyzer())

    logger.info(
        "Multi-language scanner initialized with %d analyzers covering %d languages",
        len(scanner.analyzers),
        len(scanner.get_supported_languages()),
    )

    return scanner


class CodebaseScanner:
    """High-level codebase scanner that combines all code intelligence tools.

    Provides a unified interface for:
    - Multi-language static analysis (TS/JS, Vue, Shell)
    - Python performance analysis (via existing analyzer)
    - Issue aggregation and reporting
    """

    def __init__(self):
        """Initialize the codebase scanner."""
        self.multi_lang_analyzer = create_multi_language_scanner()
        self._scan_history: List[Dict[str, Any]] = []

    def scan_file(self, file_path: Path) -> AnalysisResult:
        """Scan a single file.

        Args:
            file_path: Path to the file to scan

        Returns:
            AnalysisResult with all detected issues
        """
        start_time = time.time()
        result = self.multi_lang_analyzer.analyze_file(file_path)
        result.analysis_time_ms = (time.time() - start_time) * 1000

        # Log scan
        self._scan_history.append(
            {
                "type": "file",
                "path": str(file_path),
                "timestamp": time.time(),
                "issues_found": len(result.issues),
                "time_ms": result.analysis_time_ms,
            }
        )

        return result

    def _filter_issues_by_language(
        self, result: AnalysisResult, languages: Set[Language]
    ) -> AnalysisResult:
        """Filter analysis result to only include specified languages. Issue #620."""
        filtered_issues = [
            issue for issue in result.issues if issue.language in languages
        ]
        new_result = AnalysisResult(
            files_analyzed=result.files_analyzed,
            errors=result.errors,
            analysis_time_ms=result.analysis_time_ms,
        )
        for issue in filtered_issues:
            new_result.add_issue(issue)
        return new_result

    def _log_directory_scan(self, directory: Path, result: AnalysisResult) -> None:
        """Log directory scan to history and emit log message. Issue #620."""
        self._scan_history.append(
            {
                "type": "directory",
                "path": str(directory),
                "timestamp": time.time(),
                "files_scanned": result.files_analyzed,
                "issues_found": len(result.issues),
                "time_ms": result.analysis_time_ms,
            }
        )
        logger.info(
            "Directory scan complete: %d files, %d issues in %.2fms",
            result.files_analyzed,
            len(result.issues),
            result.analysis_time_ms,
        )

    def scan_directory(
        self,
        directory: Path,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None,
        languages: Optional[Set[Language]] = None,
    ) -> AnalysisResult:
        """Scan all supported files in a directory.

        Args:
            directory: Root directory to scan
            recursive: Whether to scan subdirectories
            exclude_patterns: Glob patterns to exclude
            languages: Optional set of languages to scan (None = all)

        Returns:
            AnalysisResult with all detected issues
        """
        start_time = time.time()

        result = self.multi_lang_analyzer.analyze_directory(
            directory, recursive=recursive, exclude_patterns=exclude_patterns
        )

        if languages:
            result = self._filter_issues_by_language(result, languages)

        result.analysis_time_ms = (time.time() - start_time) * 1000
        self._log_directory_scan(directory, result)

        return result

    def scan_codebase(
        self,
        root_path: Optional[Path] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> AnalysisResult:
        """Scan the entire AutoBot codebase.

        Args:
            root_path: Root path (defaults to current directory)
            exclude_patterns: Additional patterns to exclude

        Returns:
            AnalysisResult with all detected issues
        """
        if root_path is None:
            root_path = Path.cwd()

        # Default exclusions for the AutoBot project
        default_excludes = [
            "**/node_modules/**",
            "**/__pycache__/**",
            "**/.venv/**",
            "**/venv/**",
            "**/.git/**",
            "**/dist/**",
            "**/build/**",
            "**/*.min.js",
            "**/*.min.css",
            "**/coverage/**",
            "**/.pytest_cache/**",
            "**/.mypy_cache/**",
            "**/htmlcov/**",
            "**/logs/**",
            "**/backups/**",
        ]

        all_excludes = default_excludes + (exclude_patterns or [])

        logger.info("Starting full codebase scan from %s", root_path)
        return self.scan_directory(
            root_path,
            recursive=True,
            exclude_patterns=all_excludes,
        )

    def get_high_severity_issues(
        self,
        result: AnalysisResult,
        min_confidence: float = 0.8,
    ) -> List[AnalysisIssue]:
        """Get high and critical severity issues with high confidence.

        Args:
            result: AnalysisResult to filter
            min_confidence: Minimum confidence threshold

        Returns:
            List of high/critical severity issues
        """
        from src.code_intelligence.base_analyzer import IssueSeverity

        return [
            issue
            for issue in result.issues
            if issue.severity in {IssueSeverity.HIGH, IssueSeverity.CRITICAL}
            and issue.confidence >= min_confidence
            and not issue.potential_false_positive
        ]

    def get_security_issues(self, result: AnalysisResult) -> List[AnalysisIssue]:
        """Get all security-related issues.

        Args:
            result: AnalysisResult to filter

        Returns:
            List of security issues
        """
        from src.code_intelligence.base_analyzer import IssueCategory

        return [
            issue for issue in result.issues if issue.category == IssueCategory.SECURITY
        ]

    def get_performance_issues(self, result: AnalysisResult) -> List[AnalysisIssue]:
        """Get all performance-related issues.

        Args:
            result: AnalysisResult to filter

        Returns:
            List of performance issues
        """
        from src.code_intelligence.base_analyzer import IssueCategory

        return [
            issue
            for issue in result.issues
            if issue.category == IssueCategory.PERFORMANCE
        ]

    def generate_report(self, result: AnalysisResult) -> Dict[str, Any]:
        """Generate a comprehensive scan report.

        Args:
            result: AnalysisResult to report on

        Returns:
            Dictionary with report data
        """
        from src.code_intelligence.base_analyzer import IssueCategory, IssueSeverity

        # Count by severity
        severity_counts = {sev.value: 0 for sev in IssueSeverity}
        for issue in result.issues:
            severity_counts[issue.severity.value] += 1

        # Count by category
        category_counts = {cat.value: 0 for cat in IssueCategory}
        for issue in result.issues:
            category_counts[issue.category.value] += 1

        # Count definite vs potential false positives
        definite_issues = [i for i in result.issues if not i.potential_false_positive]
        potential_fp = [i for i in result.issues if i.potential_false_positive]

        # Top files by issue count
        file_counts: Dict[str, int] = {}
        for issue in result.issues:
            file_counts[issue.file_path] = file_counts.get(issue.file_path, 0) + 1
        top_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "summary": {
                "files_analyzed": result.files_analyzed,
                "total_issues": len(result.issues),
                "definite_issues": len(definite_issues),
                "potential_false_positives": len(potential_fp),
                "analysis_time_ms": result.analysis_time_ms,
                "errors": len(result.errors),
            },
            "by_severity": severity_counts,
            "by_category": category_counts,
            "by_language": result.issues_by_language,
            "top_files": [{"file": f, "issues": c} for f, c in top_files],
            "high_priority": [
                issue.to_dict() for issue in self.get_high_severity_issues(result)[:20]
            ],
            "security_issues": [
                issue.to_dict() for issue in self.get_security_issues(result)[:20]
            ],
        }

    def get_scan_history(self) -> List[Dict[str, Any]]:
        """Get history of scans performed.

        Returns:
            List of scan history entries
        """
        return self._scan_history.copy()


# Convenience functions for quick scanning
def scan_file(file_path: str) -> AnalysisResult:
    """Quick scan a single file.

    Args:
        file_path: Path to the file

    Returns:
        AnalysisResult with detected issues
    """
    scanner = CodebaseScanner()
    return scanner.scan_file(Path(file_path))


def scan_directory(directory: str, recursive: bool = True) -> AnalysisResult:
    """Quick scan a directory.

    Args:
        directory: Path to the directory
        recursive: Whether to scan subdirectories

    Returns:
        AnalysisResult with detected issues
    """
    scanner = CodebaseScanner()
    return scanner.scan_directory(Path(directory), recursive=recursive)


def scan_codebase(root_path: Optional[str] = None) -> AnalysisResult:
    """Quick scan the entire codebase.

    Args:
        root_path: Optional root path

    Returns:
        AnalysisResult with all detected issues
    """
    scanner = CodebaseScanner()
    path = Path(root_path) if root_path else None
    return scanner.scan_codebase(path)


# Create singleton for easy access
codebase_scanner = CodebaseScanner()
