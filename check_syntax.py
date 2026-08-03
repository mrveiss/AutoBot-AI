#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Byte-compile Python files to check them for syntax errors.

Usage::

    python3 check_syntax.py                       # default MCP metrics file set
    python3 check_syntax.py path/a.py path/b.py   # explicit file list

Paths are resolved against the repository root derived from ``__file__``
(#13409) — the default list previously used absolute paths into a developer
worktree that no longer exists, so this script could not run at all.
"""

import py_compile
import sys
from pathlib import Path
from typing import List

_REPO_ROOT = Path(__file__).resolve().parent

# Default set: the MCP metrics modules this script was written to guard.
DEFAULT_FILES = (
    "autobot_shared/monitoring/metrics/mcp_worker.py",
    "autobot_shared/monitoring/metrics/__init__.py",
    "autobot_shared/monitoring/prometheus_metrics.py",
    "autobot-backend/services/mcp_isolated_runtime.py",
)


def resolve_targets(argv: List[str]) -> List[Path]:
    """Return the files to compile: explicit argv, else the default set."""
    if argv:
        return [Path(arg) if Path(arg).is_absolute() else _REPO_ROOT / arg for arg in argv]
    return [_REPO_ROOT / rel for rel in DEFAULT_FILES]


def compile_file(path: Path) -> bool:
    """Byte-compile ``path``; report and return success."""
    rel = path.relative_to(_REPO_ROOT) if path.is_relative_to(_REPO_ROOT) else path
    if not path.is_file():
        print(f"✗ {rel}: file not found")  # noqa: print
        return False
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        print(f"✗ {rel}: {exc}")  # noqa: print
        return False
    print(f"✓ {rel}")  # noqa: print
    return True


def main(argv: List[str]) -> int:
    """Compile every target; return 0 when all have valid syntax."""
    results = [compile_file(path) for path in resolve_targets(argv)]
    if all(results):
        print("\nAll files have valid Python syntax!")  # noqa: print
        return 0
    print("\nSome files have syntax errors!")  # noqa: print
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
