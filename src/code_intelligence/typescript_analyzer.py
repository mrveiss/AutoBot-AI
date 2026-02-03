# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
TypeScript/JavaScript Code Analyzer

Issue #386: Analyzes TypeScript and JavaScript files for:
- Performance issues (blocking I/O, sync operations)
- Security vulnerabilities (eval, XSS, injection)
- Anti-patterns and best practice violations
- Code quality issues

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import logging
import re
from pathlib import Path
from typing import Dict, FrozenSet, List, Set, Tuple

from src.code_intelligence.base_analyzer import (
    AnalysisIssue,
    BaseLanguageAnalyzer,
    IssueCategory,
    IssueSeverity,
    Language,
    is_in_comment,
)

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for TypeScript file extensions
_TYPESCRIPT_EXTENSIONS: FrozenSet[str] = frozenset({".ts", ".tsx", ".mts", ".cts"})


# =============================================================================
# Pattern Definitions with Confidence Scores
# =============================================================================

# HIGH CONFIDENCE - Definite issues (0.9+)
BLOCKING_IO_PATTERNS_HIGH: Dict[str, Tuple[str, float, str]] = {
    # Sync file operations
    r"fs\.readFileSync\s*\(": (
        "Use fs.promises.readFile() or fs/promises for async file reading",
        0.95,
        "PERF001",
    ),
    r"fs\.writeFileSync\s*\(": (
        "Use fs.promises.writeFile() for async file writing",
        0.95,
        "PERF002",
    ),
    r"fs\.appendFileSync\s*\(": (
        "Use fs.promises.appendFile() for async appending",
        0.95,
        "PERF003",
    ),
    r"fs\.existsSync\s*\(": (
        "Use fs.promises.access() or fs.promises.stat() for async existence checks",
        0.92,
        "PERF004",
    ),
    r"fs\.statSync\s*\(": (
        "Use fs.promises.stat() for async file stats",
        0.92,
        "PERF005",
    ),
    r"fs\.mkdirSync\s*\(": (
        "Use fs.promises.mkdir() for async directory creation",
        0.90,
        "PERF006",
    ),
    r"fs\.readdirSync\s*\(": (
        "Use fs.promises.readdir() for async directory listing",
        0.92,
        "PERF007",
    ),
    r"fs\.unlinkSync\s*\(": (
        "Use fs.promises.unlink() for async file deletion",
        0.90,
        "PERF008",
    ),
    r"fs\.copyFileSync\s*\(": (
        "Use fs.promises.copyFile() for async file copying",
        0.90,
        "PERF009",
    ),
    r"fs\.renameSync\s*\(": (
        "Use fs.promises.rename() for async renaming",
        0.90,
        "PERF010",
    ),
    # Sync child process
    r"child_process\.execSync\s*\(": (
        "Use child_process.exec() with promisify or spawn for async execution",
        0.95,
        "PERF011",
    ),
    r"child_process\.spawnSync\s*\(": (
        "Use child_process.spawn() for async process spawning",
        0.95,
        "PERF012",
    ),
    r"execSync\s*\(": (
        "Use exec() with promisify or spawn for async command execution",
        0.93,
        "PERF013",
    ),
    r"spawnSync\s*\(": (
        "Use spawn() for async process spawning",
        0.93,
        "PERF014",
    ),
    # Blocking crypto
    r"crypto\.pbkdf2Sync\s*\(": (
        "Use crypto.pbkdf2() (async) for non-blocking key derivation",
        0.95,
        "PERF015",
    ),
    r"crypto\.scryptSync\s*\(": (
        "Use crypto.scrypt() (async) for non-blocking key derivation",
        0.95,
        "PERF016",
    ),
    r"crypto\.randomFillSync\s*\(": (
        "Use crypto.randomFill() for async random generation",
        0.90,
        "PERF017",
    ),
    # Network sync
    r"XMLHttpRequest\(\)": (
        "Use fetch() API or axios for async HTTP requests",
        0.85,
        "PERF018",
    ),
}

# SECURITY - High severity vulnerabilities
SECURITY_PATTERNS_CRITICAL: Dict[str, Tuple[str, float, str]] = {
    r"\beval\s*\(": (
        "eval() can execute arbitrary code - use JSON.parse() or safer alternatives",
        0.98,
        "SEC001",
    ),
    r"new\s+Function\s*\(": (
        "new Function() is similar to eval() - avoid dynamic code generation",
        0.95,
        "SEC002",
    ),
    r"setTimeout\s*\(\s*['\"`]": (
        "setTimeout with string argument acts like eval() - use function instead",
        0.92,
        "SEC003",
    ),
    r"setInterval\s*\(\s*['\"`]": (
        "setInterval with string argument acts like eval() - use function instead",
        0.92,
        "SEC004",
    ),
    r"\.innerHTML\s*=": (
        "innerHTML can lead to XSS - use textContent or sanitize input",
        0.88,
        "SEC005",
    ),
    r"\.outerHTML\s*=": (
        "outerHTML can lead to XSS - use safer DOM manipulation",
        0.88,
        "SEC006",
    ),
    r"document\.write\s*\(": (
        "document.write() can enable XSS attacks - use DOM manipulation",
        0.90,
        "SEC007",
    ),
    r"document\.writeln\s*\(": (
        "document.writeln() can enable XSS attacks - use DOM manipulation",
        0.90,
        "SEC008",
    ),
    # SQL Injection patterns
    r"\$\{.*\}.*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)": (
        "Possible SQL injection - use parameterized queries",
        0.85,
        "SEC009",
    ),
    r"['\"`]\s*\+.*(?:SELECT|INSERT|UPDATE|DELETE)": (
        "String concatenation in SQL query - use parameterized queries",
        0.82,
        "SEC010",
    ),
    # Command injection
    r"exec\s*\([^)]*\$\{": (
        "Template literal in exec() - possible command injection",
        0.90,
        "SEC011",
    ),
    r"spawn\s*\([^)]*\$\{": (
        "Template literal in spawn() - possible command injection",
        0.88,
        "SEC012",
    ),
}

# SECURITY - Medium severity
SECURITY_PATTERNS_MEDIUM: Dict[str, Tuple[str, float, str]] = {
    r"localStorage\.setItem\s*\(": (
        "Consider security implications of storing sensitive data in localStorage",
        0.70,
        "SEC020",
    ),
    r"sessionStorage\.setItem\s*\(": (
        "Consider if sessionStorage is appropriate for this data",
        0.65,
        "SEC021",
    ),
    r"(?:password|secret|apiKey|api_key|token)\s*[=:]\s*['\"`][^'\"`]+['\"`]": (
        "Hardcoded credential detected - use environment variables",
        0.92,
        "SEC022",
    ),
    r"console\.(log|debug|info)\s*\(.*(?:password|secret|token|key)": (
        "Potential credential logging - remove before production",
        0.85,
        "SEC023",
    ),
    r"debugger\s*;": (
        "debugger statement should be removed before production",
        0.95,
        "SEC024",
    ),
}

# ANTI-PATTERNS - Code quality issues
ANTI_PATTERN_DEFINITIONS: Dict[str, Tuple[str, float, str, IssueCategory]] = {
    # Async anti-patterns
    r"await\s+.*\s+in\s+.*for\s*\(": (
        "await in for loop - consider Promise.all() for parallel execution",
        0.80,
        "ANTI001",
        IssueCategory.PERFORMANCE,
    ),
    r"for\s*\([^)]*\)\s*\{[^}]*await\s+": (
        "Sequential awaits in loop - consider Promise.all() for parallel execution",
        0.75,
        "ANTI002",
        IssueCategory.PERFORMANCE,
    ),
    r"\.then\s*\([^)]*\)\s*\.then\s*\([^)]*\)\s*\.then": (
        "Deeply nested .then() chains - consider async/await syntax",
        0.82,
        "ANTI003",
        IssueCategory.CODE_QUALITY,
    ),
    # Error handling
    r"catch\s*\([^)]*\)\s*\{\s*\}": (
        "Empty catch block silently swallows errors - handle or rethrow",
        0.95,
        "ANTI004",
        IssueCategory.RELIABILITY,
    ),
    r"catch\s*\([^)]*\)\s*\{\s*console\.log": (
        "Catch block only logs error - consider proper error handling",
        0.70,
        "ANTI005",
        IssueCategory.RELIABILITY,
    ),
    # Type issues (TypeScript specific)
    r":\s*any\b": (
        "Avoid 'any' type - use specific types for better type safety",
        0.65,
        "ANTI006",
        IssueCategory.CODE_QUALITY,
    ),
    r"as\s+any\b": (
        "Type assertion to 'any' bypasses type checking",
        0.70,
        "ANTI007",
        IssueCategory.CODE_QUALITY,
    ),
    r"@ts-ignore": (
        "@ts-ignore suppresses TypeScript errors - fix the underlying issue",
        0.80,
        "ANTI008",
        IssueCategory.CODE_QUALITY,
    ),
    r"@ts-nocheck": (
        "@ts-nocheck disables type checking for entire file",
        0.85,
        "ANTI009",
        IssueCategory.CODE_QUALITY,
    ),
    # Memory leaks
    r"addEventListener\s*\([^)]+\)(?![\s\S]*removeEventListener)": (
        "Event listener added - ensure cleanup with removeEventListener",
        0.60,
        "ANTI010",
        IssueCategory.RELIABILITY,
    ),
    r"setInterval\s*\((?![\s\S]*clearInterval)": (
        "setInterval without clearInterval - potential memory leak",
        0.70,
        "ANTI011",
        IssueCategory.RELIABILITY,
    ),
    r"setTimeout\s*\((?![\s\S]*clearTimeout)": (
        "Consider storing timeout ID for potential cleanup",
        0.50,
        "ANTI012",
        IssueCategory.BEST_PRACTICE,
    ),
    # Deprecated/problematic
    r"var\s+\w+\s*=": (
        "Use 'let' or 'const' instead of 'var' for block scoping",
        0.75,
        "ANTI013",
        IssueCategory.CODE_QUALITY,
    ),
    r"==(?!=)": (
        "Use === for strict equality comparison",
        0.70,
        "ANTI014",
        IssueCategory.CODE_QUALITY,
    ),
    r"!=(?!=)": (
        "Use !== for strict inequality comparison",
        0.70,
        "ANTI015",
        IssueCategory.CODE_QUALITY,
    ),
}

# SAFE PATTERNS - Known false positives to skip
SAFE_PATTERNS: Set[str] = {
    # Import/require statements
    "import",
    "require(",
    "from ",
    # Type definitions
    "interface ",
    "type ",
    ": string",
    ": number",
    ": boolean",
    # Comments
    "//",
    "/*",
    "* ",
    # Common safe patterns
    ".get(",  # HTTP client methods
    ".post(",
    ".put(",
    ".delete(",
    "router.",
    "app.",
    # Test patterns
    "describe(",
    "it(",
    "test(",
    "expect(",
    "jest.",
    "vitest.",
}


class TypeScriptAnalyzer(BaseLanguageAnalyzer):
    """Analyzer for TypeScript and JavaScript code.

    Detects performance issues, security vulnerabilities, and anti-patterns
    in TypeScript (.ts, .tsx) and JavaScript (.js, .jsx) files.
    """

    @property
    def supported_languages(self) -> Set[Language]:
        """Return languages this analyzer supports."""
        return {Language.TYPESCRIPT, Language.JAVASCRIPT}

    @property
    def analyzer_name(self) -> str:
        """Return the display name of this analyzer."""
        return "TypeScript/JavaScript Analyzer"

    def analyze_file(self, file_path: Path) -> List[AnalysisIssue]:
        """Analyze a TypeScript or JavaScript file."""
        if not self._load_file(file_path):
            return []

        language = (
            Language.TYPESCRIPT
            if file_path.suffix in _TYPESCRIPT_EXTENSIONS
            else Language.JAVASCRIPT
        )

        # Run all detection methods
        self._check_blocking_io(language)
        self._check_security_issues(language)
        self._check_anti_patterns(language)

        logger.debug(
            f"TypeScript Analyzer found {len(self.issues)} issues in {file_path}"
        )
        return self.issues

    def _should_skip_line(self, line: str, line_num: int) -> bool:
        """Check if line should be skipped (comment, import, etc.)."""
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            return True

        # Skip comments
        if (
            stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
        ):
            return True

        # Skip imports/requires
        if stripped.startswith("import ") or stripped.startswith("export "):
            return True
        if "require(" in stripped and ("=" in stripped or "const " in stripped):
            return True

        # Skip type definitions
        if stripped.startswith("interface ") or stripped.startswith("type "):
            return True

        return False

    def _check_blocking_io(self, language: Language) -> None:
        """Check for blocking I/O operations."""
        for line_num, line in enumerate(self.lines, start=1):
            if self._should_skip_line(line, line_num):
                continue

            for pattern, (
                recommendation,
                confidence,
                rule_id,
            ) in BLOCKING_IO_PATTERNS_HIGH.items():
                if re.search(pattern, line, re.IGNORECASE):
                    # Extract the matched function call
                    match = re.search(pattern, line)
                    if match:
                        self.issues.append(
                            AnalysisIssue(
                                issue_id=self._generate_issue_id("blocking"),
                                category=IssueCategory.PERFORMANCE,
                                severity=IssueSeverity.HIGH,
                                language=language,
                                file_path=self.file_path,
                                line_start=line_num,
                                line_end=line_num,
                                column_start=match.start(),
                                column_end=match.end(),
                                title=f"Blocking I/O: {match.group().strip()}",
                                description="Synchronous operation detected that blocks the event loop",
                                recommendation=recommendation,
                                current_code=line.strip(),
                                confidence=confidence,
                                potential_false_positive=confidence < 0.9,
                                false_positive_reason=""
                                if confidence >= 0.9
                                else "Context may justify sync operation",
                                rule_id=rule_id,
                                tags=["blocking-io", "performance", "async"],
                            )
                        )

    def _create_security_issue(
        self,
        line_num: int,
        line: str,
        match,
        pattern_data: Tuple,
        language: Language,
        is_critical: bool,
    ) -> "AnalysisIssue":
        """Create security issue from pattern match (Issue #315 - extracted helper)."""
        recommendation, confidence, rule_id = pattern_data
        if is_critical:
            severity = (
                IssueSeverity.CRITICAL if confidence >= 0.90 else IssueSeverity.HIGH
            )
            title = f"Security Issue: {rule_id}"
            description = "Potential security vulnerability detected"
            false_positive = confidence < 0.85
            fp_reason = "" if confidence >= 0.85 else "May be intentional or sanitized"
            tags = ["security", "vulnerability"]
        else:
            severity = IssueSeverity.MEDIUM
            title = f"Security Concern: {rule_id}"
            description = "Potential security concern detected"
            false_positive = True
            fp_reason = "May be appropriate depending on context"
            tags = ["security", "review-needed"]

        return AnalysisIssue(
            issue_id=self._generate_issue_id("security"),
            category=IssueCategory.SECURITY,
            severity=severity,
            language=language,
            file_path=self.file_path,
            line_start=line_num,
            line_end=line_num,
            column_start=match.start(),
            column_end=match.end(),
            title=title,
            description=description,
            recommendation=recommendation,
            current_code=line.strip(),
            confidence=confidence,
            potential_false_positive=false_positive,
            false_positive_reason=fp_reason,
            rule_id=rule_id,
            tags=tags,
        )

    def _check_security_pattern_on_line(
        self,
        line_num: int,
        line: str,
        pattern: str,
        pattern_data: Tuple,
        language: Language,
        is_critical: bool,
    ) -> None:
        """Check single security pattern on a line (Issue #315 - extracted helper)."""
        match = re.search(pattern, line, re.IGNORECASE)
        if not match:
            return
        if is_in_comment(self.source_code, line_num, language):
            return
        issue = self._create_security_issue(
            line_num, line, match, pattern_data, language, is_critical
        )
        self.issues.append(issue)

    def _check_security_issues(self, language: Language) -> None:
        """Check for security vulnerabilities (Issue #315 - refactored)."""
        for line_num, line in enumerate(self.lines, start=1):
            if self._should_skip_line(line, line_num):
                continue

            for pattern, pattern_data in SECURITY_PATTERNS_CRITICAL.items():
                self._check_security_pattern_on_line(
                    line_num, line, pattern, pattern_data, language, is_critical=True
                )

            for pattern, pattern_data in SECURITY_PATTERNS_MEDIUM.items():
                self._check_security_pattern_on_line(
                    line_num, line, pattern, pattern_data, language, is_critical=False
                )

    def _get_antipattern_severity(
        self, category: "IssueCategory", confidence: float
    ) -> "IssueSeverity":
        """Determine severity based on category and confidence (Issue #315 - extracted helper)."""
        if category == IssueCategory.SECURITY:
            return IssueSeverity.HIGH
        if category == IssueCategory.RELIABILITY:
            return IssueSeverity.MEDIUM
        if confidence >= 0.80:
            return IssueSeverity.MEDIUM
        return IssueSeverity.LOW

    def _create_antipattern_issue(
        self, line_num: int, line: str, match, pattern_data: Tuple, language: Language
    ) -> "AnalysisIssue":
        """Create an AnalysisIssue from anti-pattern match (Issue #315 - extracted helper)."""
        recommendation, confidence, rule_id, category = pattern_data
        severity = self._get_antipattern_severity(category, confidence)
        return AnalysisIssue(
            issue_id=self._generate_issue_id("antipattern"),
            category=category,
            severity=severity,
            language=language,
            file_path=self.file_path,
            line_start=line_num,
            line_end=line_num,
            column_start=match.start(),
            column_end=match.end(),
            title=f"Anti-pattern: {rule_id}",
            description="Code pattern that may indicate an issue",
            recommendation=recommendation,
            current_code=line.strip(),
            confidence=confidence,
            potential_false_positive=confidence < 0.75,
            false_positive_reason=""
            if confidence >= 0.75
            else "Context may make this acceptable",
            rule_id=rule_id,
            tags=["anti-pattern", category.value],
        )

    def _check_antipattern_on_line(
        self,
        line_num: int,
        line: str,
        pattern: str,
        pattern_data: Tuple,
        language: Language,
    ) -> None:
        """Check single anti-pattern on a line (Issue #315 - extracted helper)."""
        match = re.search(pattern, line, re.IGNORECASE)
        if not match:
            return
        if is_in_comment(self.source_code, line_num, language):
            return
        issue = self._create_antipattern_issue(
            line_num, line, match, pattern_data, language
        )
        self.issues.append(issue)

    def _check_anti_patterns(self, language: Language) -> None:
        """Check for anti-patterns and code quality issues (Issue #315 - refactored)."""
        for line_num, line in enumerate(self.lines, start=1):
            if self._should_skip_line(line, line_num):
                continue

            for pattern, pattern_data in ANTI_PATTERN_DEFINITIONS.items():
                self._check_antipattern_on_line(
                    line_num, line, pattern, pattern_data, language
                )

    def _check_await_in_loops(self, language: Language) -> None:
        """Advanced check for sequential awaits that could be parallelized."""
        # This is a more sophisticated check that looks at the AST structure
        # For now, we rely on the regex patterns above


# Create singleton instance for easy importing
typescript_analyzer = TypeScriptAnalyzer()
