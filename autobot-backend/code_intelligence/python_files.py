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
import threading
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Iterator, List, Set, Tuple

from autobot_shared.security.safe_open import open_under_root, read_text_under_root
from autobot_shared.testfile_names import is_test_filename
from utils.file_categorization import ALL_CODE_EXTENSIONS, PYTHON_EXTENSIONS, SKIP_DIRS

# The one directory-name exclusion rule for every code-intelligence analyzer
# (#21004): the repo-wide ``SKIP_DIRS`` plus ONE non-code rule, defined here once.
# ``PACKAGE_AWARE_NON_CODE_NAMES`` names archive/backup/vendored trees, but they are
# also legitimate package names (``autobot-backend/backup/`` is imported by the
# lifespan), so such a directory is skipped only when it is NOT a Python package
# (no ``__init__.py``). ``.mypy_cache`` is never code and is skipped always.
#
# Limits of the package check, pinned by tests: it looks ONLY at ``<dir>/__init__.py``.
# A PEP 420 namespace package (no ``__init__.py``) named like one of these is therefore
# treated as non-code, and so is a nested ``pkg/backup/`` without one. A directory that
# holds source files of another language (``.ts``/``.vue``/... from
# ``ALL_CODE_EXTENSIONS``) that the walk selects is code in that language and is kept;
# a Python-only walk (``*.py``) selects none, so there the ``__init__.py`` test decides.
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


_FOREIGN_SOURCE_EXTENSIONS = frozenset(ALL_CODE_EXTENSIONS - PYTHON_EXTENSIONS)


def _holds_foreign_source(directory: Path, patterns: Iterable[str]) -> bool:
    """True if *directory* holds a non-Python source file that one of *patterns* selects."""
    names = list(patterns)
    for _, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in _FOREIGN_SOURCE_EXTENSIONS and any(
                fnmatch.fnmatchcase(name, p) for p in names
            ):
                return True
    return False


def _is_skipped_dir(parent: Path, name: str, excluded: Iterable[str], holds_code: Callable[[Path], bool]) -> bool:
    """True if directory *name* under *parent* is excluded.

    An archive/backup-style name is kept when it is a Python package or when
    *holds_code* says it holds source of a language the caller scans.
    """
    if name not in excluded:
        return False
    if name not in PACKAGE_AWARE_NON_CODE_NAMES:
        return True
    directory = parent / name
    return not ((directory / "__init__.py").is_file() or holds_code(directory))


def is_excluded(path: Path, root: Path, excluded: Iterable[str]) -> bool:
    """True if a directory component of *path* **below** *root* is excluded.

    Matching the absolute path asked whether an excluded name appears anywhere
    in it, including in the root itself, so a tree checked out below e.g. a
    ``venv`` directory scanned as empty (#13602, #20493). An archive/backup-style
    name is excluded only when that directory is not a Python package and *path*
    is not itself a source file of another language.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        # A path outside the root has no root-relative parts to judge. Treat it
        # as excluded, as is_skipped_path does: scanning something we cannot
        # place under the root is worse than skipping it (#20493).
        return True
    excluded = set(excluded)
    foreign = path.suffix.lower() in _FOREIGN_SOURCE_EXTENSIONS
    return any(_is_skipped_dir(root.joinpath(*parts[:i]), n, excluded, lambda _d: foreign) for i, n in enumerate(parts))


def _leaf_location(real_root: Path, root: Path, dirpath: str, name: str, excluded: Set[str]) -> Path | None:
    """The path to yield for file *name* in *dirpath*, or ``None`` when it is not a contained, wanted file.

    Resolved through ``open_under_root`` (descriptor-relative, ``O_NOFOLLOW``), so a symlinked leaf is
    followed only while it stays inside the root and never into an excluded directory (#13602), and a
    component swapped for an out-of-root link after the walk listed it is refused, not read (#21289).
    """
    path = Path(dirpath) / name
    parts = path.relative_to(root).parts
    try:
        fd, final = open_under_root(str(real_root), parts)
    except (OSError, ValueError):
        return None
    os.close(fd)
    # The directory prune is only "may hold wanted files"; whether THIS file is excluded is
    # ``is_excluded``'s per-file answer, the same one ``matches_exclusion`` gives (#21004).
    if is_excluded(real_root.joinpath(*final), real_root, excluded) or is_excluded(path, root, excluded):
        return None
    return path


def _walk_matches(root: Path, patterns: List[str], excluded: Set[str]) -> Iterator[Path]:
    """Yield files under *root* matching a pattern, pruning excluded dirs while walking.

    ``os.fwalk`` descends by directory descriptor and refuses a subdirectory swapped for a link
    after it was listed, so the walk itself never leaves the root (#21289).
    """
    real_root = root.resolve()
    register_discovery_root(root)
    if not real_root.is_dir():
        return

    def holds(directory: Path) -> bool:
        return _holds_foreign_source(directory, patterns)

    # Walked by real path (a symlinked root is trusted configuration), reported under the caller's spelling.
    for real_dir, dirnames, filenames, _fd in os.fwalk(real_root, follow_symlinks=False):
        shown = root / os.path.relpath(real_dir, real_root)
        dirnames[:] = [d for d in dirnames if not _is_skipped_dir(shown, d, excluded, holds)]
        for name in filenames:
            if not any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
                continue
            found = _leaf_location(real_root, root, str(shown), name, excluded)
            if found is not None:
                yield found


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


# Roots that ``discover_files`` has walked (#21289). A detector later reads a discovered path through
# ``read_source_text``, which looks the root up here: the read then walks from the root descriptor with
# ``O_NOFOLLOW`` at every step, so a directory swapped for an out-of-root symlink between discovery and
# read is refused rather than followed. Discovery has no per-file handle to give back: callers receive
# plain ``Path``/``str`` values (the API stays compatible), so containment is re-established per read
# from the root, and no file descriptor outlives a call (no leaks on large trees).
_DISCOVERY_ROOTS: Set[str] = set()
_ROOTS_LOCK = threading.Lock()


def register_discovery_root(root: str | Path) -> None:
    """Remember *root* as a tree whose discovered files are read root-relative."""
    with _ROOTS_LOCK:
        _DISCOVERY_ROOTS.add(os.path.abspath(root))


def _locate(path: str | Path) -> Tuple[str, Tuple[str, ...]] | None:
    """``(root, parts)`` for the longest registered root containing *path*, or ``None`` if none does."""
    text = os.path.abspath(path)
    with _ROOTS_LOCK:
        roots = sorted(_DISCOVERY_ROOTS, key=len, reverse=True)
    for root in roots:
        if text.startswith(root.rstrip(os.sep) + os.sep):
            return root, Path(text).relative_to(root).parts
    return None


def read_source_text(path: str | Path, encoding: str = "utf-8", errors: str = "strict") -> str:
    """The one read of a source file for the code-intelligence detectors (#21289).

    A path below a root ``discover_files`` walked is read descriptor-relative from that root (see above);
    ``OSError``/``ValueError`` when a component was swapped for an out-of-root link. A path no discovery
    covers (a file the caller named directly) is read by name, as ``Path.read_text`` always did.
    """
    located = _locate(path)
    if located is None:
        return Path(path).read_text(encoding=encoding, errors=errors)
    return read_text_under_root(located[0], located[1], encoding, errors)
