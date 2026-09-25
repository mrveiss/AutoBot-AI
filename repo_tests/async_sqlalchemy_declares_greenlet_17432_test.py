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

#: Requirements files excused from the rule, each with its reason. Empty on
#: purpose: `requirements-ci/storage.txt` was the candidate and is **mirrored**
#: instead (`greenlet==3.3.2`), because "nothing has been observed failing
#: there" is not "it does not need it" -- and that exact invisibility is what
#: hid #17432 for a day. A test that skips, or never opens an async engine,
#: observes nothing either way.
#:
#: The mechanism stays so a future exemption must carry a reason and cannot
#: outlive its file (`test_the_exemption_list_still_matches_the_tree`).
_NO_SIBLING_SOURCE: Dict[str, str] = {}

#: STATED LIMITATION: a requirements file with no sibling Python tree --
#: `requirements-ci/*.txt` is the live example -- reaches the async-usage check
#: and finds nothing, so it passes without being examined. That is a pass by
#: absence of evidence, not by evidence of absence. It is recorded here rather
#: than hidden because the rule this guard enforces is exactly that distinction;
#: closing it means teaching the guard which test suites run against which
#: requirements set, which nothing in the tree currently records.


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


def _violates(root: pathlib.Path, relative: str) -> bool:
    """Does *relative* need greenlet and not declare it?

    The ONE predicate. Both the real-tree test and the synthetic fixtures below
    call it, so the fixtures prove the detector rather than a copy of its logic
    -- a contrast test that re-states the rule agrees with itself and catches
    nothing (#17407 is that failure, in another guard, today).
    """
    if relative in _NO_SIBLING_SOURCE:
        return False
    if not _uses_async_engine(root, (root / relative).parent):
        return False
    return not _GREENLET_FLOOR.search((root / relative).read_text(encoding="utf-8"))


def _violations(root: pathlib.Path) -> List[str]:
    return [rel for rel in _declares_sqlalchemy(root) if _violates(root, rel)]


def _service_fixture(root: pathlib.Path, *, with_greenlet: bool) -> pathlib.Path:
    """A minimal service: requirements declaring SQLAlchemy, and code using the async engine."""
    service = root / "svc"
    service.mkdir(parents=True, exist_ok=True)
    (service / "app.py").write_text(
        "from sqlalchemy.ext.asyncio import AsyncSession\n\n\nasync def f(s: AsyncSession): ...\n",
        encoding="utf-8",
    )
    lines = ["sqlalchemy>=2.0.54\n"]
    if with_greenlet:
        lines.append("greenlet>=3.1.0\n")
    (service / "requirements.txt").write_text("".join(lines), encoding="utf-8")
    return service


@pytest.mark.parametrize("relative", _declares_sqlalchemy())
def test_a_service_using_the_async_engine_declares_greenlet(relative: str) -> None:
    if relative in _NO_SIBLING_SOURCE:
        pytest.skip(f"{relative}: {_NO_SIBLING_SOURCE[relative]}")

    assert not _violates(repo_root(), relative), (
        f"{relative} declares SQLAlchemy and its service uses the async engine "
        "(AsyncSession / create_async_engine), but does not declare greenlet with a floor. "
        "SQLAlchemy supplies greenlet only via an extra or a platform_machine marker, so it "
        "can stop arriving without any commit here -- which is what took `main` red in #17432."
    )


def test_the_detector_flags_a_service_missing_greenlet(tmp_path: pathlib.Path) -> None:
    """The negative case, without which this guard proves nothing about itself.

    Review found the parametrised test above iterates the REAL tree, and the
    tree now declares greenlet everywhere -- so it passes trivially and would
    pass identically if the detector were broken. A local mutation showed the
    detector worked on the day it was written; it left nothing in the suite to
    catch it breaking later.

    That is the third instance of this shape found today in one repo, each time
    by someone other than the author: a glob blind to `storage.txt`, an
    exclusion keyed on a filename that moved, and an async-usage check that
    passed a file it never examined. **A detector with no contrast pair is the
    same family as no detector at all** -- it reports clean either way.
    """
    _service_fixture(tmp_path, with_greenlet=False)

    assert _violations(tmp_path) == ["svc/requirements.txt"]


def test_the_detector_passes_a_service_that_declares_greenlet(tmp_path: pathlib.Path) -> None:
    """The other half. Without it, "flags the bad fixture" is satisfied by flagging everything."""
    _service_fixture(tmp_path, with_greenlet=True)

    assert _violations(tmp_path) == []


def test_the_exemption_list_still_matches_the_tree() -> None:
    """An exemption naming a file the tree no longer has is a hole nobody reopened."""
    present = set(_declares_sqlalchemy())
    stale = sorted(set(_NO_SIBLING_SOURCE) - present)
    assert not stale, f"exempted requirements files are gone; delete the entries: {stale}"
