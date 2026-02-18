#!/usr/bin/env python3
"""
Fix Bare Except Clauses

This script identifies and optionally fixes bare except clauses
in Python files throughout the codebase.
"""

import argparse
import ast
import os
import re
from typing import List, Tuple


class BareExceptFinder(ast.NodeVisitor):
    """AST visitor to find bare except clauses."""

    def __init__(self):
        self.bare_excepts: List[Tuple[int, int]] = []

    def visit_ExceptHandler(self, node):
        if node.type is None:  # Bare except
            self.bare_excepts.append((node.lineno, node.col_offset))
        self.generic_visit(node)


def find_bare_excepts(file_path: str) -> List[Tuple[int, int]]:
    """Find all bare except clauses in a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)
        finder = BareExceptFinder()
        finder.visit(tree)
        return finder.bare_excepts
    except (SyntaxError, UnicodeDecodeError):
        # Skip files with syntax errors or encoding issues
        return []


def fix_bare_except_line(line: str) -> str:
    """Fix a single line containing bare except."""
    # Simple regex replacement
    if re.match(r"^\s*except\s*:\s*$", line):
        indent = len(line) - len(line.lstrip())
        return " " * indent + "except Exception:\n"
    return line


def fix_file(file_path: str, dry_run: bool = False) -> int:
    """Fix bare except clauses in a file."""
    bare_excepts = find_bare_excepts(file_path)
    if not bare_excepts:
        return 0

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    fixed_count = 0
    for line_no, _ in bare_excepts:
        # Adjust for 0-based indexing
        idx = line_no - 1
        if idx < len(lines):
            original = lines[idx]
            fixed = fix_bare_except_line(original)
            if original != fixed:
                lines[idx] = fixed
                fixed_count += 1
                if not dry_run:
                    print(f"  Line {line_no}: except: → except Exception:")

    if fixed_count > 0 and not dry_run:
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    return fixed_count


def scan_directory(
    directory: str,
    fix: bool = False,
    dry_run: bool = False,
    exclude_dirs: List[str] = None,
) -> Tuple[int, int]:
    """Scan directory for bare except clauses."""
    if exclude_dirs is None:
        exclude_dirs = [".git", "__pycache__", "venv", ".venv", "build", "dist"]

    total_files = 0
    total_bare_excepts = 0
    files_with_issues = []

    for root, dirs, files in os.walk(directory):
        # Remove excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                total_files += 1

                if fix:
                    count = fix_file(file_path, dry_run)
                    if count > 0:
                        total_bare_excepts += count
                        files_with_issues.append((file_path, count))
                        if not dry_run:
                            print(f"\nFixed {count} bare except(s) in {file_path}")
                else:
                    bare_excepts = find_bare_excepts(file_path)
                    if bare_excepts:
                        total_bare_excepts += len(bare_excepts)
                        files_with_issues.append((file_path, len(bare_excepts)))

    if not fix and files_with_issues:
        print("\nFiles with bare except clauses:")
        for file_path, count in sorted(files_with_issues):
            print(f"  {file_path}: {count} occurrence(s)")

    return total_files, total_bare_excepts


def main():
    parser = argparse.ArgumentParser(
        description="Find and fix bare except clauses in Python files"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix bare except clauses (replace with except Exception:)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    parser.add_argument(
        "--exclude", nargs="+", help="Additional directories to exclude"
    )

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: {args.directory} is not a valid directory")
        return 1

    exclude_dirs = [".git", "__pycache__", "venv", ".venv", "build", "dist"]
    if args.exclude:
        exclude_dirs.extend(args.exclude)

    print(f"Scanning {args.directory} for bare except clauses...")
    if args.fix:
        print(f"Mode: {'DRY RUN' if args.dry_run else 'FIX'}")

    total_files, total_bare_excepts = scan_directory(
        args.directory, fix=args.fix, dry_run=args.dry_run, exclude_dirs=exclude_dirs
    )

    print("\nSummary:")
    print(f"  Total Python files scanned: {total_files}")
    print(f"  Total bare except clauses: {total_bare_excepts}")

    if args.fix and not args.dry_run:
        print(f"\n✓ Fixed {total_bare_excepts} bare except clause(s)")
    elif args.fix and args.dry_run:
        print(f"\nDry run: Would fix {total_bare_excepts} bare except clause(s)")
    else:
        if total_bare_excepts > 0:
            print("\nTo fix these issues, run with --fix flag")

    return 0 if total_bare_excepts == 0 else 1


if __name__ == "__main__":
    exit(main())
