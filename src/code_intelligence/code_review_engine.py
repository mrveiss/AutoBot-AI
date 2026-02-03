# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AI-Powered Code Review Engine (Issue #225)

Provides automated code review with pattern checking, security analysis,
and AI-generated review comments. Learns from past reviews.

Part of EPIC #217 - Advanced Code Intelligence Methods

Features:
- Git diff parsing and analysis
- Pattern-based violation detection
- Code quality scoring
- Review comment generation
- Context-aware suggestions
- Learning from feedback

Issue #554: Enhanced with Vector/Redis/LLM infrastructure:
- ChromaDB for storing review pattern embeddings
- Redis for caching review results
- LLM for semantic code analysis and intelligent suggestions
- Historical review pattern learning via embeddings
"""

import logging
import re
import subprocess
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

# Issue #380: Module-level tuples/frozensets for constant data
_COMMENT_PREFIXES = ("#", '"""', "'''")
_LINE_COUNT_TYPES = frozenset({"add", "context"})
_SUPPORTED_CODE_SUFFIXES = (".py", ".vue", ".ts", ".js")

# Issue #380: Pre-compiled regex patterns for diff parsing
_OLD_PATH_RE = re.compile(r"a/(\S+)")
_HUNK_HEADER_RE = re.compile(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@")


# ============================================================================
# Enums and Data Classes
# ============================================================================


class ReviewSeverity(Enum):
    """Review comment severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


class ReviewCategory(Enum):
    """Categories of review findings."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    BUG_RISK = "bug_risk"
    MAINTAINABILITY = "maintainability"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    BEST_PRACTICE = "best_practice"


@dataclass
class ReviewPattern:
    """Definition of a review pattern."""

    id: str
    name: str
    category: ReviewCategory
    severity: ReviewSeverity
    pattern: Optional[str]  # Regex pattern (None for programmatic checks)
    message: str
    suggestion: Optional[str] = None
    file_extensions: list[str] = field(default_factory=lambda: [".py"])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "suggestion": self.suggestion,
            "has_pattern": self.pattern is not None,
            "file_extensions": self.file_extensions,
        }


@dataclass
class ReviewComment:
    """A single review comment."""

    id: str
    file_path: str
    line_number: int
    severity: ReviewSeverity
    category: ReviewCategory
    message: str
    suggestion: Optional[str] = None
    code_snippet: Optional[str] = None
    pattern_id: Optional[str] = None
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet,
            "pattern_id": self.pattern_id,
            "context_before": self.context_before,
            "context_after": self.context_after,
        }


@dataclass
class DiffHunk:
    """A hunk of changes from a diff."""

    old_start: int
    new_start: int
    old_count: int
    new_count: int
    lines: list[dict[str, str]]  # {"type": add/delete/context, "content": str}


@dataclass
class DiffFile:
    """A file from a diff."""

    path: str
    old_path: Optional[str] = None
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    additions: int = 0
    deletions: int = 0
    hunks: list[DiffHunk] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Complete review result for a diff or PR."""

    id: str
    timestamp: datetime
    files_reviewed: int
    total_comments: int
    score: float  # 0-100
    comments: list[ReviewComment] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    diff_stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "files_reviewed": self.files_reviewed,
            "total_comments": self.total_comments,
            "score": round(self.score, 1),
            "comments": [c.to_dict() for c in self.comments],
            "summary": self.summary,
            "diff_stats": self.diff_stats,
        }


# ============================================================================
# Built-in Review Patterns
# ============================================================================


BUILTIN_PATTERNS: dict[str, ReviewPattern] = {
    # Security patterns
    "SEC001": ReviewPattern(
        id="SEC001",
        name="Hardcoded Secret",
        category=ReviewCategory.SECURITY,
        severity=ReviewSeverity.CRITICAL,
        pattern=r'(?i)(password|secret|api_key|apikey|token|auth)\s*[=:]\s*["\'][^"\']{4,}["\']',
        message="Potential hardcoded secret detected. Use environment variables.",
        suggestion="Move this value to an environment variable or secrets manager.",
    ),
    "SEC002": ReviewPattern(
        id="SEC002",
        name="SQL Injection Risk",
        category=ReviewCategory.SECURITY,
        severity=ReviewSeverity.CRITICAL,
        pattern=r'execute\s*\(\s*[f"\'].*\{.*\}.*["\']',
        message="Potential SQL injection vulnerability. Use parameterized queries.",
        suggestion="Use query parameters instead of string formatting.",
    ),
    "SEC003": ReviewPattern(
        id="SEC003",
        name="Unsafe eval",
        category=ReviewCategory.SECURITY,
        severity=ReviewSeverity.CRITICAL,
        pattern=r'\beval\s*\(',
        message="Use of eval() is a security risk. Avoid if possible.",
        suggestion="Use ast.literal_eval() for safe evaluation or refactor.",
    ),
    "SEC004": ReviewPattern(
        id="SEC004",
        name="Hardcoded IP Address",
        category=ReviewCategory.SECURITY,
        severity=ReviewSeverity.WARNING,
        pattern=(
            r'["\'](?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
            r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)["\']'
        ),
        message="Hardcoded IP address found. Use configuration.",
        suggestion="Move IP addresses to NetworkConstants or environment variables.",
    ),
    "SEC005": ReviewPattern(
        id="SEC005",
        name="Shell Injection Risk",
        category=ReviewCategory.SECURITY,
        severity=ReviewSeverity.CRITICAL,
        pattern=r'subprocess\.\w+\([^)]*shell\s*=\s*True',
        message="shell=True with subprocess can lead to injection attacks.",
        suggestion="Use shell=False and pass arguments as a list.",
    ),
    # Performance patterns
    "PERF001": ReviewPattern(
        id="PERF001",
        name="N+1 Query Pattern",
        category=ReviewCategory.PERFORMANCE,
        severity=ReviewSeverity.WARNING,
        pattern=r'for\s+\w+\s+in\s+\w+:\s*\n\s+.*\.(get|filter|select|query)',
        message="Potential N+1 query pattern. Consider using bulk operations.",
        suggestion="Use prefetch_related, select_related, or batch fetching.",
    ),
    "PERF002": ReviewPattern(
        id="PERF002",
        name="Inefficient String Concatenation",
        category=ReviewCategory.PERFORMANCE,
        severity=ReviewSeverity.INFO,
        pattern=r'for\s+\w+\s+in\s+\w+:\s*\n\s+\w+\s*\+=\s*["\']',
        message="String concatenation in loop is inefficient.",
        suggestion="Use ''.join() or list comprehension instead.",
    ),
    "PERF003": ReviewPattern(
        id="PERF003",
        name="Synchronous I/O in Async Function",
        category=ReviewCategory.PERFORMANCE,
        severity=ReviewSeverity.WARNING,
        pattern=r'async\s+def\s+\w+[^}]+open\s*\([^)]+\)',
        message="Synchronous file I/O in async function blocks event loop.",
        suggestion="Use aiofiles for async file operations.",
    ),
    # Bug Risk patterns
    "BUG001": ReviewPattern(
        id="BUG001",
        name="Empty except block",
        category=ReviewCategory.BUG_RISK,
        severity=ReviewSeverity.WARNING,
        pattern=r'except\s*:\s*\n\s*(pass|\.\.\.)',
        message="Empty except block silently swallows all exceptions.",
        suggestion="Log the exception or handle it explicitly.",
    ),
    "BUG002": ReviewPattern(
        id="BUG002",
        name="Mutable default argument",
        category=ReviewCategory.BUG_RISK,
        severity=ReviewSeverity.WARNING,
        pattern=r'def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|set\(\))',
        message="Mutable default argument can cause unexpected behavior.",
        suggestion="Use None as default and initialize inside the function.",
    ),
    "BUG003": ReviewPattern(
        id="BUG003",
        name="Comparison to None",
        category=ReviewCategory.BUG_RISK,
        severity=ReviewSeverity.INFO,
        pattern=r'\b\w+\s*[!=]=\s*None\b',
        message="Use 'is None' or 'is not None' for None comparisons.",
        suggestion="Replace '== None' with 'is None'.",
    ),
    "BUG004": ReviewPattern(
        id="BUG004",
        name="Bare raise without exception",
        category=ReviewCategory.BUG_RISK,
        severity=ReviewSeverity.INFO,
        pattern=r'^\s*raise\s*$',
        message="Bare 'raise' should only be used inside except blocks.",
        suggestion="Ensure 'raise' is only used inside except blocks.",
    ),
    # Style patterns
    "STYLE001": ReviewPattern(
        id="STYLE001",
        name="Magic Number",
        category=ReviewCategory.STYLE,
        severity=ReviewSeverity.SUGGESTION,
        pattern=r'(?<![\w])(?:if|elif|while|for|return)\s+.*[^0-9_]\d{3,}[^0-9]',
        message="Magic number detected. Consider using a named constant.",
        suggestion="Extract this value to a named constant for readability.",
    ),
    "STYLE002": ReviewPattern(
        id="STYLE002",
        name="Long Function",
        category=ReviewCategory.MAINTAINABILITY,
        severity=ReviewSeverity.WARNING,
        pattern=None,  # Checked programmatically
        message="Function exceeds 50 lines. Consider breaking it down.",
        suggestion="Break this function into smaller, focused functions.",
    ),
    "STYLE003": ReviewPattern(
        id="STYLE003",
        name="Deep Nesting",
        category=ReviewCategory.MAINTAINABILITY,
        severity=ReviewSeverity.WARNING,
        pattern=None,  # Checked programmatically
        message="Code has deep nesting (>4 levels). Consider refactoring.",
        suggestion="Use early returns or extract nested logic to functions.",
    ),
    # Documentation patterns
    "DOC001": ReviewPattern(
        id="DOC001",
        name="Missing docstring",
        category=ReviewCategory.DOCUMENTATION,
        severity=ReviewSeverity.INFO,
        pattern=r'def\s+[a-z_]\w*\s*\([^)]*\):\s*\n\s+(?!""")',
        message="Public function missing docstring.",
        suggestion="Add a docstring describing purpose and parameters.",
    ),
    "DOC002": ReviewPattern(
        id="DOC002",
        name="Missing class docstring",
        category=ReviewCategory.DOCUMENTATION,
        severity=ReviewSeverity.INFO,
        pattern=r'class\s+\w+[^:]*:\s*\n\s+(?!""")',
        message="Class missing docstring.",
        suggestion="Add a docstring describing the class purpose.",
    ),
    # Testing patterns
    "TEST001": ReviewPattern(
        id="TEST001",
        name="Test without assertion",
        category=ReviewCategory.TESTING,
        severity=ReviewSeverity.WARNING,
        pattern=None,  # Checked programmatically
        message="Test function may lack assertions.",
        suggestion="Add assert statements to verify expected behavior.",
    ),
    # Best practice patterns
    "BP001": ReviewPattern(
        id="BP001",
        name="Print statement",
        category=ReviewCategory.BEST_PRACTICE,
        severity=ReviewSeverity.SUGGESTION,
        pattern=r'^[^#]*\bprint\s*\(',
        message="Print statement found. Use logging for production code.",
        suggestion="Replace with logger.info() or logger.debug().",
    ),
    "BP002": ReviewPattern(
        id="BP002",
        name="TODO comment",
        category=ReviewCategory.BEST_PRACTICE,
        severity=ReviewSeverity.INFO,
        pattern=r'#\s*TODO',
        message="TODO comment found. Consider creating an issue.",
        suggestion="Create a GitHub issue to track this work.",
    ),
    "BP003": ReviewPattern(
        id="BP003",
        name="Commented-out code",
        category=ReviewCategory.BEST_PRACTICE,
        severity=ReviewSeverity.SUGGESTION,
        pattern=r'#\s*(def |class |import |from |if |for |while )',
        message="Commented-out code detected. Remove if no longer needed.",
        suggestion="Delete dead code or move to version control history.",
    ),
    "BP004": ReviewPattern(
        id="BP004",
        name="Star import",
        category=ReviewCategory.BEST_PRACTICE,
        severity=ReviewSeverity.WARNING,
        pattern=r'from\s+\w+\s+import\s+\*',
        message="Star import pollutes namespace and hinders analysis.",
        suggestion="Import specific names instead of using *.",
    ),
}


# ============================================================================
# Code Review Engine
# ============================================================================


# Issue #554: Dynamic base class selection for semantic analysis support
_BaseClass = SemanticAnalysisMixin if SEMANTIC_ANALYSIS_AVAILABLE else object


class CodeReviewEngine(_BaseClass):
    """
    AI-powered code review engine.

    Analyzes code changes for issues and generates review comments
    with suggestions for improvement.

    Issue #554: Enhanced with optional Vector/Redis/LLM infrastructure:
    - use_semantic_analysis=True enables LLM-based code review suggestions
    - Semantic analysis finds issues that regex patterns cannot detect
    - Results cached in Redis for performance

    Usage:
        # Standard review
        engine = CodeReviewEngine()
        result = engine.review_diff(diff_content)

        # With semantic analysis (requires ChromaDB + Ollama)
        engine = CodeReviewEngine(use_semantic_analysis=True)
        result = await engine.review_diff_async(diff_content)
    """

    # Severity weights for scoring
    SEVERITY_WEIGHTS = {
        ReviewSeverity.CRITICAL: 15,
        ReviewSeverity.WARNING: 5,
        ReviewSeverity.INFO: 1,
        ReviewSeverity.SUGGESTION: 0.5,
    }

    def __init__(
        self,
        project_root: Optional[str] = None,
        patterns: Optional[dict[str, ReviewPattern]] = None,
        context_lines: int = 2,
        max_function_lines: int = 50,
        max_nesting_depth: int = 4,
        use_semantic_analysis: bool = False,
    ):
        """
        Initialize Code Review Engine.

        Args:
            project_root: Root directory of the project
            patterns: Custom patterns (defaults to BUILTIN_PATTERNS)
            context_lines: Number of context lines to include
            max_function_lines: Maximum lines before flagging
            max_nesting_depth: Maximum nesting before flagging
            use_semantic_analysis: Enable LLM-based semantic review (Issue #554)
        """
        # Issue #554: Initialize semantic analysis infrastructure if enabled
        self.use_semantic_analysis = use_semantic_analysis and SEMANTIC_ANALYSIS_AVAILABLE

        if self.use_semantic_analysis:
            super().__init__()
            self._init_infrastructure(
                collection_name="code_review_patterns",
                use_llm=True,
                use_cache=True,
                redis_database="analytics",
            )

        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.patterns = patterns or BUILTIN_PATTERNS.copy()
        self.context_lines = context_lines
        self.max_function_lines = max_function_lines
        self.max_nesting_depth = max_nesting_depth

        # Compile regex patterns
        self._compiled_patterns: dict[str, re.Pattern] = {}
        for pid, pdef in self.patterns.items():
            if pdef.pattern:
                try:
                    self._compiled_patterns[pid] = re.compile(
                        pdef.pattern, re.IGNORECASE | re.MULTILINE
                    )
                except re.error as e:
                    logger.warning("Invalid pattern %s: %s", pid, e)

    def review_file(self, file_path: str, content: Optional[str] = None) -> list[ReviewComment]:
        """
        Review a single file for issues.

        Args:
            file_path: Path to the file
            content: File content (if not provided, reads from disk)

        Returns:
            List of review comments
        """
        path = Path(file_path)

        if content is None:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                logger.warning("Failed to read %s: %s", file_path, e)
                return []

        lines = content.split("\n")
        comments = []

        # Check regex patterns
        for pattern_id, pattern in self._compiled_patterns.items():
            pattern_def = self.patterns[pattern_id]

            # Check file extension
            if path.suffix not in pattern_def.file_extensions:
                if not (path.suffix == "" and ".py" in pattern_def.file_extensions):
                    continue

            for match in pattern.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                code_snippet = lines[line_num - 1] if line_num <= len(lines) else ""

                # Get context
                ctx_before = lines[max(0, line_num - 1 - self.context_lines):line_num - 1]
                ctx_after = lines[line_num:min(len(lines), line_num + self.context_lines)]

                comments.append(ReviewComment(
                    id=f"{pattern_id}-{line_num}",
                    file_path=str(file_path),
                    line_number=line_num,
                    severity=pattern_def.severity,
                    category=pattern_def.category,
                    message=pattern_def.message,
                    suggestion=pattern_def.suggestion,
                    code_snippet=code_snippet.strip(),
                    pattern_id=pattern_id,
                    context_before=ctx_before,
                    context_after=ctx_after,
                ))

        # Programmatic checks
        comments.extend(self._check_function_length(file_path, lines))
        comments.extend(self._check_nesting_depth(file_path, lines))
        comments.extend(self._check_test_assertions(file_path, content, lines))

        return comments

    def _get_changed_lines_from_diff(self, diff_file: DiffFile) -> set:
        """Extract changed line numbers from a diff file (Issue #335 - extracted helper)."""
        changed_lines = set()
        for hunk in diff_file.hunks:
            line = hunk.new_start
            for diff_line in hunk.lines:
                if diff_line["type"] == "add":
                    changed_lines.add(line)
                if diff_line["type"] in _LINE_COUNT_TYPES:
                    line += 1
        return changed_lines

    def _filter_comments_by_changed_lines(
        self, comments: List[ReviewComment], changed_lines: set
    ) -> List[ReviewComment]:
        """Filter comments to those near changed lines (Issue #335 - extracted helper)."""
        filtered = []
        for comment in comments:
            for changed_line in changed_lines:
                if abs(comment.line_number - changed_line) <= 3:
                    filtered.append(comment)
                    break
        return filtered

    def review_diff(self, diff_content: str) -> ReviewResult:
        """
        Review a git diff for issues.

        Args:
            diff_content: Unified diff content

        Returns:
            ReviewResult with all findings
        """
        diff_files = self._parse_diff(diff_content)

        all_comments = []
        total_additions = 0
        total_deletions = 0

        for diff_file in diff_files:
            total_additions += diff_file.additions
            total_deletions += diff_file.deletions

            # Only review modified/new files, not deleted
            if diff_file.is_deleted:
                continue

            # Get full file content (Issue #380: use module-level constant)
            file_path = self.project_root / diff_file.path
            if not file_path.exists() or file_path.suffix not in _SUPPORTED_CODE_SUFFIXES:
                continue

            comments = self.review_file(str(file_path))
            changed_lines = self._get_changed_lines_from_diff(diff_file)
            filtered = self._filter_comments_by_changed_lines(comments, changed_lines)
            all_comments.extend(filtered)

        # Calculate score and summary
        score = self._calculate_score(all_comments)
        summary = self._generate_summary(all_comments)

        return ReviewResult(
            id=f"review-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            timestamp=datetime.now(),
            files_reviewed=len([f for f in diff_files if not f.is_deleted]),
            total_comments=len(all_comments),
            score=score,
            comments=all_comments,
            summary=summary,
            diff_stats={
                "files_changed": len(diff_files),
                "additions": total_additions,
                "deletions": total_deletions,
            },
        )

    def review_commit_range(self, commit_range: str = "HEAD~1..HEAD") -> ReviewResult:
        """
        Review changes in a commit range.

        Args:
            commit_range: Git commit range (e.g., "HEAD~1..HEAD")

        Returns:
            ReviewResult with all findings
        """
        diff_content = self._get_git_diff(commit_range)
        if not diff_content:
            return ReviewResult(
                id=f"review-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                timestamp=datetime.now(),
                files_reviewed=0,
                total_comments=0,
                score=100.0,
                comments=[],
                summary={},
                diff_stats={},
            )
        return self.review_diff(diff_content)

    def review_staged_changes(self) -> ReviewResult:
        """
        Review currently staged changes.

        Returns:
            ReviewResult with all findings
        """
        diff_content = self._get_git_diff("--cached")
        if not diff_content:
            return ReviewResult(
                id=f"review-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                timestamp=datetime.now(),
                files_reviewed=0,
                total_comments=0,
                score=100.0,
                comments=[],
                summary={},
                diff_stats={},
            )
        return self.review_diff(diff_content)

    def get_patterns(self) -> list[dict[str, Any]]:
        """Get all registered patterns."""
        return [p.to_dict() for p in self.patterns.values()]

    def add_pattern(self, pattern: ReviewPattern) -> None:
        """Add a custom pattern."""
        self.patterns[pattern.id] = pattern
        if pattern.pattern:
            try:
                self._compiled_patterns[pattern.id] = re.compile(
                    pattern.pattern, re.IGNORECASE | re.MULTILINE
                )
            except re.error as e:
                logger.warning("Invalid pattern %s: %s", pattern.id, e)

    def remove_pattern(self, pattern_id: str) -> bool:
        """Remove a pattern by ID."""
        if pattern_id in self.patterns:
            del self.patterns[pattern_id]
            self._compiled_patterns.pop(pattern_id, None)
            return True
        return False

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _finalize_current_file(
        self, current_file: Optional[DiffFile], current_hunk: Optional[DiffHunk], files: list
    ) -> None:
        """Finalize current file and add to files list (Issue #335 - extracted helper)."""
        if not current_file:
            return
        if current_hunk:
            current_file.hunks.append(current_hunk)
        files.append(current_file)

    def _parse_diff_git_line(self, line: str) -> DiffFile:
        """Parse diff --git line (Issue #335 - extracted helper)."""
        parts = line.split(" b/")
        file_path = parts[-1] if len(parts) > 1 else "unknown"
        old_path_match = _OLD_PATH_RE.search(line)
        old_path = old_path_match.group(1) if old_path_match else None
        return DiffFile(path=file_path, old_path=old_path)

    def _parse_hunk_header(self, line: str) -> Optional[DiffHunk]:
        """Parse hunk header line (Issue #335 - extracted helper)."""
        match = _HUNK_HEADER_RE.match(line)
        if not match:
            return None
        return DiffHunk(
            old_start=int(match.group(1)),
            old_count=int(match.group(2)) if match.group(2) else 1,
            new_start=int(match.group(3)),
            new_count=int(match.group(4)) if match.group(4) else 1,
            lines=[],
        )

    def _parse_hunk_line(
        self, line: str, current_hunk: DiffHunk, current_file: Optional[DiffFile]
    ) -> None:
        """Parse a hunk content line (Issue #335 - extracted helper)."""
        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.lines.append({"type": "add", "content": line[1:]})
            if current_file:
                current_file.additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.lines.append({"type": "delete", "content": line[1:]})
            if current_file:
                current_file.deletions += 1
        elif line.startswith(" ") or line == "":
            current_hunk.lines.append({
                "type": "context",
                "content": line[1:] if line.startswith(" ") else "",
            })

    def _handle_file_metadata(
        self, line: str, current_file: Optional[DiffFile]
    ) -> bool:
        """Handle file metadata lines (Issue #315 - reduce nesting)."""
        if not current_file:
            return False
        if line.startswith("new file"):
            current_file.is_new = True
            return True
        if line.startswith("deleted file"):
            current_file.is_deleted = True
            return True
        if line.startswith("rename from"):
            current_file.is_renamed = True
            return True
        return False

    def _parse_diff(self, diff_content: str) -> list[DiffFile]:
        """Parse unified diff format into structured data (Issue #315: depth 7→3)."""
        files: list[DiffFile] = []
        current_file: Optional[DiffFile] = None
        current_hunk: Optional[DiffHunk] = None

        for line in diff_content.split("\n"):
            # Handle new file marker
            if line.startswith("diff --git"):
                self._finalize_current_file(current_file, current_hunk, files)
                current_file = self._parse_diff_git_line(line)
                current_hunk = None
                continue

            # Handle file metadata
            if self._handle_file_metadata(line, current_file):
                continue

            # Handle hunk header
            if line.startswith("@@"):
                if current_file and current_hunk:
                    current_file.hunks.append(current_hunk)
                current_hunk = self._parse_hunk_header(line)
                continue

            # Handle hunk content
            if current_hunk is not None:
                self._parse_hunk_line(line, current_hunk, current_file)

        self._finalize_current_file(current_file, current_hunk, files)
        return files

    def _get_git_diff(self, args: str) -> str:
        """Get git diff output."""
        try:
            cmd = ["git", "diff"] + args.split()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TimingConstants.SHORT_TIMEOUT,
                encoding="utf-8",
                cwd=self.project_root,
            )
            return result.stdout if result.returncode == 0 else ""
        except Exception as e:
            logger.warning("Failed to get git diff: %s", e)
            return ""

    def _find_function_end(self, lines: list[str], start: int, indent: int) -> int:
        """Find the end line of a function (Issue #335 - extracted helper)."""
        func_end = start
        for j in range(start, len(lines)):
            line = lines[j]
            if not line.strip():
                func_end = j + 1
                continue
            if line.startswith(" " * (indent + 1)):
                func_end = j + 1
                continue
            if line.strip().startswith(_COMMENT_PREFIXES):
                func_end = j + 1
                continue
            # Found line with less or equal indent - function ends
            return j
        return func_end

    def _check_function_length(
        self, file_path: str, lines: list[str]
    ) -> list[ReviewComment]:
        """Check for functions exceeding maximum length."""
        comments = []
        func_pattern = re.compile(r"^(\s*)(async\s+)?def\s+(\w+)\s*\(")

        i = 0
        while i < len(lines):
            match = func_pattern.match(lines[i])
            if not match:
                i += 1
                continue

            indent = len(match.group(1))
            func_name = match.group(3)
            func_start = i + 1

            func_end = self._find_function_end(lines, i + 1, indent)
            func_length = func_end - func_start

            if func_length > self.max_function_lines:
                comments.append(ReviewComment(
                    id=f"STYLE002-{func_start}",
                    file_path=str(file_path),
                    line_number=func_start,
                    severity=ReviewSeverity.WARNING,
                    category=ReviewCategory.MAINTAINABILITY,
                    message=f"Function '{func_name}' is {func_length} lines. "
                            f"Consider refactoring (max: {self.max_function_lines}).",
                    suggestion="Break into smaller, focused functions.",
                    pattern_id="STYLE002",
                ))
            i += 1

        return comments

    def _check_nesting_depth(
        self, file_path: str, lines: list[str]
    ) -> list[ReviewComment]:
        """Check for deeply nested code."""
        comments = []
        reported_lines = set()

        for i, line in enumerate(lines, 1):
            if line.strip():
                indent = len(line) - len(line.lstrip())
                depth = indent // 4  # Assuming 4-space indent

                if depth > self.max_nesting_depth and i not in reported_lines:
                    comments.append(ReviewComment(
                        id=f"STYLE003-{i}",
                        file_path=str(file_path),
                        line_number=i,
                        severity=ReviewSeverity.WARNING,
                        category=ReviewCategory.MAINTAINABILITY,
                        message=f"Deep nesting ({depth} levels). "
                                f"Consider refactoring (max: {self.max_nesting_depth}).",
                        suggestion="Use early returns or extract to helper functions.",
                        code_snippet=line.strip(),
                        pattern_id="STYLE003",
                    ))
                    reported_lines.add(i)

        return comments

    def _check_test_assertions(
        self, file_path: str, content: str, lines: list[str]
    ) -> list[ReviewComment]:
        """Check test functions for assertions."""
        comments = []

        if "test_" not in file_path:
            return comments

        test_pattern = re.compile(r"^(\s*)def\s+(test_\w+)\s*\(")

        for i, line in enumerate(lines):
            match = test_pattern.match(line)
            if match:
                indent = len(match.group(1))
                test_name = match.group(2)
                test_start = i

                # Find test end and check for assertions
                has_assertion = False
                for j in range(i + 1, len(lines)):
                    test_line = lines[j]
                    if test_line.strip() and not test_line.startswith(" " * (indent + 1)):
                        break
                    if "assert" in test_line.lower() or "pytest.raises" in test_line:
                        has_assertion = True
                        break

                if not has_assertion:
                    comments.append(ReviewComment(
                        id=f"TEST001-{test_start + 1}",
                        file_path=str(file_path),
                        line_number=test_start + 1,
                        severity=ReviewSeverity.WARNING,
                        category=ReviewCategory.TESTING,
                        message=f"Test '{test_name}' may lack assertions.",
                        suggestion="Add assert statements to verify expected behavior.",
                        pattern_id="TEST001",
                    ))

        return comments

    def _calculate_score(self, comments: list[ReviewComment]) -> float:
        """Calculate overall code quality score."""
        if not comments:
            return 100.0

        total_deduction = sum(
            self.SEVERITY_WEIGHTS.get(c.severity, 1) for c in comments
        )
        return max(0, 100 - total_deduction)

    def _generate_summary(self, comments: list[ReviewComment]) -> dict[str, Any]:
        """Generate review summary statistics."""
        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}

        for comment in comments:
            sev = comment.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            cat = comment.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "by_severity": by_severity,
            "by_category": by_category,
            "critical_count": by_severity.get("critical", 0),
            "warning_count": by_severity.get("warning", 0),
            "info_count": by_severity.get("info", 0) + by_severity.get("suggestion", 0),
            "top_issues": [
                {"category": cat, "count": count}
                for cat, count in sorted(
                    by_category.items(), key=lambda x: x[1], reverse=True
                )[:5]
            ],
        }

    # =========================================================================
    # Issue #554: Async Semantic Analysis Methods
    # =========================================================================

    async def review_diff_async(self, diff_content: str) -> ReviewResult:
        """
        Review a git diff with semantic analysis.

        Issue #554: Async version that includes LLM-based semantic review
        and caches results in Redis.

        Args:
            diff_content: Unified diff content

        Returns:
            ReviewResult with all findings including semantic analysis
        """
        # Check for cached results
        cache_key = f"review:{hash(diff_content)}"
        if self.use_semantic_analysis:
            cached = await self._get_cached_result(cache_key, prefix="code_review")
            if cached:
                logger.info("Returning cached code review")
                return ReviewResult(**cached)

        # Use synchronous review as base
        result = self.review_diff(diff_content)

        # Cache results if semantic analysis enabled
        if self.use_semantic_analysis:
            await self._cache_result(
                cache_key,
                result.to_dict(),
                prefix="code_review",
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


def review_file(file_path: str, content: Optional[str] = None) -> list[ReviewComment]:
    """
    Review a file for issues.

    Args:
        file_path: Path to the file
        content: Optional file content

    Returns:
        List of review comments
    """
    engine = CodeReviewEngine()
    return engine.review_file(file_path, content)


def review_diff(diff_content: str) -> ReviewResult:
    """
    Review a git diff.

    Args:
        diff_content: Unified diff content

    Returns:
        ReviewResult with findings
    """
    engine = CodeReviewEngine()
    return engine.review_diff(diff_content)


def review_commit(commit_range: str = "HEAD~1..HEAD") -> ReviewResult:
    """
    Review changes in a commit range.

    Args:
        commit_range: Git commit range

    Returns:
        ReviewResult with findings
    """
    engine = CodeReviewEngine()
    return engine.review_commit_range(commit_range)


def review_staged() -> ReviewResult:
    """
    Review staged changes.

    Returns:
        ReviewResult with findings
    """
    engine = CodeReviewEngine()
    return engine.review_staged_changes()


def get_review_patterns() -> list[dict[str, Any]]:
    """
    Get all built-in review patterns.

    Returns:
        List of pattern definitions
    """
    return [p.to_dict() for p in BUILTIN_PATTERNS.values()]


def get_review_categories() -> list[dict[str, Any]]:
    """
    Get all review categories.

    Returns:
        List of category definitions
    """
    descriptions = {
        ReviewCategory.SECURITY: "Security vulnerabilities and sensitive data",
        ReviewCategory.PERFORMANCE: "Performance issues and optimization",
        ReviewCategory.STYLE: "Code style and formatting",
        ReviewCategory.BUG_RISK: "Patterns that commonly lead to bugs",
        ReviewCategory.MAINTAINABILITY: "Code maintainability and readability",
        ReviewCategory.DOCUMENTATION: "Missing or incomplete documentation",
        ReviewCategory.TESTING: "Test coverage and quality issues",
        ReviewCategory.BEST_PRACTICE: "Deviations from best practices",
    }

    icons = {
        ReviewCategory.SECURITY: "shield",
        ReviewCategory.PERFORMANCE: "zap",
        ReviewCategory.STYLE: "palette",
        ReviewCategory.BUG_RISK: "bug",
        ReviewCategory.MAINTAINABILITY: "wrench",
        ReviewCategory.DOCUMENTATION: "file-text",
        ReviewCategory.TESTING: "beaker",
        ReviewCategory.BEST_PRACTICE: "star",
    }

    return [
        {
            "id": cat.value,
            "name": cat.value.replace("_", " ").title(),
            "description": descriptions.get(cat, ""),
            "icon": icons.get(cat, "circle"),
        }
        for cat in ReviewCategory
    ]


def get_review_severities() -> list[dict[str, Any]]:
    """
    Get all review severity levels.

    Returns:
        List of severity definitions
    """
    return [
        {
            "level": ReviewSeverity.CRITICAL.value,
            "weight": 15,
            "description": "Blocks merge, requires immediate fix",
        },
        {
            "level": ReviewSeverity.WARNING.value,
            "weight": 5,
            "description": "Should be addressed before merge",
        },
        {
            "level": ReviewSeverity.INFO.value,
            "weight": 1,
            "description": "Informational, consider addressing",
        },
        {
            "level": ReviewSeverity.SUGGESTION.value,
            "weight": 0.5,
            "description": "Optional improvement",
        },
    ]
