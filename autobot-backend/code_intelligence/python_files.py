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
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator, List, Set

from autobot_shared.testfile_names import is_test_filename
from utils.file_categorization import SKIP_DIRS

# The one directory-name exclusion rule for every code-intelligence analyzer
# (#21004): the repo-wide ``SKIP_DIRS`` plus ONE non-code rule, defined here once.
# ``PACKAGE_AWARE_NON_CODE_NAMES`` names archive/backup/vendored trees, but they are
# also legitimate package names (``autobot-backend/backup/`` is imported by the
# lifespan), so such a directory is skipped only when it is NOT a Python package
# (no ``__init__.py``). ``.mypy_cache`` is never code and is skipped always.
PACKAGE_AWARE_NON_CODE_NAMES: frozenset = frozenset({"archive", "archives", "backup", "backups", "third_party"})
ANALYSIS_EXCLUDE_DIRS: frozenset = frozenset(SKIP_DIRS | PACKAGE_AWARE_NON_CODE_NAMES | {".mypy_cache"})

# A pattern token (not a glob) meaning "the file name follows a test-file
# convention"; answered by the shared ``is_test_filename`` rule (#20493).
TEST_FILE_PATTERN = "<test-files>"

_GLOB_CHARS = "*?["


@lru_cache(maxsize=256)
def _glob_regex(pattern: str) -> "re.Pattern[str]":
    """A glob with a slash as a right-anchored regex: ``*`` stays in one component, ``**`` spans several."""
    parts = pattern.lstrip("/").split("/")
    body = ""
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part == "**":
            body += ".+" if last else "(?:[^/]+/)*"
            continue
        body += _component_regex(part) + ("" if last else "/")
    return re.compile("(?:^|/)" + body + "$")


def _component_regex(part: str) -> str:
    """One path component's glob (``*``, ``?``, ``[set]``) as regex that cannot cross ``/``."""
    out, i = "", 0
    while i < len(part):
        char = part[i]
        close = part.find("]", i + 2) if char == "[" else -1
        if char == "[" and close != -1:
            out += part[i : close + 1].replace("[!", "[^")
            i = close + 1
            continue
        out += "[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char)
        i += 1
    return out


def _contains_components(text: str, word: str) -> bool:
    """True if the ``/``-separated components of *word* appear consecutively in *text*."""
    want = [c for c in word.split("/") if c]
    have = [c for c in text.split("/") if c]
    return bool(want) and any(have[i : i + len(want)] == want for i in range(len(have) - len(want) + 1))


def _pattern_matches(pattern: str, text: str) -> bool:
    """One pattern against a ``/``-prefixed path text (the single pattern grammar).

    ``TEST_FILE_PATTERN`` -> shared test-file name rule. A slash-free glob -> the
    file name. A glob with a slash is right-anchored (a leading ``**/`` is implied):
    ``*`` stays inside one component, ``**`` spans components. Anything else is a
    plain word or ``a/b`` run that must equal whole path components, so ``build``
    never matches ``rebuild.py`` and ``lib`` never matches ``library/``.
    """
    if pattern == TEST_FILE_PATTERN:
        return is_test_filename(text)
    if any(char in pattern for char in _GLOB_CHARS):
        if "/" not in pattern:
            return fnmatch.fnmatchcase(text.rsplit("/", 1)[-1], pattern)
        return _glob_regex(pattern).search(text) is not None
    return _contains_components(text, pattern)


def matches_exclusion(path: str | Path, patterns: Iterable[str], root: Path | None = None) -> bool:
    """The one file-exclusion predicate for the code-intelligence analyzers (#21004).

    True if *path* is in an excluded directory (when *root* is given: below *root*
    only, with the package-aware rule of ``is_excluded``) or any of *patterns*
    matches it. Patterns are matched against the path made relative to *root*, so a
    checkout under ``build/`` does not exclude everything; callers that hold an
    absolute path should always pass *root*.
    """
    if root is not None and is_excluded(Path(path), root, ANALYSIS_EXCLUDE_DIRS):
        return True
    text = Path(path).as_posix()
    if root is not None:
        try:
            text = Path(path).relative_to(root).as_posix()
        except ValueError:
            pass
    text = "/" + text.lstrip("/")
    return any(_pattern_matches(pattern, text) for pattern in patterns)


def _is_skipped_dir(parent: Path, name: str, excluded: Iterable[str]) -> bool:
    """True if directory *name* under *parent* is excluded (package-aware for archive/backup names)."""
    if name not in excluded:
        return False
    return not (name in PACKAGE_AWARE_NON_CODE_NAMES and (parent / name / "__init__.py").is_file())


def is_excluded(path: Path, root: Path, excluded: Iterable[str]) -> bool:
    """True if a directory component of *path* **below** *root* is excluded.

    Matching the absolute path asked whether an excluded name appears anywhere
    in it, including in the root itself, so a tree checked out below e.g. a
    ``venv`` directory scanned as empty (#13602, #20493). An archive/backup-style
    name is excluded only when that directory is not a Python package.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        # A path outside the root has no root-relative parts to judge. Treat it
        # as excluded, as is_skipped_path does: scanning something we cannot
        # place under the root is worse than skipping it (#20493).
        return True
    excluded = set(excluded)
    return any(_is_skipped_dir(root.joinpath(*parts[:i]), name, excluded) for i, name in enumerate(parts))


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
        dirnames[:] = [d for d in dirnames if not _is_skipped_dir(Path(dirpath), d, excluded)]
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
