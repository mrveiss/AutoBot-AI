# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Analyzer Framework for Multi-Language Code Analysis

Issue #386: Provides abstract base class and common utilities for
analyzing code across multiple languages (Python, TypeScript, JavaScript,
Vue, Shell, YAML, etc.)

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Set

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex patterns for string literal extraction
_STRING_PATTERNS_PYTHON: List[Pattern] = [
    re.compile(r'"""[\s\S]*?"""'),
    re.compile(r"'''[\s\S]*?'''"),
    re.compile(r'"(?:[^"\\]|\\.)*"'),
    re.compile(r"'(?:[^'\\]|\\.)*'"),
]
_STRING_PATTERNS_JS_TS: List[Pattern] = [
    re.compile(r'"(?:[^"\\]|\\.)*"'),
    re.compile(r"'(?:[^'\\]|\\.)*'"),
    re.compile(r"`(?:[^`\\]|\\.)*`"),
]
_STRING_PATTERNS_SHELL: List[Pattern] = [
    re.compile(r'"(?:[^"\\]|\\.)*"'),
    re.compile(r"'[^']*'"),
]
_STRING_PATTERNS_DEFAULT: List[Pattern] = [
    re.compile(r'"(?:[^"\\]|\\.)*"'),
    re.compile(r"'(?:[^'\\]|\\.)*'"),
]


class Language(Enum):
    """Supported programming languages."""
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    VUE = "vue"
    SHELL = "shell"
    YAML = "yaml"
    JSON = "json"
    GO = "go"
    UNKNOWN = "unknown"


class IssueSeverity(Enum):
    """Unified severity levels across all analyzers."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueCategory(Enum):
    """Categories of issues that can be detected."""
    PERFORMANCE = "performance"
    SECURITY = "security"
    CODE_QUALITY = "code_quality"
    ANTI_PATTERN = "anti_pattern"
    BEST_PRACTICE = "best_practice"
    MAINTAINABILITY = "maintainability"
    RELIABILITY = "reliability"


@dataclass
class AnalysisIssue:
    """Unified issue format for all language analyzers."""

    # Core identification (required)
    issue_id: str
    category: IssueCategory
    severity: IssueSeverity
    language: Language

    # Location (required)
    file_path: str
    line_start: int
    line_end: int

    # Description (required)
    title: str
    description: str
    recommendation: str

    # Location (optional)
    column_start: int = 0
    column_end: int = 0

    # Code context (optional)
    current_code: str = ""
    suggested_fix: str = ""

    # Confidence and false positive handling (Issue #385)
    confidence: float = 1.0
    potential_false_positive: bool = False
    false_positive_reason: str = ""

    # Additional metadata (optional)
    rule_id: str = ""
    documentation_url: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "issue_id": self.issue_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "language": self.language.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "column_start": self.column_start,
            "column_end": self.column_end,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "current_code": self.current_code,
            "suggested_fix": self.suggested_fix,
            "confidence": self.confidence,
            "potential_false_positive": self.potential_false_positive,
            "false_positive_reason": self.false_positive_reason,
            "rule_id": self.rule_id,
            "documentation_url": self.documentation_url,
            "tags": self.tags,
            "metadata": self.metadata,
        }


@dataclass
class AnalysisResult:
    """Result of analyzing a file or codebase."""

    files_analyzed: int = 0
    issues: List[AnalysisIssue] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Statistics by category
    issues_by_severity: Dict[str, int] = field(default_factory=dict)
    issues_by_category: Dict[str, int] = field(default_factory=dict)
    issues_by_language: Dict[str, int] = field(default_factory=dict)

    # Performance metrics
    analysis_time_ms: float = 0

    def add_issue(self, issue: AnalysisIssue) -> None:
        """Add an issue and update statistics."""
        self.issues.append(issue)

        # Update severity counts
        severity = issue.severity.value
        self.issues_by_severity[severity] = self.issues_by_severity.get(severity, 0) + 1

        # Update category counts
        category = issue.category.value
        self.issues_by_category[category] = self.issues_by_category.get(category, 0) + 1

        # Update language counts
        language = issue.language.value
        self.issues_by_language[language] = self.issues_by_language.get(language, 0) + 1

    def get_high_confidence_issues(self, min_confidence: float = 0.8) -> List[AnalysisIssue]:
        """Get issues with confidence above threshold."""
        return [i for i in self.issues if i.confidence >= min_confidence]

    def get_definite_issues(self) -> List[AnalysisIssue]:
        """Get issues that are definitely NOT false positives."""
        return [i for i in self.issues if not i.potential_false_positive]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "files_analyzed": self.files_analyzed,
            "total_issues": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "errors": self.errors,
            "issues_by_severity": self.issues_by_severity,
            "issues_by_category": self.issues_by_category,
            "issues_by_language": self.issues_by_language,
            "analysis_time_ms": self.analysis_time_ms,
        }


# Language detection by file extension
EXTENSION_TO_LANGUAGE: Dict[str, Language] = {
    ".py": Language.PYTHON,
    ".pyi": Language.PYTHON,
    ".pyw": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".mts": Language.TYPESCRIPT,
    ".cts": Language.TYPESCRIPT,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".vue": Language.VUE,
    ".sh": Language.SHELL,
    ".bash": Language.SHELL,
    ".zsh": Language.SHELL,
    ".yaml": Language.YAML,
    ".yml": Language.YAML,
    ".json": Language.JSON,
    ".go": Language.GO,
}


def detect_language(file_path: Path) -> Language:
    """Detect programming language from file extension."""
    suffix = file_path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix, Language.UNKNOWN)


class BaseLanguageAnalyzer(ABC):
    """Abstract base class for language-specific analyzers.

    All language analyzers should inherit from this class and implement
    the abstract methods for their specific language.
    """

    def __init__(self):
        self.issues: List[AnalysisIssue] = []
        self.file_path: str = ""
        self.source_code: str = ""
        self.lines: List[str] = []
        self._issue_counter: int = 0

    @property
    @abstractmethod
    def supported_languages(self) -> Set[Language]:
        """Return set of languages this analyzer supports."""
        pass

    @property
    @abstractmethod
    def analyzer_name(self) -> str:
        """Return human-readable name of this analyzer."""
        pass

    @abstractmethod
    def analyze_file(self, file_path: Path) -> List[AnalysisIssue]:
        """Analyze a single file and return list of issues.

        Args:
            file_path: Path to the file to analyze

        Returns:
            List of AnalysisIssue objects found in the file
        """
        pass

    def supports_language(self, language: Language) -> bool:
        """Check if this analyzer supports the given language."""
        return language in self.supported_languages

    def supports_file(self, file_path: Path) -> bool:
        """Check if this analyzer can process the given file."""
        language = detect_language(file_path)
        return self.supports_language(language)

    def _generate_issue_id(self, prefix: str = "") -> str:
        """Generate unique issue ID."""
        self._issue_counter += 1
        analyzer_prefix = self.analyzer_name.lower().replace(" ", "_")
        return f"{analyzer_prefix}_{prefix}_{self._issue_counter}"

    def _get_line(self, line_number: int) -> str:
        """Get source code line by 1-based line number."""
        if 1 <= line_number <= len(self.lines):
            return self.lines[line_number - 1]
        return ""

    def _get_lines(self, start: int, end: int) -> str:
        """Get source code lines from start to end (1-based, inclusive)."""
        if start < 1:
            start = 1
        if end > len(self.lines):
            end = len(self.lines)
        return "\n".join(self.lines[start - 1:end])

    def _load_file(self, file_path: Path) -> bool:
        """Load file content for analysis."""
        try:
            self.file_path = str(file_path)
            self.source_code = file_path.read_text(encoding="utf-8")
            self.lines = self.source_code.splitlines()
            self.issues = []
            self._issue_counter = 0
            return True
        except Exception as e:
            logger.error("Failed to load file %s: %s", file_path, e)
            return False


class MultiLanguageAnalyzer:
    """Coordinator for running multiple language-specific analyzers.

    This class manages a collection of language analyzers and can analyze
    entire codebases by delegating to the appropriate analyzer for each file.
    """

    def __init__(self):
        self.analyzers: List[BaseLanguageAnalyzer] = []
        self._analyzer_by_language: Dict[Language, List[BaseLanguageAnalyzer]] = {}

    def register_analyzer(self, analyzer: BaseLanguageAnalyzer) -> None:
        """Register a language analyzer."""
        self.analyzers.append(analyzer)

        # Index by language for fast lookup
        for language in analyzer.supported_languages:
            if language not in self._analyzer_by_language:
                self._analyzer_by_language[language] = []
            self._analyzer_by_language[language].append(analyzer)

        logger.info(
            f"Registered analyzer: {analyzer.analyzer_name} "
            f"for languages: {[l.value for l in analyzer.supported_languages]}"
        )

    def get_analyzers_for_file(self, file_path: Path) -> List[BaseLanguageAnalyzer]:
        """Get all analyzers that can process the given file."""
        language = detect_language(file_path)
        return self._analyzer_by_language.get(language, [])

    def analyze_file(self, file_path: Path) -> AnalysisResult:
        """Analyze a single file with all applicable analyzers."""
        result = AnalysisResult()

        if not file_path.exists():
            result.errors.append(f"File not found: {file_path}")
            return result

        analyzers = self.get_analyzers_for_file(file_path)
        if not analyzers:
            language = detect_language(file_path)
            if language != Language.UNKNOWN:
                result.errors.append(
                    f"No analyzer registered for language: {language.value}"
                )
            return result

        result.files_analyzed = 1

        for analyzer in analyzers:
            try:
                issues = analyzer.analyze_file(file_path)
                for issue in issues:
                    result.add_issue(issue)
            except Exception as e:
                result.errors.append(
                    f"Analyzer {analyzer.analyzer_name} failed on {file_path}: {e}"
                )

        return result

    def _collect_files_to_analyze(
        self,
        directory: Path,
        recursive: bool,
        exclude_patterns: Optional[List[str]],
    ) -> List[Path]:
        """Collect files to analyze after applying exclusion patterns (Issue #665: extracted helper)."""
        # Default exclusions
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
        ]
        all_excludes = set((exclude_patterns or []) + default_excludes)

        pattern = "**/*" if recursive else "*"
        files_to_analyze = []

        for file_path in directory.glob(pattern):
            if not file_path.is_file():
                continue

            # Check exclusions
            excluded = any(file_path.match(exclude) for exclude in all_excludes)
            if excluded:
                continue

            # Check if we have an analyzer for this file
            if self.get_analyzers_for_file(file_path):
                files_to_analyze.append(file_path)

        return files_to_analyze

    def _aggregate_file_results(
        self, result: "AnalysisResult", file_result: "AnalysisResult"
    ) -> None:
        """Aggregate file analysis results into overall result (Issue #665: extracted helper)."""
        result.files_analyzed += file_result.files_analyzed
        result.errors.extend(file_result.errors)
        for issue in file_result.issues:
            result.add_issue(issue)

    def analyze_directory(
        self,
        directory: Path,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None,
    ) -> AnalysisResult:
        """Analyze all files in a directory.

        Args:
            directory: Root directory to analyze
            recursive: Whether to recurse into subdirectories
            exclude_patterns: Glob patterns to exclude (e.g., ["**/node_modules/**"])

        Returns:
            AnalysisResult with all issues found
        """
        import time
        start_time = time.time()

        result = AnalysisResult()
        files_to_analyze = self._collect_files_to_analyze(
            directory, recursive, exclude_patterns
        )

        logger.info("Analyzing %d files in %s", len(files_to_analyze), directory)

        for file_path in files_to_analyze:
            file_result = self.analyze_file(file_path)
            self._aggregate_file_results(result, file_result)

        result.analysis_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Analysis complete: {result.files_analyzed} files, "
            f"{len(result.issues)} issues, "
            f"{result.analysis_time_ms:.2f}ms"
        )

        return result

    def get_supported_languages(self) -> Set[Language]:
        """Get all languages supported by registered analyzers."""
        return set(self._analyzer_by_language.keys())

    def get_analyzer_info(self) -> List[Dict[str, Any]]:
        """Get information about registered analyzers."""
        return [
            {
                "name": a.analyzer_name,
                "languages": [lang.value for lang in a.supported_languages],
            }
            for a in self.analyzers
        ]


# Utility functions for pattern matching across languages

def find_pattern_in_code(
    source: str,
    pattern: str,
    flags: int = 0,
) -> List[Dict[str, Any]]:
    """Find all occurrences of a regex pattern in source code.

    Returns list of dicts with: line_number, column, match, context
    """
    matches = []
    lines = source.splitlines()

    for line_num, line in enumerate(lines, start=1):
        for match in re.finditer(pattern, line, flags):
            matches.append({
                "line_number": line_num,
                "column": match.start(),
                "match": match.group(),
                "context": line.strip(),
            })

    return matches


def is_in_comment(source: str, line_number: int, language: Language) -> bool:
    """Check if a line is inside a comment for the given language."""
    lines = source.splitlines()
    if line_number < 1 or line_number > len(lines):
        return False

    line = lines[line_number - 1].strip()

    if language == Language.PYTHON:
        return line.startswith("#") or line.startswith('"""') or line.startswith("'''")
    elif language in (Language.TYPESCRIPT, Language.JAVASCRIPT, Language.GO):
        return line.startswith("//") or line.startswith("/*") or line.startswith("*")
    elif language == Language.SHELL:
        return line.startswith("#")
    elif language == Language.VUE:
        return line.startswith("<!--") or line.startswith("//") or line.startswith("/*")

    return False


def extract_string_literals(source: str, language: Language) -> List[str]:
    """Extract all string literals from source code."""
    strings = []

    # Issue #380: Use pre-compiled patterns based on language
    if language == Language.PYTHON:
        compiled_patterns = _STRING_PATTERNS_PYTHON
    elif language in (Language.TYPESCRIPT, Language.JAVASCRIPT, Language.VUE):
        compiled_patterns = _STRING_PATTERNS_JS_TS
    elif language == Language.SHELL:
        compiled_patterns = _STRING_PATTERNS_SHELL
    else:
        compiled_patterns = _STRING_PATTERNS_DEFAULT

    for compiled_pattern in compiled_patterns:
        strings.extend(compiled_pattern.findall(source))

    return strings
