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

from pathlib import Path
from typing import Iterable, List

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


def discover_files(
    directory: str | Path,
    patterns: Iterable[str] = ("*.py",),
    exclude_dirs: Iterable[str] | None = None,
) -> List[Path]:
    """The one file-discovery walk for the code-intelligence analyzers (#21004).

    Returns the sorted, de-duplicated files under *directory* matching any glob
    in *patterns*, minus those with an excluded component **below** the root
    (``exclude_dirs`` defaults to ``ANALYSIS_EXCLUDE_DIRS``).
    """
    root = Path(directory)
    excluded = ANALYSIS_EXCLUDE_DIRS if exclude_dirs is None else set(exclude_dirs)
    found = {path for pattern in patterns for path in root.rglob(pattern) if path.is_file()}
    return sorted(path for path in found if not is_excluded(path, root, excluded))


def collect_python_files(directory: str, exclude_dirs: Iterable[str]) -> List[str]:
    """Return sorted ``*.py`` paths under *directory* at any depth, minus excluded parts."""
    return [str(path) for path in discover_files(directory, ("*.py",), exclude_dirs)]


def cache_covers_exclusions(exclude_dirs: Iterable[str]) -> bool:
    """True if the shared file cache's fixed ``SKIP_DIRS`` filter is implied by *exclude_dirs*.

    The cache pre-filters with ``SKIP_DIRS``. Only then can ``is_excluded`` over
    the cached list equal the uncached walk; for a custom ``exclude_dirs`` that
    omits a ``SKIP_DIRS`` name the cache already dropped files the caller wants,
    so discovery must walk instead. ``exclude_dirs`` stays authoritative (#20493).
    """
    return SKIP_DIRS <= set(exclude_dirs)
