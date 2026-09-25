# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A service using SQLAlchemy's async engine declares greenlet itself (#17432).

On 2026-09-24 every `docker-smoke-test` run began failing, on every branch
including `main`:

    Container autobot-slm  Error
    ModuleNotFoundError: No module named 'greenlet'

`greenlet` appeared in no requirements file in the tree. SQLAlchemy needs it for
`AsyncSession` / `create_async_engine`, and it had been arriving transitively --
SQLAlchemy declares it under an `[asyncio]` extra AND, in some releases, under a
`platform_machine == "x86_64" or ...` marker. So whether it arrives depends on
which release a `>=` floor resolves to and on the machine doing the resolving.
Neither is a property this repo controls, and both changed without a commit here.

Six PRs were blocked behind a red base, because `smoke-test` and
`hardened-smoke-test` are required contexts. That is the cost of a transitive
runtime dependency: nothing in the tree records the requirement, so nothing
fails when it stops being met until a container will not start.

The rule this pins: **if a service's own code uses the async engine, its own
requirements declare greenlet.** Not the extra -- an extra is still an
inheritance, and the point is to stop inheriting.
"""

from __future__ import annotations

import pathlib
import re
from typing import Dict, List

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ASYNC_MARKERS = ("AsyncSession", "create_async_engine")
_SQLALCHEMY = re.compile(r"^sqlalchemy\b", re.IGNORECASE | re.MULTILINE)
_GREENLET_FLOOR = re.compile(r"^greenlet\s*(==|>=)\s*\d", re.IGNORECASE | re.MULTILINE)

#: Requirements files with no sibling source tree to scan. Each needs its own
#: reason, so the list cannot quietly absorb a service that simply forgot.
_NO_SIBLING_SOURCE: Dict[str, str] = {
    "requirements-ci/storage.txt": (
        "a CI-only dependency set, not a deployed service: it has no source tree of its own, "
        "and it pins exact versions rather than floors. It declares sqlalchemy and aiosqlite, so "
        "async-engine tests running against it would need greenlet -- but no failure has been "
        "observed there, and #17432 deliberately did not change it in the PR whose job was "
        "unblocking a red base. Recorded rather than fixed blind."
    ),
}


def _requirements_files(root: pathlib.Path) -> List[pathlib.Path]:
    """`requirements*.txt` anywhere, plus any `.txt` inside a `requirements*` directory.

    The second clause is not tidiness: `requirements-ci/storage.txt` declares
    SQLAlchemy and its filename is `storage.txt`, so a `requirements*.txt` glob
    misses it entirely. The first version of this scan did, and the exemption
    staleness test below caught it -- the exemption named a file the scan could
    not see, which read as "the file is gone" rather than "the scan is narrow".
    """
    seen: set[pathlib.Path] = set()
    for pattern in ("requirements*.txt", "requirements*/*.txt", "requirements*/**/*.txt"):
        for path in root.rglob(pattern):
            if any(part in {"venv", ".venv", "node_modules", ".git"} for part in path.parts):
                continue
            seen.add(path)
    return sorted(seen)


def _declares_sqlalchemy(root: pathlib.Path | None = None) -> List[str]:
    """Requirements files that declare SQLAlchemy, repo-relative."""
    base = root or repo_root()
    found: List[str] = []
    for path in _requirements_files(base):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _SQLALCHEMY.search(text):
            found.append(str(path.relative_to(base)))
    return found


def _uses_async_engine(base: pathlib.Path, service_dir: pathlib.Path) -> bool:
    for path in service_dir.rglob("*.py"):
        if any(part in {"venv", ".venv", "node_modules"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(marker in text for marker in _ASYNC_MARKERS):
            return True
    return False


SQLALCHEMY_DECLARATIONS = declare(
    "sqlalchemy-requirements-files",
    discover=_declares_sqlalchemy,
    floor=3,
    growth=3,
    what="requirements files declaring SQLAlchemy (#17432)",
)


def test_the_sweep_finds_the_declarations() -> None:
    """`no offender found` must not be reachable by finding no requirements files."""
    SQLALCHEMY_DECLARATIONS.verify_floor(repo_root())


@pytest.mark.parametrize("relative", _declares_sqlalchemy())
def test_a_service_using_the_async_engine_declares_greenlet(relative: str) -> None:
    base = repo_root()
    text = (base / relative).read_text(encoding="utf-8")
    if relative in _NO_SIBLING_SOURCE:
        pytest.skip(f"{relative}: {_NO_SIBLING_SOURCE[relative]}")

    service_dir = (base / relative).parent
    if not _uses_async_engine(base, service_dir):
        return  # declares SQLAlchemy but never opens an async engine

    assert _GREENLET_FLOOR.search(text), (
        f"{relative} declares SQLAlchemy and its service uses the async engine "
        "(AsyncSession / create_async_engine), but does not declare greenlet with a floor. "
        "SQLAlchemy supplies greenlet only via an extra or a platform_machine marker, so it "
        "can stop arriving without any commit here -- which is what took `main` red in #17432."
    )


def test_the_exemption_list_still_matches_the_tree() -> None:
    """An exemption naming a file the tree no longer has is a hole nobody reopened."""
    present = set(_declares_sqlalchemy())
    stale = sorted(set(_NO_SIBLING_SOURCE) - present)
    assert not stale, f"exempted requirements files are gone; delete the entries: {stale}"
