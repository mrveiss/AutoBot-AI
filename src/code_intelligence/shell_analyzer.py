# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shell Script Analyzer

Issue #386: Analyzes shell scripts (.sh, .bash, .zsh) for:
- Security vulnerabilities (command injection, unquoted variables)
- Best practices (error handling, variable quoting)
- Code quality issues (deprecated syntax, portability)

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from src.code_intelligence.base_analyzer import (
    AnalysisIssue,
    BaseLanguageAnalyzer,
    IssueCategory,
    IssueSeverity,
    Language,
)

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for dangerous shell commands
_DANGEROUS_COMMANDS = frozenset({"rm", "mv", "cp", "chmod", "chown", "mkdir", "rmdir", "cd"})

# Issue #380: Pre-compiled regex patterns for set options checking
_SET_E_RE = re.compile(r"set\s+-[a-z]*e")
_SET_U_RE = re.compile(r"set\s+-[a-z]*u")
_SET_PIPEFAIL_RE = re.compile(r"set\s+-o\s+pipefail")
_SET_EUO_PIPEFAIL_RE = re.compile(r"set\s+-euo\s+pipefail")


# =============================================================================
# Security Patterns - Critical
# =============================================================================

SECURITY_PATTERNS_CRITICAL: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # Command injection
    r"\beval\s+[\"']?\$": (
        "eval with variable expansion is extremely dangerous - avoid eval or sanitize input",
        0.98,
        "SHELL-SEC001",
        IssueSeverity.CRITICAL,
    ),
    r"\beval\s+\$\{": (
        "eval with parameter expansion is dangerous - consider safer alternatives",
        0.98,
        "SHELL-SEC002",
        IssueSeverity.CRITICAL,
    ),
    r"`\$[^`]+`": (
        "Backtick command substitution with variables - use $() and quote variables",
        0.85,
        "SHELL-SEC003",
        IssueSeverity.HIGH,
    ),
    # Removed SHELL-SEC004 - too many false positives from legitimate $(command "$var") usage
    # Variable expansion inside command substitution is normal in shell scripts
    # Unquoted variables in dangerous contexts
    r"\brm\s+-rf?\s+\$[^{\"]": (
        "Unquoted variable in rm command - use \"$var\" to prevent word splitting",
        0.95,
        "SHELL-SEC005",
        IssueSeverity.CRITICAL,
    ),
    r"\brm\s+-rf?\s+\$\{[^}]+\}(?!\")": (
        "Unquoted parameter expansion in rm - use \"${var}\" for safety",
        0.95,
        "SHELL-SEC006",
        IssueSeverity.CRITICAL,
    ),
    r"\bchmod\s+\d+\s+\$[^{\"]": (
        "Unquoted variable in chmod - quote to prevent issues with spaces",
        0.80,
        "SHELL-SEC007",
        IssueSeverity.HIGH,
    ),
    r"\bchown\s+\S+\s+\$[^{\"]": (
        "Unquoted variable in chown - quote to prevent issues",
        0.80,
        "SHELL-SEC008",
        IssueSeverity.HIGH,
    ),
    # curl/wget without verification
    r"\bcurl\s+(?!.*-[kf]).*\|\s*(?:ba)?sh": (
        "Piping curl to shell is dangerous - download and inspect first",
        0.92,
        "SHELL-SEC009",
        IssueSeverity.CRITICAL,
    ),
    r"\bwget\s+.*-O\s*-\s*\|\s*(?:ba)?sh": (
        "Piping wget to shell is dangerous - download and inspect first",
        0.92,
        "SHELL-SEC010",
        IssueSeverity.CRITICAL,
    ),
    # Unsafe temp file creation
    r"\b(?:TMP|TEMP)\s*=\s*/tmp/[^$\s]+\b(?!\$)": (
        "Predictable temp file path - use mktemp for secure temp files",
        0.88,
        "SHELL-SEC011",
        IssueSeverity.HIGH,
    ),
    r">\s*/tmp/[a-zA-Z0-9_]+(?!\$)": (
        "Writing to predictable temp file - use mktemp for security",
        0.85,
        "SHELL-SEC012",
        IssueSeverity.MEDIUM,
    ),
}

# =============================================================================
# Security Patterns - Medium
# =============================================================================

SECURITY_PATTERNS_MEDIUM: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # Credential patterns
    r"(?:PASSWORD|SECRET|TOKEN|API_KEY)\s*=\s*['\"][^'\"]+['\"]": (
        "Hardcoded credential - use environment variables or secrets manager",
        0.92,
        "SHELL-SEC020",
        IssueSeverity.HIGH,
    ),
    r"--password\s*[=\s]['\"][^'\"]+['\"]": (
        "Password in command line - use environment variable or stdin",
        0.90,
        "SHELL-SEC021",
        IssueSeverity.HIGH,
    ),
    r"curl.*-u\s+\S+:\S+": (
        "Credentials in curl command - use .netrc or environment variables",
        0.85,
        "SHELL-SEC022",
        IssueSeverity.MEDIUM,
    ),
    # SSH/sudo patterns
    r"\bsudo\s+.*<<<\s*\$": (
        "Passing variable to sudo via heredoc - ensure input is sanitized",
        0.75,
        "SHELL-SEC023",
        IssueSeverity.MEDIUM,
    ),
    r"echo\s+.*\|\s*sudo": (
        "Piping to sudo - consider using sudo -S or proper authentication",
        0.70,
        "SHELL-SEC024",
        IssueSeverity.MEDIUM,
    ),
    # Source untrusted
    r"\bsource\s+\$": (
        "Sourcing variable path - ensure path is validated",
        0.80,
        "SHELL-SEC025",
        IssueSeverity.MEDIUM,
    ),
    r"\.\s+\$": (
        "Sourcing variable path with dot - ensure path is validated",
        0.80,
        "SHELL-SEC026",
        IssueSeverity.MEDIUM,
    ),
}

# =============================================================================
# Best Practice Patterns
# =============================================================================

BEST_PRACTICE_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # NOTE: SHELL-BP001 (set options) is handled in _check_set_options() as a file-level check
    # Unquoted variables
    r"\[\s+\$\w+\s+": (
        "Unquoted variable in test - use \"$var\" to handle empty values",
        0.85,
        "SHELL-BP002",
        IssueSeverity.MEDIUM,
    ),
    r"\[\s+-[a-z]\s+\$\w+(?!\")": (
        "Unquoted variable in test expression - quote to handle spaces",
        0.82,
        "SHELL-BP003",
        IssueSeverity.MEDIUM,
    ),
    # Command substitution
    r"`[^`]+`": (
        "Backtick syntax is deprecated - use $() for command substitution",
        0.90,
        "SHELL-BP004",
        IssueSeverity.LOW,
    ),
    # Test syntax
    r"\[\s+[^]]+\s+-a\s+": (
        "-a in test is deprecated - use [[ ]] with && instead",
        0.85,
        "SHELL-BP005",
        IssueSeverity.LOW,
    ),
    r"\[\s+[^]]+\s+-o\s+": (
        "-o in test is deprecated - use [[ ]] with || instead",
        0.85,
        "SHELL-BP006",
        IssueSeverity.LOW,
    ),
    # Error handling
    r"\b(?:cd|pushd)\s+[^&|;]+(?![\s]*\|\|)(?![\s]*&&)$": (
        "cd/pushd without error handling - use 'cd ... || exit 1'",
        0.75,
        "SHELL-BP007",
        IssueSeverity.MEDIUM,
    ),
    # Useless use of cat
    r"\bcat\s+[^|]+\|\s*(?:grep|awk|sed|head|tail)": (
        "Useless use of cat - pipe directly: cmd < file or cmd file",
        0.80,
        "SHELL-BP008",
        IssueSeverity.INFO,
    ),
    # Useless use of echo
    r"\becho\s+[^|]+\|\s*read\b": (
        "Useless echo|read - use heredoc or direct assignment",
        0.75,
        "SHELL-BP009",
        IssueSeverity.INFO,
    ),
    # Variable expansion
    r"\$\w+\s*\+\s*\$\w+": (
        "Arithmetic with $ prefix - use $(( var + var )) for math",
        0.70,
        "SHELL-BP010",
        IssueSeverity.LOW,
    ),
    # NOTE: SHELL-BP011 (lowercase globals) removed - too noisy for real codebases
    # Many scripts use lowercase variables intentionally
}

# =============================================================================
# Code Quality Patterns
# =============================================================================

CODE_QUALITY_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # NOTE: SHELL-QUAL001 (missing shebang) is handled in _check_shebang() as a file-level check
    # Long lines
    r"^.{200,}$": (
        "Line exceeds 200 characters - consider breaking up for readability",
        0.70,
        "SHELL-QUAL002",
        IssueSeverity.INFO,
    ),
    # Complex conditionals
    r"if\s+.*&&.*&&.*&&": (
        "Complex conditional - consider breaking into multiple conditions",
        0.65,
        "SHELL-QUAL003",
        IssueSeverity.INFO,
    ),
    # Nested loops depth
    r"for\s+.*\bfor\s+.*\bfor\s+": (
        "Deeply nested loops - consider refactoring into functions",
        0.70,
        "SHELL-QUAL004",
        IssueSeverity.LOW,
    ),
    # Function without local
    r"^\s*\w+\s*\(\s*\)\s*\{[^}]*\b[a-z_][a-z0-9_]*\s*=[^}]*\}(?!.*\blocal\b)": (
        "Function modifies global variable - use 'local' for function variables",
        0.60,
        "SHELL-QUAL005",
        IssueSeverity.LOW,
    ),
    # Deprecated test
    r"\[\s+\"\$\w+\"\s+==\s+": (
        "== in [ ] test is not POSIX - use = for portability or [[ ]]",
        0.75,
        "SHELL-QUAL006",
        IssueSeverity.LOW,
    ),
}

# =============================================================================
# Performance Patterns
# =============================================================================

PERFORMANCE_PATTERNS: Dict[str, Tuple[str, float, str, IssueSeverity]] = {
    # Subprocess in loop
    r"(?:for|while)\s+[^;]+;\s*do[^;]*\$\(": (
        "Command substitution in loop - consider processing outside loop",
        0.70,
        "SHELL-PERF001",
        IssueSeverity.LOW,
    ),
    # Multiple grep/sed/awk
    r"\|\s*grep[^|]*\|\s*grep": (
        "Multiple greps - combine into single grep with -E 'pattern1|pattern2'",
        0.75,
        "SHELL-PERF002",
        IssueSeverity.INFO,
    ),
    r"\|\s*sed[^|]*\|\s*sed": (
        "Multiple seds - combine into single sed with multiple commands",
        0.75,
        "SHELL-PERF003",
        IssueSeverity.INFO,
    ),
    # find with exec
    r"\bfind\s+.*-exec\s+.*\{\}\s*\\;": (
        "find -exec with \\; runs command per file - use + for batching",
        0.80,
        "SHELL-PERF004",
        IssueSeverity.LOW,
    ),
    # Reading file in loop
    r"while\s+.*read.*;\s*do[\s\S]*\bdone\s*<\s*\$\(cat": (
        "Reading from $(cat file) - use 'while read; do ... done < file'",
        0.82,
        "SHELL-PERF005",
        IssueSeverity.LOW,
    ),
}


class ShellAnalyzer(BaseLanguageAnalyzer):
    """Analyzer for shell scripts (.sh, .bash, .zsh).

    Detects security vulnerabilities, best practice violations,
    and code quality issues in shell scripts.
    """

    @property
    def supported_languages(self) -> Set[Language]:
        """Return languages this analyzer supports."""
        return {Language.SHELL}

    @property
    def analyzer_name(self) -> str:
        """Return the display name of this analyzer."""
        return "Shell Script Analyzer"

    def analyze_file(self, file_path: Path) -> List[AnalysisIssue]:
        """Analyze a shell script file."""
        if not self._load_file(file_path):
            return []

        # Run all checks
        self._check_security_critical()
        self._check_security_medium()
        self._check_best_practices()
        self._check_code_quality()
        self._check_performance()

        # Special file-level checks
        self._check_shebang()
        self._check_set_options()
        self._check_unquoted_variables()

        logger.debug("Shell Analyzer found %d issues in %s", len(self.issues), file_path)
        return self.issues

    def _should_skip_line(self, line: str) -> bool:
        """Check if line should be skipped."""
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            return True

        # Skip comments (but not shebang)
        if stripped.startswith("#") and not stripped.startswith("#!"):
            return True

        return False

    def _get_category_from_prefix(self, prefix: str) -> "IssueCategory":
        """Determine issue category from prefix (Issue #315 - extracted helper)."""
        prefix_lower = prefix.lower()
        if "sec" in prefix_lower:
            return IssueCategory.SECURITY
        if "perf" in prefix_lower:
            return IssueCategory.PERFORMANCE
        if "bp" in prefix_lower:
            return IssueCategory.BEST_PRACTICE
        return IssueCategory.CODE_QUALITY

    def _create_pattern_issue(
        self, line_num: int, line: str, match, pattern_data: Tuple, prefix: str, category: "IssueCategory"
    ) -> "AnalysisIssue":
        """Create an AnalysisIssue from pattern match (Issue #315 - extracted helper)."""
        recommendation, confidence, rule_id, severity = pattern_data
        return AnalysisIssue(
            issue_id=self._generate_issue_id(prefix),
            category=category,
            severity=severity,
            language=Language.SHELL,
            file_path=self.file_path,
            line_start=line_num,
            line_end=line_num,
            column_start=match.start(),
            column_end=match.end(),
            title=f"Shell {category.value}: {rule_id}",
            description="Pattern detected that may indicate an issue",
            recommendation=recommendation,
            current_code=line.strip(),
            confidence=confidence,
            potential_false_positive=confidence < 0.80,
            false_positive_reason="" if confidence >= 0.80 else "Context may justify this pattern",
            rule_id=rule_id,
            tags=["shell", category.value],
        )

    def _check_pattern_on_line(
        self, line_num: int, line: str, pattern: str, pattern_data: Tuple, prefix: str, category: "IssueCategory"
    ) -> None:
        """Check single pattern on a line (Issue #315 - extracted helper)."""
        try:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                issue = self._create_pattern_issue(line_num, line, match, pattern_data, prefix, category)
                self.issues.append(issue)
        except re.error:
            pass  # Skip invalid regex patterns

    def _check_patterns(
        self,
        patterns: Dict[str, Tuple],
        prefix: str,
    ) -> None:
        """Check a set of patterns against source code (Issue #315 - refactored)."""
        category = self._get_category_from_prefix(prefix)

        for line_num, line in enumerate(self.lines, start=1):
            if self._should_skip_line(line):
                continue

            for pattern, pattern_data in patterns.items():
                self._check_pattern_on_line(line_num, line, pattern, pattern_data, prefix, category)

    def _check_security_critical(self) -> None:
        """Check for critical security issues."""
        self._check_patterns(SECURITY_PATTERNS_CRITICAL, "security-critical")

    def _check_security_medium(self) -> None:
        """Check for medium security issues."""
        self._check_patterns(SECURITY_PATTERNS_MEDIUM, "security-medium")

    def _check_best_practices(self) -> None:
        """Check for best practice violations."""
        self._check_patterns(BEST_PRACTICE_PATTERNS, "best-practice")

    def _check_code_quality(self) -> None:
        """Check for code quality issues."""
        self._check_patterns(CODE_QUALITY_PATTERNS, "code-quality")

    def _check_performance(self) -> None:
        """Check for performance issues."""
        self._check_patterns(PERFORMANCE_PATTERNS, "performance")

    def _check_shebang(self) -> None:
        """Check for proper shebang line (file-level check)."""
        if not self.lines:
            return

        first_line = self.lines[0].strip()
        if not first_line.startswith("#!"):
            # Only flag if it looks like a real script (has multiple lines)
            if len(self.lines) > 5:
                self.issues.append(
                    AnalysisIssue(
                        issue_id=self._generate_issue_id("shebang"),
                        category=IssueCategory.CODE_QUALITY,
                        severity=IssueSeverity.MEDIUM,
                        language=Language.SHELL,
                        file_path=self.file_path,
                        line_start=1,
                        line_end=1,
                        title="Missing shebang",
                        description="Script is missing a shebang line to specify the interpreter",
                        recommendation="Add #!/usr/bin/env bash or #!/bin/bash at the start of the file",
                        current_code=first_line[:50] if first_line else "(empty file)",
                        suggested_fix="#!/usr/bin/env bash",
                        confidence=0.85,
                        potential_false_positive=True,
                        false_positive_reason="May be a sourced file that doesn't need a shebang",
                        rule_id="SHELL-QUAL001",
                        tags=["shell", "shebang", "code-quality"],
                    )
                )

    def _check_set_options(self) -> None:
        """Check for proper error handling with set options."""
        has_set_e = False
        has_set_u = False
        has_pipefail = False

        # Issue #380: Use pre-compiled patterns for set option checking
        for line in self.lines[:30]:  # Check first 30 lines
            if _SET_E_RE.search(line):
                has_set_e = True
            if _SET_U_RE.search(line):
                has_set_u = True
            if _SET_PIPEFAIL_RE.search(line):
                has_pipefail = True
            if _SET_EUO_PIPEFAIL_RE.search(line):
                has_set_e = has_set_u = has_pipefail = True

        missing = []
        if not has_set_e:
            missing.append("set -e (exit on error)")
        if not has_set_u:
            missing.append("set -u (error on undefined)")
        if not has_pipefail:
            missing.append("set -o pipefail (pipe failures)")

        if missing and len(self.lines) > 10:  # Only for non-trivial scripts
            self.issues.append(
                AnalysisIssue(
                    issue_id=self._generate_issue_id("set-options"),
                    category=IssueCategory.BEST_PRACTICE,
                    severity=IssueSeverity.INFO,
                    language=Language.SHELL,
                    file_path=self.file_path,
                    line_start=1,
                    line_end=1,
                    title="Missing error handling options",
                    description=f"Script missing: {', '.join(missing)}",
                    recommendation="Add 'set -euo pipefail' near the start of the script for stricter error handling",
                    current_code=self.lines[0] if self.lines else "",
                    suggested_fix="#!/usr/bin/env bash\nset -euo pipefail",
                    confidence=0.65,
                    potential_false_positive=True,
                    false_positive_reason="Some scripts intentionally need lenient error handling",
                    rule_id="SHELL-BP001",
                    tags=["shell", "error-handling", "best-practice"],
                )
            )

    def _check_unquoted_variables(self) -> None:
        """Advanced check for unquoted variables in dangerous contexts."""
        for line_num, line in enumerate(self.lines, start=1):  # Issue #380: use _DANGEROUS_COMMANDS
            if self._should_skip_line(line):
                continue

            # Check for unquoted $VAR after dangerous commands
            for cmd in _DANGEROUS_COMMANDS:  # Issue #380: use module constant
                # Pattern: cmd ... $var (not "$var" or "${var}")
                pattern = rf"\b{cmd}\s+[^|;&\n]*\$([a-zA-Z_][a-zA-Z0-9_]*)(?![a-zA-Z0-9_\"}}])"
                match = re.search(pattern, line)
                if match:
                    var_name = match.group(1)
                    # Check it's not already quoted
                    var_pos = match.start(1) - 1  # Position of $
                    if var_pos > 0 and line[var_pos - 1] == '"':
                        continue

                    self.issues.append(
    AnalysisIssue(
        issue_id=self._generate_issue_id("unquoted-var"),
        category=IssueCategory.SECURITY,
        severity=IssueSeverity.MEDIUM,
        language=Language.SHELL,
        file_path=self.file_path,
        line_start=line_num,
        line_end=line_num,
        title=f"Unquoted variable ${var_name} in {cmd}",
        description="Unquoted variable expansion can cause issues with spaces or special characters",
        recommendation=f'Quote the variable: "${var_name}" or "${{var_name}}"',
        current_code=line.strip(),
        confidence=0.85,
        potential_false_positive=True,
        false_positive_reason="Variable may be known to never contain spaces",
        rule_id="SHELL-SEC030",
        tags=[
            "shell",
            "security",
            "quoting"],
             ) )


# Create singleton instance
shell_analyzer = ShellAnalyzer()
