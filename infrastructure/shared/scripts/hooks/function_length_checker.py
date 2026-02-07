#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Function Length Checker - AST-based Analysis

Checks Python functions for length violations according to CLAUDE.md guidelines:
- <=30 lines: Ideal
- 31-50 lines: Acceptable
- 51-65 lines: WARNING - Must refactor before merge
- >65 lines: ERROR - Blocks commit

Issue #620 - Function Length Enforcement
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# ANSI color codes (matching bash wrapper)
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"

# Thresholds from CLAUDE.md
ACCEPTABLE_THRESHOLD = 50
WARNING_THRESHOLD = 65  # 51-65: WARNING, >65: ERROR


@dataclass
class FunctionViolation:
    """Represents a function length violation. Issue #620."""

    file_path: str
    function_name: str
    line_number: int
    line_count: int
    is_error: bool  # True = >65 (blocks), False = 51-65 (warns)
    class_name: Optional[str] = None

    @property
    def full_name(self) -> str:
        """Return fully qualified function name. Issue #620."""
        if self.class_name:
            return f"{self.class_name}.{self.function_name}"
        return self.function_name


class FunctionLengthVisitor(ast.NodeVisitor):
    """AST visitor that checks function lengths. Issue #620."""

    def __init__(self, file_path: str, source_lines: List[str]):
        """Initialize visitor with file context. Issue #620."""
        self.file_path = file_path
        self.source_lines = source_lines
        self.violations: List[FunctionViolation] = []
        self.current_class: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class context for method names. Issue #620."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Analyze synchronous function definitions. Issue #620."""
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Analyze async function definitions. Issue #620."""
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node) -> None:
        """Check a function/method for length violations. Issue #620."""
        body_line_count = self._count_body_lines(node)

        if body_line_count > ACCEPTABLE_THRESHOLD:
            is_error = body_line_count > WARNING_THRESHOLD
            self.violations.append(
                FunctionViolation(
                    file_path=self.file_path,
                    function_name=node.name,
                    line_number=node.lineno,
                    line_count=body_line_count,
                    is_error=is_error,
                    class_name=self.current_class,
                )
            )

    def _count_body_lines(self, node) -> int:
        """Count non-empty, non-comment lines in function body. Issue #620."""
        if not hasattr(node, "end_lineno") or node.end_lineno is None:
            return self._count_body_lines_fallback(node)

        start_line = node.lineno
        end_line = node.end_lineno

        # Get docstring span to exclude
        docstring_end = self._get_docstring_end_line(node)

        count = 0
        for line_num in range(start_line, end_line + 1):
            # Skip docstring lines
            if docstring_end and line_num <= docstring_end:
                continue

            # Skip the function definition line itself
            if line_num == start_line:
                continue

            # Get line content
            if line_num <= len(self.source_lines):
                line = self.source_lines[line_num - 1].strip()

                # Skip empty lines and comment-only lines
                if line and not line.startswith("#"):
                    count += 1

        return count

    def _get_docstring_end_line(self, node) -> Optional[int]:
        """Get the ending line number of a docstring if present. Issue #620."""
        if not node.body:
            return None

        first_stmt = node.body[0]

        # Check if first statement is a docstring
        if isinstance(first_stmt, ast.Expr) and isinstance(
            first_stmt.value, ast.Constant
        ):
            if isinstance(first_stmt.value.value, str):
                return getattr(first_stmt, "end_lineno", first_stmt.lineno)

        return None

    def _count_body_lines_fallback(self, node) -> int:
        """Fallback line counting for Python < 3.8. Issue #620."""
        start = node.lineno
        end = start

        for child in ast.walk(node):
            child_end = getattr(child, "lineno", start)
            if child_end > end:
                end = child_end

        return end - start


def analyze_file(file_path: str) -> List[FunctionViolation]:
    """Analyze a single Python file for function length violations. Issue #620."""
    path = Path(file_path)

    if not path.exists():
        return []

    try:
        source = path.read_text(encoding="utf-8")
        source_lines = source.splitlines()
        tree = ast.parse(source, filename=file_path)

        visitor = FunctionLengthVisitor(file_path, source_lines)
        visitor.visit(tree)

        return visitor.violations
    except SyntaxError as e:
        print(f"{YELLOW}WARNING{NC} {file_path}: Syntax error - {e}")
        return []
    except Exception as e:
        print(f"{YELLOW}WARNING{NC} {file_path}: Parse error - {e}")
        return []


def print_violation(v: FunctionViolation) -> None:
    """Print a single violation in IDE-friendly format. Issue #620."""
    level = f"{RED}ERROR{NC}" if v.is_error else f"{YELLOW}WARNING{NC}"
    threshold = WARNING_THRESHOLD if v.is_error else ACCEPTABLE_THRESHOLD

    print(f"{level} {v.file_path}:{v.line_number}")
    print(f"  Function '{v.full_name}' has {v.line_count} body lines")
    print(f"  Threshold: {'>' if v.is_error else ''}{threshold} lines")
    print(f"  {CYAN}Fix: Extract helper methods using _helper_function() pattern{NC}")
    print("  Reference: CLAUDE.md function length guidelines")
    print()


def main() -> int:
    """Main entry point. Reads file paths from stdin. Issue #620."""
    files = [line.strip() for line in sys.stdin if line.strip()]

    if not files:
        print(f"{GREEN}No files to check.{NC}")
        return 0

    print(f"Scanning {len(files)} staged file(s)...")
    print()

    all_violations: List[FunctionViolation] = []

    for file_path in files:
        violations = analyze_file(file_path)
        all_violations.extend(violations)

    # Print all violations
    for v in all_violations:
        print_violation(v)

    # Summary
    print("=" * 48)

    errors = [v for v in all_violations if v.is_error]
    warnings = [v for v in all_violations if not v.is_error]

    if errors:
        print(f"{RED}COMMIT BLOCKED: {len(errors)} function(s) exceed 65 lines{NC}")
        if warnings:
            print(f"{YELLOW}Plus {len(warnings)} warning(s) (51-65 lines){NC}")
        print()
        print("Quick fix using Extract Method pattern:")
        print("  1. Identify cohesive blocks of code")
        print("  2. Extract to _helper_function() with docstring referencing parent")
        print("  3. Keep functions under 50 lines (ideal: under 30)")
        print()
        print("Documentation: CLAUDE.md - Function Length section")
        print()
        print("To bypass (NOT recommended): git commit --no-verify")
        return 1
    elif warnings:
        print(f"{YELLOW}{len(warnings)} warning(s) - commit allowed{NC}")
        print("Consider refactoring before merge (functions 51-65 lines)")
        print()
        return 0
    else:
        print(f"{GREEN}No function length violations found!{NC}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
