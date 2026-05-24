#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared helpers for tools/lint/*.py regression-prevention hooks.

Extracted per #5449 after #5394 + #5418 showed two hooks with byte-
identical ``_iter_target_files`` implementations drifted independently
(``.worktrees`` exclusion fixed in one, then the other). A single source
of truth prevents a third such drift.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

# Directories skipped during full-repo ``rglob('*.py')`` scans. Kept as a
# frozenset so hooks can reference the same constant without risk of
# per-hook mutation. Adding a new entry here covers all current + future
# callers in one place.
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".git",
        "dist",
        "build",
        ".worktrees",  # parallel-work git worktrees (#5394, #5418)
    }
)


def iter_python_files(args: List[str], repo_root: Path) -> Iterable[Path]:
    """Yield target ``.py`` files for a lint hook.

    Two modes:

    * **Explicit argv** — pre-commit / CI passes changed file paths. Each
      is filtered by ``.py`` suffix and yielded as-is (absolute or
      repo-relative). Directory exclusions are NOT applied because
      explicit paths are trusted.
    * **Full-repo scan** — no argv (e.g. ``python3 tools/lint/hook.py``).
      Walks ``repo_root.rglob('*.py')`` and skips any path whose parts
      intersect :data:`EXCLUDED_DIR_NAMES`.

    Args:
        args: Positional argv tail (argv[1:]). When truthy, treated as
            explicit file list. When empty, triggers full-repo mode.
        repo_root: Repository root path, used to resolve relative argv
            entries and to seed ``rglob``.

    Yields:
        ``Path`` objects for each target file.
    """
    if args:
        for a in args:
            p = Path(a)
            if not p.is_absolute():
                p = repo_root / p
            if p.is_file() and p.suffix == ".py":
                yield p
        return

    for p in repo_root.rglob("*.py"):
        parts = p.relative_to(repo_root).parts
        if any(part in EXCLUDED_DIR_NAMES for part in parts):
            continue
        yield p
