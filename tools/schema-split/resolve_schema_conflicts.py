# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Resolve git merge conflicts in Python schema files by keeping both sides.

Validates the result with ast.parse() before writing to catch docstring
corruption from blind concatenation of partial class bodies.

Usage:
    python3 tools/schema-split/resolve_schema_conflicts.py <file> [<file2> ...]
    python3 tools/schema-split/resolve_schema_conflicts.py --stdin  # read path from stdin
    python3 tools/schema-split/resolve_schema_conflicts.py --check  # dry-run, exit 1 on conflict

When run with no arguments, scans autobot-backend/api/schemas_*.py for conflicts.
"""

import ast
import re
import sys
import os

CONFLICT_RE = re.compile(
    r"<<<<<<< [^\n]+\n(.*?)\n=======\n(.*?)\n>>>>>>> [^\n]+\n",
    re.DOTALL,
)


def _resolve_content(content: str) -> str:
    """Replace each conflict marker block with HEAD + THEIRS concatenated."""
    return CONFLICT_RE.sub(lambda m: m.group(1) + "\n" + m.group(2), content)


def resolve_file(path: str, dry_run: bool = False) -> bool:
    """Resolve conflicts in *path*.  Returns True on success, False on failure."""
    with open(path, encoding="utf-8") as f:
        original = f.read()

    if "<<<<<<< " not in original:
        return True

    resolved = _resolve_content(original)

    try:
        ast.parse(resolved)
    except SyntaxError as exc:
        print(
            f"ERROR: {path}: conflict resolution produced invalid Python "
            f"at line {exc.lineno}: {exc.msg}\n"
            "  Likely cause: a docstring was split across a conflict boundary.\n"
            "  Resolve manually: check that each class docstring is complete on both sides.",
            file=sys.stderr,
        )
        return False

    if dry_run:
        conflict_count = len(CONFLICT_RE.findall(original))
        print(f"Would resolve {conflict_count} conflict(s) in {path} (AST OK)")
        return True

    with open(path, "w", encoding="utf-8") as f:
        f.write(resolved)

    conflict_count = len(CONFLICT_RE.findall(original))
    print(f"Resolved {conflict_count} conflict(s) in {path}")
    return True


def _schema_files() -> list[str]:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    api_dir = os.path.join(repo_root, "autobot-backend", "api")
    return sorted(
        os.path.join(api_dir, f) for f in os.listdir(api_dir) if f.startswith("schemas_") and f.endswith(".py")
    )


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--check" in args
    args = [a for a in args if a != "--check"]

    if "--stdin" in args:
        paths = [line.strip() for line in sys.stdin if line.strip()]
    elif args:
        paths = args
    else:
        paths = _schema_files()

    ok = True
    for path in paths:
        if not resolve_file(path, dry_run=dry_run):
            ok = False

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
