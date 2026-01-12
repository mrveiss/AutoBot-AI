# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Type definitions for codebase analytics parallel processing.

Issue #711: Dataclasses for thread-safe file analysis results.
These immutable types enable parallel file processing by returning
results instead of mutating shared state.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FileAnalysisResult:
    """
    Immutable result from analyzing a single file.

    Issue #711: Replaces direct dict mutation for thread-safe parallel processing.
    All fields are computed during analysis; no shared state mutation occurs.

    This dataclass is returned by analyzers and collected during parallel
    processing, then aggregated in a single pass after all files complete.

    Attributes:
        file_path: Absolute path to the analyzed file
        relative_path: Path relative to project root
        extension: File extension (lowercase, e.g., ".py")
        file_category: Category from file_categorization (code, config, docs, etc.)
        was_processed: True if file was actually analyzed
        was_skipped_unchanged: True if skipped due to incremental indexing
        file_hash: SHA-256 hash for incremental indexing
        functions: List of function definitions found
        classes: List of class definitions found
        imports: List of import statements
        hardcodes: List of hardcoded values detected
        problems: List of code quality problems
        technical_debt: List of technical debt items
        line_count: Total lines in file
        code_lines: Lines containing code
        comment_lines: Lines containing comments
        docstring_lines: Lines in docstrings
        blank_lines: Empty/whitespace lines
        documentation_lines: Lines in doc files
        analyzer_type: Type of analyzer used ("python", "js", "doc", None)
        stat_key: Stats key to increment ("python_files", etc.)
    """

    # Identity
    file_path: Path
    relative_path: str
    extension: str
    file_category: str

    # Processing status
    was_processed: bool = False
    was_skipped_unchanged: bool = False
    file_hash: str = ""

    # Analysis results (immutable after creation)
    functions: List[Dict[str, Any]] = field(default_factory=list)
    classes: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    hardcodes: List[Dict[str, Any]] = field(default_factory=list)
    problems: List[Dict[str, Any]] = field(default_factory=list)
    technical_debt: List[Dict[str, Any]] = field(default_factory=list)

    # Line counts
    line_count: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    docstring_lines: int = 0
    blank_lines: int = 0
    documentation_lines: int = 0

    # Analyzer metadata (for stats tracking)
    analyzer_type: Optional[str] = None  # "python", "js", "doc", None
    stat_key: Optional[str] = None  # "python_files", "javascript_files", etc.

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format for backward compatibility.

        Issue #711: Allows existing code to work with FileAnalysisResult
        by converting to the original dict format.
        """
        return {
            "functions": self.functions,
            "classes": self.classes,
            "imports": self.imports,
            "hardcodes": self.hardcodes,
            "problems": self.problems,
            "technical_debt": self.technical_debt,
            "line_count": self.line_count,
            "code_lines": self.code_lines,
            "comment_lines": self.comment_lines,
            "docstring_lines": self.docstring_lines,
            "blank_lines": self.blank_lines,
            "documentation_lines": self.documentation_lines,
        }


@dataclass
class AnalysisBatchResult:
    """
    Result from processing a batch of files.

    Issue #711: Aggregates multiple FileAnalysisResult objects for batch operations.
    Used for tracking progress and errors during parallel processing.
    """

    results: List[FileAnalysisResult] = field(default_factory=list)
    files_processed: int = 0
    files_skipped: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)

    def add_result(self, result: FileAnalysisResult) -> None:
        """Add a result to the batch and update counters."""
        self.results.append(result)
        if result.was_skipped_unchanged:
            self.files_skipped += 1
        elif result.was_processed:
            self.files_processed += 1

    def add_error(self, file_path: str, error: str) -> None:
        """Record an error during file processing."""
        self.errors.append({"file_path": file_path, "error": error})


@dataclass
class ParallelProcessingStats:
    """
    Statistics from parallel file processing.

    Issue #711: Tracks performance metrics for parallel processing
    to enable comparison with sequential mode.
    """

    total_files: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_errored: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    concurrency_limit: int = 0

    @property
    def elapsed_seconds(self) -> float:
        """Total elapsed time in seconds."""
        if self.end_time > 0 and self.start_time > 0:
            return self.end_time - self.start_time
        return 0.0

    @property
    def files_per_second(self) -> float:
        """Processing rate in files per second."""
        elapsed = self.elapsed_seconds
        if elapsed > 0:
            return self.files_processed / elapsed
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/reporting."""
        return {
            "total_files": self.total_files,
            "files_processed": self.files_processed,
            "files_skipped": self.files_skipped,
            "files_errored": self.files_errored,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "files_per_second": round(self.files_per_second, 1),
            "concurrency_limit": self.concurrency_limit,
        }
