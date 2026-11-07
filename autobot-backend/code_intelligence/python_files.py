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


def collect_python_files(directory: str, exclude_dirs: Iterable[str]) -> List[str]:
    """Return sorted ``*.py`` paths under *directory* at any depth, minus excluded parts."""
    root = Path(directory)
    excluded = set(exclude_dirs)
    return sorted(str(py_file) for py_file in root.rglob("*.py") if not is_excluded(py_file, root, excluded))


def cache_covers_exclusions(exclude_dirs: Iterable[str]) -> bool:
    """True if the shared file cache's fixed ``SKIP_DIRS`` filter is implied by *exclude_dirs*.

    The cache pre-filters with ``SKIP_DIRS``. Only then can ``is_excluded`` over
    the cached list equal the uncached walk; for a custom ``exclude_dirs`` that
    omits a ``SKIP_DIRS`` name the cache already dropped files the caller wants,
    so discovery must walk instead. ``exclude_dirs`` stays authoritative (#20493).
    """
    return SKIP_DIRS <= set(exclude_dirs)
