# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pre-commit Hook Analyzer

Analyzes code for issues that should be caught before commits including:
- Security issues (hardcoded credentials, API keys, private keys)
- Debug statements (console.log, print, debugger)
- Code quality issues (empty except blocks, magic numbers)
- Style issues (trailing whitespace, mixed tabs/spaces)
- Documentation issues (missing docstrings)

Part of Issue #223 - Git Pre-commit Hook Analyzer
Parent Epic: #217 - Advanced Code Intelligence
"""

import concurrent.futures
import logging
import re
import subprocess  # nosec B404 - controlled git process execution
import time
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CheckSeverity(Enum):
    """Severity levels for pre-commit checks."""

    BLOCK = "block"  # Prevents commit
    WARN = "warn"  # Shows warning but allows commit
    INFO = "info"  # Informational only


class CheckCategory(Enum):
    """Categories of pre-commit checks."""

    SECURITY = "security"
    QUALITY = "quality"
    STYLE = "style"
    DEBUG = "debug"
    DOCS = "docs"


@dataclass
class CheckDefinition:
    """Definition of a pre-commit check rule."""

    id: str
    name: str
    category: CheckCategory
    severity: CheckSeverity
    pattern: str
    description: str
    suggestion: str
    file_patterns: List[str] = field(default_factory=lambda: ["*"])
    enabled: bool = True
    multiline: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "severity": self.severity.value,
            "pattern": self.pattern,
            "description": self.description,
            "suggestion": self.suggestion,
            "file_patterns": self.file_patterns,
            "enabled": self.enabled,
        }


@dataclass
class CheckResult:
    """Result of a single check."""

    check_id: str
    name: str
    category: CheckCategory
    severity: CheckSeverity
    passed: bool
    message: str
    file_path: str = ""
    line: int = 0
    column: int = 0
    snippet: str = ""
    suggestion: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "check_id": self.check_id,
            "name": self.name,
            "category": self.category.value,
            "severity": self.severity.value,
            "passed": self.passed,
            "message": self.message,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "snippet": self.snippet,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass
class CommitCheckResult:
    """Result of checking files for commit."""

    passed: bool
    blocked: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    warnings: int
    infos: int
    duration_ms: float
    results: List[CheckResult]
    files_checked: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "warnings": self.warnings,
            "infos": self.infos,
            "duration_ms": self.duration_ms,
            "results": [r.to_dict() for r in self.results],
            "files_checked": self.files_checked,
        }


# Built-in check definitions
BUILTIN_CHECKS: Dict[str, CheckDefinition] = {
    # Security Checks
    "SEC001": CheckDefinition(
        id="SEC001",
        name="Hardcoded Password",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.BLOCK,
        pattern=r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']{4,}["\']',
        description="Detected hardcoded password",
        suggestion="Use environment variables or secrets manager",
        file_patterns=["*.py", "*.js", "*.ts", "*.json", "*.yaml", "*.yml"],
    ),
    "SEC002": CheckDefinition(
        id="SEC002",
        name="API Key Exposure",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.BLOCK,
        pattern=r'(?i)(api[_-]?key|apikey|secret[_-]?key)\s*[=:]\s*["\'][a-zA-Z0-9]{16,}["\']',
        description="Detected exposed API key",
        suggestion="Store API keys in environment variables",
        file_patterns=["*.py", "*.js", "*.ts", "*.json", "*.env"],
    ),
    "SEC003": CheckDefinition(
        id="SEC003",
        name="Private Key in Code",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.BLOCK,
        pattern=r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
        description="Private key detected in source file",
        suggestion="Never commit private keys - use key management service",
        file_patterns=["*"],
    ),
    "SEC004": CheckDefinition(
        id="SEC004",
        name="Hardcoded IP Address",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.WARN,
        pattern=r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
        description="Hardcoded IP address detected",
        suggestion="Use configuration or NetworkConstants for IP addresses",
        file_patterns=["*.py", "*.js", "*.ts"],
    ),
    "SEC005": CheckDefinition(
        id="SEC005",
        name="AWS Access Key",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.BLOCK,
        pattern=r"AKIA[0-9A-Z]{16}",
        description="AWS Access Key ID detected",
        suggestion="Use AWS credentials file or environment variables",
        file_patterns=["*"],
    ),
    "SEC006": CheckDefinition(
        id="SEC006",
        name="JWT Token",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.BLOCK,
        pattern=r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
        description="JWT token detected in source code",
        suggestion="Never commit JWT tokens - they should be dynamic",
        file_patterns=["*.py", "*.js", "*.ts", "*.json"],
    ),
    # Debug Checks
    "DBG001": CheckDefinition(
        id="DBG001",
        name="Console.log Statement",
        category=CheckCategory.DEBUG,
        severity=CheckSeverity.WARN,
        pattern=r"console\.(log|debug|info|warn)\s*\(",
        description="Console statement found",
        suggestion="Remove console statements before committing",
        file_patterns=["*.js", "*.ts", "*.vue"],
    ),
    "DBG002": CheckDefinition(
        id="DBG002",
        name="Print Statement",
        category=CheckCategory.DEBUG,
        severity=CheckSeverity.WARN,
        pattern=r"^\s*print\s*\(",
        description="Print statement found",
        suggestion="Replace with proper logging",
        file_patterns=["*.py"],
    ),
    "DBG003": CheckDefinition(
        id="DBG003",
        name="Debugger Statement",
        category=CheckCategory.DEBUG,
        severity=CheckSeverity.BLOCK,
        pattern=r"\bdebugger\b|import\s+pdb|pdb\.set_trace\(\)|breakpoint\(\)",
        description="Debugger statement found",
        suggestion="Remove debugger statements before committing",
        file_patterns=["*.py", "*.js", "*.ts"],
    ),
    "DBG004": CheckDefinition(
        id="DBG004",
        name="TODO/FIXME Comment",
        category=CheckCategory.DEBUG,
        severity=CheckSeverity.INFO,
        pattern=r"(?i)#\s*(TODO|FIXME|XXX|HACK|BUG):",
        description="TODO/FIXME comment found",
        suggestion="Consider addressing before committing",
        file_patterns=["*.py", "*.js", "*.ts", "*.vue"],
    ),
    # Quality Checks
    "QUA001": CheckDefinition(
        id="QUA001",
        name="Empty Except Block",
        category=CheckCategory.QUALITY,
        severity=CheckSeverity.WARN,
        pattern=r"except\s*(?:\w+\s*)?:\s*(?:pass|\.\.\.)\s*$",
        description="Empty exception handler found",
        suggestion="Add proper error handling or logging",
        file_patterns=["*.py"],
    ),
    "QUA002": CheckDefinition(
        id="QUA002",
        name="Bare Except",
        category=CheckCategory.QUALITY,
        severity=CheckSeverity.WARN,
        pattern=r"except\s*:",
        description="Bare except clause catches all exceptions",
        suggestion="Catch specific exception types",
        file_patterns=["*.py"],
    ),
    "QUA003": CheckDefinition(
        id="QUA003",
        name="Long Line",
        category=CheckCategory.QUALITY,
        severity=CheckSeverity.INFO,
        pattern=r"^.{121,}$",
        description="Line exceeds 120 characters",
        suggestion="Break line for readability",
        file_patterns=["*.py"],
    ),
    "QUA004": CheckDefinition(
        id="QUA004",
        name="Hardcoded Port",
        category=CheckCategory.QUALITY,
        severity=CheckSeverity.WARN,
        pattern=r"(?<![a-zA-Z_])port\s*[=:]\s*\d{4,5}(?![0-9])",
        description="Hardcoded port number detected",
        suggestion="Use NetworkConstants for port numbers",
        file_patterns=["*.py", "*.js", "*.ts"],
    ),
    # Style Checks
    "STY001": CheckDefinition(
        id="STY001",
        name="Trailing Whitespace",
        category=CheckCategory.STYLE,
        severity=CheckSeverity.INFO,
        pattern=r"[ \t]+$",
        description="Trailing whitespace detected",
        suggestion="Remove trailing whitespace",
        file_patterns=["*"],
    ),
    "STY002": CheckDefinition(
        id="STY002",
        name="Mixed Tabs and Spaces",
        category=CheckCategory.STYLE,
        severity=CheckSeverity.WARN,
        pattern=r"^(\t+ +| +\t+)",
        description="Mixed tabs and spaces in indentation",
        suggestion="Use consistent indentation (spaces recommended)",
        file_patterns=["*.py", "*.js", "*.ts"],
    ),
    "STY003": CheckDefinition(
        id="STY003",
        name="Multiple Blank Lines",
        category=CheckCategory.STYLE,
        severity=CheckSeverity.INFO,
        pattern=r"\n{4,}",
        description="More than 2 consecutive blank lines",
        suggestion="Reduce to maximum 2 blank lines",
        file_patterns=["*.py"],
        multiline=True,
    ),
    # Documentation Checks
    "DOC001": CheckDefinition(
        id="DOC001",
        name="Missing Function Docstring",
        category=CheckCategory.DOCS,
        severity=CheckSeverity.INFO,
        pattern=r'def\s+(?!_)[a-zA-Z_]\w*\s*\([^)]*\)\s*(?:->.*?)?:\s*\n(?!\s*["\'])',
        description="Public function missing docstring",
        suggestion="Add docstring describing function purpose",
        file_patterns=["*.py"],
        multiline=True,
    ),
    "DOC002": CheckDefinition(
        id="DOC002",
        name="Missing Class Docstring",
        category=CheckCategory.DOCS,
        severity=CheckSeverity.INFO,
        pattern=r'class\s+[A-Z]\w*\s*(?:\([^)]*\))?\s*:\s*\n(?!\s*["\'])',
        description="Class missing docstring",
        suggestion="Add docstring describing class purpose",
        file_patterns=["*.py"],
        multiline=True,
    ),
}


class PrecommitAnalyzer:
    """Analyzer for pre-commit checks."""

    def __init__(
        self,
        project_root: Optional[str] = None,
        checks: Optional[Dict[str, CheckDefinition]] = None,
        fast_mode: bool = False,
        parallel: bool = True,
        max_workers: int = 4,
    ):
        """Initialize analyzer with project root and check configuration."""
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.checks = checks if checks is not None else BUILTIN_CHECKS.copy()
        self.fast_mode = fast_mode
        self.parallel = parallel
        self.max_workers = max_workers
        self.results: List[CheckResult] = []

        # Expensive checks to skip in fast mode
        self.expensive_checks = {"DOC001", "DOC002", "QUA003", "STY003"}

    def get_staged_files(self) -> List[str]:
        """Get list of files staged for commit."""
        try:
            result = subprocess.run(  # nosec B607 - git command is safe
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                return [f for f in result.stdout.strip().split("\n") if f]
            return []
        except Exception as e:
            logger.warning("Failed to get staged files: %s", e)
            return []

    def get_file_content(self, filepath: str) -> Optional[str]:
        """Get content of a staged file."""
        try:
            # Try to get staged content first (what will be committed)
            result = subprocess.run(  # nosec B607 - git command is safe
                ["git", "show", f":{filepath}"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                return result.stdout

            # Fall back to file system
            path = self.project_root / filepath
            if path.exists():
                return path.read_text(encoding="utf-8")
            return None
        except Exception as e:
            logger.warning("Failed to read file %s: %s", filepath, e)
            return None

    def matches_file_pattern(self, filepath: str, patterns: List[str]) -> bool:
        """Check if filepath matches any of the patterns."""
        filename = Path(filepath).name
        for pattern in patterns:
            if pattern == "*":
                return True
            if fnmatch(filename, pattern) or fnmatch(filepath, pattern):
                return True
        return False

    def run_check(
        self, check: CheckDefinition, filepath: str, content: str
    ) -> List[CheckResult]:
        """Run a single check against file content."""
        results = []

        if not self.matches_file_pattern(filepath, check.file_patterns):
            return results

        try:
            flags = re.MULTILINE
            if check.multiline:
                flags |= re.DOTALL

            pattern = re.compile(check.pattern, flags)
            lines = content.split("\n")

            if check.multiline:
                self._run_multiline_check(
                    check, filepath, content, lines, pattern, results
                )
            else:
                self._run_singleline_check(check, filepath, lines, pattern, results)

        except re.error as e:
            logger.warning("Invalid regex in check %s: %s", check.id, e)

        return results

    def _run_multiline_check(
        self,
        check: CheckDefinition,
        filepath: str,
        content: str,
        lines: List[str],
        pattern: re.Pattern,
        results: List[CheckResult],
    ) -> None:
        """Run multiline pattern matching against entire file content. Issue #620."""
        for match in pattern.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            snippet = self._get_snippet(lines, line_num)
            results.append(
                self._create_check_result(check, filepath, line_num, snippet)
            )

    def _run_singleline_check(
        self,
        check: CheckDefinition,
        filepath: str,
        lines: List[str],
        pattern: re.Pattern,
        results: List[CheckResult],
    ) -> None:
        """Run single-line pattern matching against each line. Issue #620."""
        for i, line in enumerate(lines, 1):
            for match in pattern.finditer(line):
                snippet = self._get_snippet(lines, i)
                results.append(
                    self._create_check_result(
                        check, filepath, i, snippet, match.start() + 1
                    )
                )

    def _create_check_result(
        self,
        check: CheckDefinition,
        filepath: str,
        line_num: int,
        snippet: str,
        column: Optional[int] = None,
    ) -> CheckResult:
        """Create a CheckResult instance for a pattern match. Issue #620."""
        return CheckResult(
            check_id=check.id,
            name=check.name,
            category=check.category,
            severity=check.severity,
            passed=False,
            message=check.description,
            file_path=filepath,
            line=line_num,
            column=column,
            snippet=snippet,
            suggestion=check.suggestion,
        )

    def _get_snippet(self, lines: List[str], line_num: int, context: int = 2) -> str:
        """Get code snippet with context around the specified line."""
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)

        snippet_lines = []
        for i in range(start, end):
            prefix = ">" if i == line_num - 1 else " "
            snippet_lines.append(f"{prefix}{i + 1:4d}: {lines[i]}")

        return "\n".join(snippet_lines)

    def analyze_file(self, filepath: str) -> List[CheckResult]:
        """Analyze a single file for pre-commit issues."""
        content = self.get_file_content(filepath)
        if content is None:
            return []

        results = []
        active_checks = self._get_active_checks()

        for check in active_checks.values():
            check_results = self.run_check(check, filepath, content)
            results.extend(check_results)

        return results

    def _get_active_checks(self) -> Dict[str, CheckDefinition]:
        """Get checks that should be run."""
        active = {k: v for k, v in self.checks.items() if v.enabled}

        if self.fast_mode:
            active = {k: v for k, v in active.items() if k not in self.expensive_checks}

        return active

    def _analyze_files_parallel(self, files: List[str]) -> List[CheckResult]:
        """Analyze files in parallel (Issue #335 - extracted helper)."""
        all_results = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            future_to_file = {executor.submit(self.analyze_file, f): f for f in files}
            for future in concurrent.futures.as_completed(future_to_file):
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    logger.error("Error analyzing file: %s", e)
        return all_results

    def _analyze_files_sequential(self, files: List[str]) -> List[CheckResult]:
        """Analyze files sequentially (Issue #335 - extracted helper)."""
        all_results = []
        for filepath in files:
            results = self.analyze_file(filepath)
            all_results.extend(results)
        return all_results

    def analyze_files(self, files: List[str]) -> CommitCheckResult:
        """Analyze multiple files for pre-commit issues."""
        start_time = time.time()

        if self.parallel and len(files) > 1:
            all_results = self._analyze_files_parallel(files)
        else:
            all_results = self._analyze_files_sequential(files)

        self.results = all_results
        duration_ms = (time.time() - start_time) * 1000

        # Calculate statistics
        blocked = any(
            r.severity == CheckSeverity.BLOCK and not r.passed for r in all_results
        )
        warnings = sum(
            1 for r in all_results if r.severity == CheckSeverity.WARN and not r.passed
        )
        infos = sum(
            1 for r in all_results if r.severity == CheckSeverity.INFO and not r.passed
        )
        failed = sum(1 for r in all_results if not r.passed)

        active_checks = self._get_active_checks()
        total_checks = len(active_checks) * len(files)

        return CommitCheckResult(
            passed=not blocked,
            blocked=blocked,
            total_checks=total_checks,
            passed_checks=total_checks - failed,
            failed_checks=failed,
            warnings=warnings,
            infos=infos,
            duration_ms=round(duration_ms, 2),
            results=all_results,
            files_checked=files,
        )

    def analyze_staged(self) -> CommitCheckResult:
        """Analyze all staged files."""
        staged_files = self.get_staged_files()

        if not staged_files:
            # Return empty result if no staged files
            return CommitCheckResult(
                passed=True,
                blocked=False,
                total_checks=0,
                passed_checks=0,
                failed_checks=0,
                warnings=0,
                infos=0,
                duration_ms=0.0,
                results=[],
                files_checked=[],
            )

        return self.analyze_files(staged_files)

    def analyze_content(
        self, content: str, filepath: str = "untitled.py"
    ) -> List[CheckResult]:
        """Analyze arbitrary content."""
        results = []
        active_checks = self._get_active_checks()

        for check in active_checks.values():
            check_results = self.run_check(check, filepath, content)
            results.extend(check_results)

        return results

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of analysis results."""
        by_severity = {}
        by_category = {}

        for result in self.results:
            if not result.passed:
                sev = result.severity.value
                by_severity[sev] = by_severity.get(sev, 0) + 1

                cat = result.category.value
                by_category[cat] = by_category.get(cat, 0) + 1

        # Determine overall status
        blocked = by_severity.get("block", 0) > 0
        warnings = by_severity.get("warn", 0)

        return {
            "total_issues": len([r for r in self.results if not r.passed]),
            "by_severity": by_severity,
            "by_category": by_category,
            "blocked": blocked,
            "warnings": warnings,
            "files_analyzed": len(set(r.file_path for r in self.results)),
            "checks_run": len(self._get_active_checks()),
        }

    def enable_check(self, check_id: str) -> bool:
        """Enable a specific check."""
        if check_id in self.checks:
            self.checks[check_id].enabled = True
            return True
        return False

    def disable_check(self, check_id: str) -> bool:
        """Disable a specific check."""
        if check_id in self.checks:
            self.checks[check_id].enabled = False
            return True
        return False

    def add_custom_check(self, check: CheckDefinition) -> None:
        """Add a custom check."""
        self.checks[check.id] = check

    def get_checks(self) -> List[CheckDefinition]:
        """Get all registered checks."""
        return list(self.checks.values())

    def get_check(self, check_id: str) -> Optional[CheckDefinition]:
        """Get a specific check by ID."""
        return self.checks.get(check_id)


def analyze_precommit(
    directory: Optional[str] = None,
    fast_mode: bool = True,
    parallel: bool = True,
) -> Dict[str, Any]:
    """
    Convenience function to analyze staged files.

    Args:
        directory: Project root directory
        fast_mode: Skip expensive checks
        parallel: Use parallel processing

    Returns:
        Dictionary with results and summary
    """
    analyzer = PrecommitAnalyzer(
        project_root=directory,
        fast_mode=fast_mode,
        parallel=parallel,
    )
    result = analyzer.analyze_staged()

    return {
        "result": result.to_dict(),
        "summary": analyzer.get_summary(),
    }


def get_precommit_checks() -> List[Dict[str, Any]]:
    """Get all available pre-commit checks with descriptions."""
    return [check.to_dict() for check in BUILTIN_CHECKS.values()]


def get_check_categories() -> List[Dict[str, Any]]:
    """Get check categories with counts."""
    category_counts: Dict[str, Dict[str, int]] = {}

    for check in BUILTIN_CHECKS.values():
        cat = check.category.value
        if cat not in category_counts:
            category_counts[cat] = {"enabled": 0, "disabled": 0, "block": 0, "warn": 0}

        if check.enabled:
            category_counts[cat]["enabled"] += 1
        else:
            category_counts[cat]["disabled"] += 1

        category_counts[cat][check.severity.value] = (
            category_counts[cat].get(check.severity.value, 0) + 1
        )

    return [
        {
            "category": cat,
            "enabled": counts["enabled"],
            "disabled": counts["disabled"],
            "total": counts["enabled"] + counts["disabled"],
            "blocking_checks": counts.get("block", 0),
            "warning_checks": counts.get("warn", 0),
        }
        for cat, counts in category_counts.items()
    ]
