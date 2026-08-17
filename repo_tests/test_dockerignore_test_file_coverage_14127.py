# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every tracked test file must be excluded from Docker build contexts (#14127).

`.dockerignore` excluded `**/*_test.py` (the suffix convention) but not
`**/test_*.py` (the prefix convention) -- both are test files by this repo's
own definition (`pytest.ini`'s `python_files = test_*.py *_test.py`, colocated
per #734), so the prefix form shipped into every Docker image built from
`docker/backend/Dockerfile`'s `COPY autobot-backend/ /app/autobot-backend/`
(and the sibling backends' equivalents). 58 files did, none referenced by
anything outside a test.

`autobot-backend/utils/secrets_store_migration_test.py` -- the file #14127
named specifically -- turned out to already be covered by the pre-existing
`**/*_test.py` rule; the real gap was the other naming convention, on files
that rule never looked at.

This is a static check against `.dockerignore`'s own patterns (a small,
Docker-syntax-compatible glob matcher, not a full spec implementation --
sufficient for the finite pattern set actually in this file), not a Docker
build -- so a new test file in either naming convention that predates its
own `.dockerignore` coverage fails here instead of shipping in an image.

The second half guards the other direction (#14413): a rule broad enough to
catch every test file also catches any *production* module named like one, and
excluding a module something imports at runtime is an ImportError in the image.
`**/test_*.py` did exactly that to `code_intelligence/test_pattern_analyzer.py`,
killing every backend container at startup; `**/*_test.py` had already done the
silent version to `utils/redis_immediate_test.py`. Both were renamed, not
allowlisted, and `test_no_shipped_module_imports_a_dockerignored_file` is what
keeps a rule this broad safe.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERIGNORE = _REPO_ROOT / ".dockerignore"

# Directories with their own dependency/packaging story (frontend bundlers,
# vendored trees) -- not backend Docker images, so not in scope for this check.
_EXCLUDED_ROOTS = ("autobot-frontend/", "autobot-slm-frontend/", "node_modules/")


def _dockerignore_patterns() -> list[str]:
    lines = _DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith(("#", "!"))]


def _matches_pattern(relative_posix: str, pattern: str) -> bool:
    """Docker-ignore-style match: a leading '**/' matches any depth, including zero;
    a plain pattern also excludes everything *under* a directory it names (`docs`
    excludes `docs/guides/x.py`), which is how Docker reads it.
    """
    parts = relative_posix.split("/")
    if pattern.startswith("**/"):
        tail = pattern[3:]
        return any(fnmatch.fnmatch("/".join(parts[i:]), tail) for i in range(len(parts)))
    if any(fnmatch.fnmatch("/".join(parts[:i]), pattern) for i in range(1, len(parts) + 1)):
        return True
    return fnmatch.fnmatch(parts[-1], pattern)


@lru_cache(maxsize=None)
def _is_dockerignored_cached(relative_posix: str, patterns: tuple[str, ...]) -> bool:
    return any(_matches_pattern(relative_posix, pattern) for pattern in patterns)


def _is_dockerignored(relative_posix: str, patterns) -> bool:
    """Memoised -- the import guard below asks about every tracked file once per
    sys.path root, which is tens of thousands of repeated questions."""
    return _is_dockerignored_cached(relative_posix, tuple(patterns))


@lru_cache(maxsize=None)
def _dockerignored_patterns_cached() -> tuple[str, ...]:
    return tuple(_dockerignore_patterns())


def _tracked_test_files() -> list[str]:
    """Every git-tracked file matching pytest's own test-file conventions
    (`python_files = test_*.py *_test.py` in pytest.ini), outside the frontend
    trees this check does not cover.
    """
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files", "*test_*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    files = [line for line in result.stdout.splitlines() if line.strip()]
    return [
        f
        for f in files
        if not f.startswith(_EXCLUDED_ROOTS) and (Path(f).name.startswith("test_") or Path(f).name.endswith("_test.py"))
    ]


def test_the_scan_actually_found_test_files():
    """An empty scan would make the assertion below vacuous."""
    assert len(_tracked_test_files()) > 100


def test_every_tracked_test_file_is_dockerignored():
    patterns = _dockerignore_patterns()
    missing = [f for f in _tracked_test_files() if not _is_dockerignored(f, patterns)]

    assert missing == [], (
        f"{len(missing)} tracked test file(s) are not excluded by .dockerignore and "
        f"will ship into a Docker image built from the repo root: {missing[:10]}"
        + (" ..." if len(missing) > 10 else "")
    )


def test_the_gap_that_was_missed_would_now_be_caught():
    """The reproduction, as a direct assertion on the matcher (#14127).

    `secrets_store_migration_test.py` (suffix convention) was already covered;
    `test_causal_executor.py` (prefix convention) was not, before `**/test_*.py`
    was added to `.dockerignore`.
    """
    patterns_before = [p for p in _dockerignore_patterns() if p != "**/test_*.py"]

    assert _is_dockerignored("autobot-backend/utils/secrets_store_migration_test.py", patterns_before)
    assert not _is_dockerignored("autobot-backend/orchestration/test_causal_executor.py", patterns_before)


def test_the_corrected_pattern_covers_the_prefix_convention():
    patterns = _dockerignored_patterns_cached()

    assert _is_dockerignored("autobot-backend/orchestration/test_causal_executor.py", patterns)


# ---------------------------------------------------------------------------
# The other half of the invariant (#14127): a rule broad enough to exclude every
# test file is only safe while no *shipped* module imports something it excludes.
# `**/test_*.py` was broad enough and did exactly that -- code_intelligence/
# __init__.py imported .test_pattern_analyzer (production code, prefix-named), so
# every backend container died at import with ModuleNotFoundError. The pre-existing
# `**/*_test.py` rule had already done the quieter version of the same thing:
# utils/async_cancellation.py imported utils.redis_immediate_test inside a bare
# `except Exception`, pinning `redis_available` to False in every image.
#
# The fix is a rename in both cases, not an allowlist -- an allowlist entry naming
# a moved file exempts nothing, silently. This check is what makes that safe.
# ---------------------------------------------------------------------------

_IMPORT_HEAD = re.compile(
    r"^[ \t]*(?:from[ \t]+(?P<dots>\.*)(?P<from_mod>[A-Za-z0-9_.]*)[ \t]+import\b"
    r"|import[ \t]+(?P<import_mods>[A-Za-z0-9_.]+(?:[ \t]*,[ \t]*[A-Za-z0-9_.]+)*))",
    re.MULTILINE,
)


def _import_heads(text: str) -> list[tuple[int, str, int]]:
    """(line, module, relative-level) for every import statement head.

    Only the head matters: a module name always sits on the statement's first
    line, even when the imported names are wrapped across several.
    """
    heads: list[tuple[int, str, int]] = []
    for match in _IMPORT_HEAD.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        if match.group("import_mods"):
            heads.extend((line, name.strip(), 0) for name in match.group("import_mods").split(","))
        else:
            heads.append((line, match.group("from_mod"), len(match.group("dots"))))
    return heads


def _module_index(files: list[str], patterns: list[str]) -> tuple[dict[str, str], set[str]]:
    """Map absolute dotted module name -> excluded file, plus the names that ship.

    Every top-level directory acts as a sys.path root (that is how the images run
    the backends), so one file yields a dotted name per root that contains it.
    """
    patterns = tuple(patterns)
    roots = sorted({f.split("/")[0] for f in files if "/" in f} | {""})
    excluded: dict[str, str] = {}
    shipped: set[str] = set()
    for relative in files:
        stem = relative[: -len(".py")].removesuffix("/__init__")
        for root in roots:
            prefix = f"{root}/" if root else ""
            if not stem.startswith(prefix):
                continue
            dotted = stem[len(prefix) :].replace("/", ".")
            if not dotted:
                continue
            if _is_dockerignored(relative, patterns):
                excluded.setdefault(dotted, relative)
            else:
                shipped.add(dotted)
    return excluded, shipped


def _imports_of_excluded_files(files, patterns, read_text) -> list[tuple[str, int, str]]:
    """Every (importer, line, excluded target) where a shipped file imports a file
    `.dockerignore` strips from the build context -- i.e. an ImportError waiting
    in the image. A name that *also* resolves to a shipped module is not a finding.
    """
    patterns = tuple(patterns)
    excluded, shipped = _module_index(files, patterns)
    tracked = set(files)
    findings: list[tuple[str, int, str]] = []
    for relative in files:
        if _is_dockerignored(relative, patterns):
            continue
        for line, module, level in _import_heads(read_text(relative)):
            if level:
                base = Path(relative).parent
                for _ in range(level - 1):
                    base = base.parent
                target = base.joinpath(*module.split(".")) if module else base
                candidates = [f"{target}.py", f"{target}/__init__.py"]
                findings.extend(
                    (relative, line, c) for c in candidates if c in tracked and _is_dockerignored(c, patterns)
                )
            elif module in excluded and module not in shipped:
                findings.append((relative, line, excluded[module]))
    return sorted(set(findings))


@lru_cache(maxsize=None)
def _tracked_python_files() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def _read_tracked(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8", errors="replace")


def test_no_shipped_module_imports_a_dockerignored_file():
    """The invariant, on the real tree: nothing that reaches an image imports
    something `.dockerignore` keeps out of it."""
    findings = _imports_of_excluded_files(_tracked_python_files(), _dockerignored_patterns_cached(), _read_tracked)

    assert findings == [], "shipped module(s) import a file .dockerignore strips from the build context: " + "; ".join(
        f"{importer}:{line} -> {target}" for importer, line, target in findings[:10]
    )


def test_the_import_scan_reaches_the_backend_trees():
    """An empty or backend-less scan would make the assertion above vacuous."""
    patterns = _dockerignored_patterns_cached()
    shipped = [f for f in _tracked_python_files() if not _is_dockerignored(f, patterns)]

    assert len(shipped) > 1000
    assert sum(1 for f in shipped if f.startswith("autobot-backend/")) > 100


def test_the_detector_catches_the_regression_it_was_written_for():
    """The reproduction, as a direct assertion on the detector (#14127).

    Both shapes that actually broke: a relative import of a prefix-named sibling
    (the ModuleNotFoundError that killed every backend container) and an absolute
    import of a suffix-named module (the silent one).
    """
    rules = ["**/test_*.py", "**/*_test.py"]
    sources = {
        "backend/pkg/__init__.py": "from .test_analyzer import Analyzer\n",
        "backend/pkg/test_analyzer.py": "",
        "backend/utils/caller.py": "def check():\n    from utils.circuit_test import breaker\n",
        "backend/utils/circuit_test.py": "",
    }

    findings = _imports_of_excluded_files(list(sources), rules, sources.__getitem__)

    assert findings == [
        ("backend/pkg/__init__.py", 1, "backend/pkg/test_analyzer.py"),
        ("backend/utils/caller.py", 2, "backend/utils/circuit_test.py"),
    ]

    # ... and stays quiet once the modules are renamed out of the test conventions,
    # which is the fix that was applied rather than an allowlist entry.
    renamed = {
        "backend/pkg/__init__.py": "from .testing_analyzer import Analyzer\n",
        "backend/pkg/testing_analyzer.py": "",
        "backend/utils/caller.py": "def check():\n    from utils.circuit_connection import breaker\n",
        "backend/utils/circuit_connection.py": "",
    }

    assert _imports_of_excluded_files(list(renamed), rules, renamed.__getitem__) == []


def test_no_negation_line_re_includes_a_python_file():
    """`_dockerignore_patterns()` drops `!` lines, so a Python re-include would make
    every check above read a file as excluded when Docker ships it. Keep the fix a
    rename, not an exemption."""
    negations = [
        line.strip()[1:]
        for line in _DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("!")
    ]

    assert [n for n in negations if n.endswith(".py") or n.endswith("*")] == []
