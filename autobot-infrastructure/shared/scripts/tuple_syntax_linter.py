#!/usr/bin/env python3
"""
Fix trailing comma tuple bugs across the codebase.

This script detects and fixes patterns like:
    x = (
        some_value
    ),  # <-- Bug: Creates tuple instead of value

And converts them to:
    x = (
        some_value
    )  # Fixed: No trailing comma

Author: mrveiss
Copyright (c) 2025 mrveiss
"""

import ast
import re
import sys
from pathlib import Path


def find_trailing_comma_tuples(content: str, filepath: str) -> list[dict]:
    """Find all single-element tuple assignments with trailing commas."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    issues = []
    lines = content.split("\n")

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Tuple) and len(node.value.elts) == 1:
                # Get the line where the tuple ends
                end_line = node.value.end_lineno
                if end_line and end_line <= len(lines):
                    line_content = lines[end_line - 1]
                    # Check if this line has a trailing comma before any comment
                    # Pattern: closing paren followed by comma
                    if re.search(r"\)\s*,\s*(#.*)?$", line_content):
                        issues.append(
                            {
                                "line": end_line,
                                "col": node.value.end_col_offset,
                                "content": line_content,
                                "target": node.targets[0].id
                                if isinstance(node.targets[0], ast.Name)
                                else "unknown",
                            }
                        )

    return issues


def trailing_comma_corrector(content: str, issues: list[dict]) -> str:
    """Remove trailing commas from identified issues."""
    lines = content.split("\n")

    for issue in issues:
        line_idx = issue["line"] - 1
        if line_idx < len(lines):
            # Remove trailing comma after closing paren
            # Pattern: ),  or ), # comment
            lines[line_idx] = re.sub(
                r"(\))\s*,(\s*(?:#.*)?)$", r"\1\2", lines[line_idx]
            )

    return "\n".join(lines)


def process_file(filepath: Path, dry_run: bool = False) -> tuple[int, list[dict]]:
    """Process a single file and fix trailing comma tuples."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0, []

    issues = find_trailing_comma_tuples(content, str(filepath))

    if issues and not dry_run:
        fixed_content = trailing_comma_corrector(content, issues)
        filepath.write_text(fixed_content, encoding="utf-8")

    return len(issues), issues


def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # Project root
    project_root = Path(__file__).parent.parent

    # Directories to scan
    scan_dirs = [
        project_root / "backend",
        project_root / "src",
    ]

    # Skip patterns
    skip_patterns = [
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        ".pytest_cache",
    ]

    total_fixed = 0
    files_fixed = 0

    print(f"{'[DRY RUN] ' if dry_run else ''}Scanning for trailing comma tuple bugs...")
    print()

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue

        for py_file in scan_dir.rglob("*.py"):
            # Skip unwanted directories
            if any(skip in str(py_file) for skip in skip_patterns):
                continue

            count, issues = process_file(py_file, dry_run)

            if count > 0:
                files_fixed += 1
                total_fixed += count
                rel_path = py_file.relative_to(project_root)
                print(
                    f"{'Would fix' if dry_run else 'Fixed'} {count} issue(s) in {rel_path}"
                )

                if verbose:
                    for issue in issues:
                        print(f"  Line {issue['line']}: {issue['target']} = (...),")

    print()
    print(
        f"{'Would fix' if dry_run else 'Fixed'} {total_fixed} trailing comma tuple(s) in {files_fixed} file(s)"
    )

    if dry_run:
        print("\nRun without --dry-run to apply fixes.")


if __name__ == "__main__":
    main()
