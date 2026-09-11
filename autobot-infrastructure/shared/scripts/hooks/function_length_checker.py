#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Function Length Checker - AST-based Analysis

Checks Python functions for length violations according to CLAUDE.md guidelines:
- <=30 lines: Ideal
- 31-50 lines: Acceptable
- 51-65 lines: WARNING - Must refactor before merge
- >65 lines: ERROR - Blocks commit

Issue #620 - Function Length Enforcement

Only the functions a change touches are judged (#16191). A function counts as
touched when a line the change added falls inside it, so adding or changing a
line in a long function, or adding a long function, still fails, while a one-line
fix elsewhere in the same file is no longer held hostage by a legacy function it
never touched. A change that only deletes lines from a long function adds none
there, so it passes: it can only have made that function shorter. The change is
the staged diff, or the range pre-commit exports for a ``--from-ref`` run, which
stages nothing. A file passed in but not part of the staged change
(``--all-files``, ``--files``) has no change to scope to, so it is judged whole
rather than passed unexamined.

``--whole-file`` judges every file whole. It is for invoking this script directly
-- the bash wrapper never passes arguments through -- and is how the current
offenders are enumerated.
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# The diff helpers every scoped lint hook shares (#16178): hunk parsing, rename
# pairing and the pre-commit range, in one place rather than one copy per hook.
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools" / "lint"))

from _scan_helpers import added_lines, resolve_base, staged_paths  # noqa: E402

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
    end_line: Optional[int] = None  # the function's last line, for scoping (#16191)

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
                    end_line=getattr(node, "end_lineno", None),
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
        if isinstance(first_stmt, ast.Expr) and isinstance(first_stmt.value, ast.Constant):
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


def _scope_to_change(
    violations: List[FunctionViolation], repo_root: Path, base: Optional[str]
) -> Tuple[List[FunctionViolation], int, List[str]]:
    """Keep the violations in functions this change touched (#16191).

    Returns (kept, how many were skipped as untouched, files judged whole). A file
    with no staged change is judged whole: an empty diff for it would read as
    "touched nothing", a verdict nobody examined.
    """
    staged = staged_paths(repo_root) if base is None else None
    added: Dict[str, Set[int]] = {}
    kept: List[FunctionViolation] = []
    whole: List[str] = []
    skipped = 0
    for v in violations:
        if staged is not None and v.file_path not in staged:
            kept.append(v)
            if v.file_path not in whole:
                whole.append(v.file_path)
            continue
        if v.file_path not in added:
            added[v.file_path] = added_lines(repo_root, v.file_path, base)
        end = v.end_line or v.line_number
        if any(v.line_number <= n <= end for n in added[v.file_path]):
            kept.append(v)
        else:
            skipped += 1
    return kept, skipped, whole


def _report_scope(violations: List[FunctionViolation]) -> List[FunctionViolation]:
    """Scope *violations* to the change, and say what was skipped or judged whole.

    Only a file that has a violation costs a git call, so a clean change reads no
    diff at all. The repository judged is the one the hook runs in, not the one
    this script lives in: pre-commit runs hooks from that repository's root, and
    the hook's own tests run it inside throwaway repositories. In staged mode, run
    from a subdirectory, the paths it is given no longer match the root-relative
    staged set, so its files are judged whole -- over-reported, never skipped.
    """
    if not violations:
        return violations
    kept, skipped, whole = _scope_to_change(violations, Path.cwd(), resolve_base())
    if skipped:
        print(f"{CYAN}Skipped {skipped} long function(s) this change did not touch (#16191).{NC}")
    if whole:
        print(
            f"{YELLOW}NOTE{NC} {len(whole)} file(s) are not part of the staged change, so they were judged whole; "
            "their long functions may predate it (#16191)."
        )
    if skipped or whole:
        print()
    return kept


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


def _print_summary(all_violations: List[FunctionViolation]) -> int:
    """Print the verdict and return the exit code. Issue #620."""
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
        return 1
    if warnings:
        print(f"{YELLOW}{len(warnings)} warning(s) - commit allowed{NC}")
        print("Consider refactoring before merge (functions 51-65 lines)")
        print()
        return 0
    print(f"{GREEN}No function length violations found!{NC}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point. Reads file paths from stdin. Issue #620, #16191."""
    whole_file = "--whole-file" in (sys.argv[1:] if argv is None else argv)
    files = [line.strip() for line in sys.stdin if line.strip()]

    if not files:
        print(f"{GREEN}No files to check.{NC}")
        return 0

    print(f"Scanning {len(files)} file(s)...")
    print()

    all_violations = [v for file_path in files for v in analyze_file(file_path)]
    if not whole_file:
        try:
            all_violations = _report_scope(all_violations)
        except RuntimeError as exc:
            # A git failure is not "this change touched nothing" (#16191).
            print(f"{RED}FATAL{NC}: {exc} -- cannot tell what this change touched, refusing to report clean")
            return 1

    for v in all_violations:
        print_violation(v)
    return _print_summary(all_violations)


if __name__ == "__main__":
    sys.exit(main())
