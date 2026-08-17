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
"""

from __future__ import annotations

import fnmatch
import subprocess
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
    """Docker-ignore-style match: a leading '**/' matches any depth, including zero."""
    if pattern.startswith("**/"):
        tail = pattern[3:]
        parts = relative_posix.split("/")
        return any(fnmatch.fnmatch("/".join(parts[i:]), tail) for i in range(len(parts)))
    return fnmatch.fnmatch(relative_posix, pattern) or fnmatch.fnmatch(Path(relative_posix).name, pattern)


def _is_dockerignored(relative_posix: str, patterns: list[str]) -> bool:
    return any(_matches_pattern(relative_posix, pattern) for pattern in patterns)


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
    patterns = _dockerignore_patterns()

    assert _is_dockerignored("autobot-backend/orchestration/test_causal_executor.py", patterns)
