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
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, List, Set

from autobot_shared.testfile_names import is_test_filename
from utils.file_categorization import SKIP_DIRS

# The one directory-name exclusion set for every code-intelligence analyzer
# (#21004). It IS the repo-wide ``SKIP_DIRS`` (which now carries the archive,
# backup, tool-cache and third-party names the per-analyzer copies used to add
# individually). Analyzers import this instead of declaring their own
# ``EXCLUDE_DIRS`` / ignore list.
ANALYSIS_EXCLUDE_DIRS: frozenset = frozenset(SKIP_DIRS)

# A pattern token (not a glob) meaning "the file name follows a test-file
# convention"; answered by the shared ``is_test_filename`` rule (#20493).
TEST_FILE_PATTERN = "<test-files>"

_GLOB_CHARS = "*?["


def _pattern_matches(pattern: str, text: str) -> bool:
    """One pattern against a ``/``-prefixed path text (the single pattern grammar).

    ``TEST_FILE_PATTERN`` -> shared test-file name rule. A glob with a slash
    (a leading ``**/`` is implied: matching is right-anchored) -> ``PurePath.match``.
    A slash-free glob -> the file name. Anything else is a path substring, so a
    plain ``venv`` or ``/migrations/`` matches a directory component.
    """
    if pattern == TEST_FILE_PATTERN:
        return is_test_filename(text)
    if any(char in pattern for char in _GLOB_CHARS):
        while pattern.startswith("**/"):
            pattern = pattern[3:]
        if "/" not in pattern:
            return fnmatch.fnmatchcase(text.rsplit("/", 1)[-1], pattern)
        anchored = pattern if pattern.startswith("*") else "*/" + pattern
        return PurePosixPath(text).match(pattern) or fnmatch.fnmatchcase(text, anchored)
    return pattern in text


def matches_exclusion(path: str | Path, patterns: Iterable[str], root: Path | None = None) -> bool:
    """The one file-exclusion predicate for the code-intelligence analyzers (#21004).

    True if any of *patterns* matches *path* (made relative to *root* when given,
    so a checkout under a skipped name does not exclude everything). Directory
    names are excluded by ``discover_files`` / ``is_excluded``; this answers the
    file-name and glob questions with one grammar (see ``_pattern_matches``).
    """
    text = Path(path).as_posix()
    if root is not None:
        try:
            text = Path(path).relative_to(root).as_posix()
        except ValueError:
            pass
    text = "/" + text.lstrip("/")
    return any(_pattern_matches(pattern, text) for pattern in patterns)


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
