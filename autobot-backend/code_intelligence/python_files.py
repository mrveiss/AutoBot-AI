# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one Python-file collector shared by the code-intelligence analyzers (#18731).

The anti-pattern suite, the clone detector and the pattern analyzer each
carried their own copy of this walk; they now delegate here. The exclusion
predicate (``is_excluded``) is shared too, so the cached (async) and
uncached (sync) discovery paths cannot disagree (#20493).
"""

import fnmatch
import os
from pathlib import Path
from typing import Iterable, Iterator, List, Set

from utils.file_categorization import SKIP_DIRS

# The one directory-name exclusion set for every code-intelligence analyzer
# (#21004). Derived from the repo-wide ``SKIP_DIRS``; the extras are the
# analysis-only names the per-analyzer copies used to add individually
# (archived/backup trees, tool caches, third-party code). Analyzers import this
# instead of declaring their own ``EXCLUDE_DIRS`` / ignore list.
ANALYSIS_EXCLUDE_DIRS: frozenset = frozenset(
    SKIP_DIRS | {"archive", "archives", "backup", "backups", ".mypy_cache", "third_party"}
)


def is_excluded(path: Path, root: Path, excluded: Iterable[str]) -> bool:
    """True if a component of *path* **below** *root* is in *excluded*.

    Matching the absolute path asked whether an excluded name appears anywhere
    in it, including in the root itself, so a tree checked out below e.g. a
    ``venv`` directory scanned as empty (#13602, #20493).
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        # A path outside the root has no root-relative parts to judge. Treat it
        # as excluded, as is_skipped_path does: scanning something we cannot
        # place under the root is worse than skipping it (#20493).
        return True
    return not set(excluded).isdisjoint(parts)


def _escapes(path: Path, real_root: Path, excluded: Iterable[str]) -> bool:
    """True if symlinked leaf *path* resolves outside the root or into an excluded dir."""
    try:
        return is_excluded(path.resolve(), real_root, excluded)
    except (OSError, RuntimeError):
        return True  # a loop or unreadable link cannot be placed under the root


def _walk_matches(root: Path, patterns: List[str], excluded: Set[str]) -> Iterator[Path]:
    """Yield files under *root* matching a pattern, pruning excluded dirs while walking."""
    real_root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in excluded]
        for name in filenames:
            if not any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
                continue
            path = Path(dirpath) / name
            if path.is_symlink() and _escapes(path, real_root, excluded):
                continue
            if path.is_file():
                yield path


def discover_files(
    directory: str | Path,
    patterns: Iterable[str] = ("*.py",),
    exclude_dirs: Iterable[str] | None = None,
) -> List[Path]:
    """The one file-discovery walk for the code-intelligence analyzers (#21004).

    A single pruned ``os.walk`` returns the sorted files under *directory* whose
    name matches any glob in *patterns* (file-name globs only: a pattern with a
    path separator raises ``ValueError``). Excluded directory names (default
    ``ANALYSIS_EXCLUDE_DIRS``) are matched **below** the root only, and are never
    descended into. A symlinked leaf that resolves outside the root, or into an
    excluded directory, is dropped (#13602 tier 2/3).
    """
    names = list(patterns)
    bad = [p for p in names if "/" in p or "\\" in p]
    if bad:
        raise ValueError(f"discover_files takes file-name globs only (no path separators): {bad}")
    excluded = set(ANALYSIS_EXCLUDE_DIRS if exclude_dirs is None else exclude_dirs)
    return sorted(_walk_matches(Path(directory), names, excluded))


def collect_python_files(directory: str, exclude_dirs: Iterable[str]) -> List[str]:
    """Return sorted ``*.py`` paths under *directory* at any depth, minus excluded parts."""
    return [str(path) for path in discover_files(directory, ("*.py",), exclude_dirs)]


def cache_covers_exclusions(exclude_dirs: Iterable[str]) -> bool:
    """True if the shared file cache's fixed ``ANALYSIS_EXCLUDE_DIRS`` filter is implied by *exclude_dirs*.

    The cache pre-filters with ``ANALYSIS_EXCLUDE_DIRS``. Only then can ``is_excluded`` over
    the cached list equal the uncached walk; for a custom ``exclude_dirs`` that
    omits one of those names the cache already dropped files the caller wants,
    so discovery must walk instead. ``exclude_dirs`` stays authoritative (#20493).
    """
    return ANALYSIS_EXCLUDE_DIRS <= set(exclude_dirs)
