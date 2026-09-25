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

import ast
import pathlib
import re
from typing import Dict, List

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

#: Names whose use implies SQLAlchemy's async engine, and therefore greenlet.
#: `async_engine_from_config` was missing, and `run_async_migrations` in
#: `autobot-backend/migrations/env.py` reaches the async engine through it and
#: through no other name in this set -- so a service doing the same passed this
#: guard without declaring greenlet (#17433 review). All are
#: `sqlalchemy.ext.asyncio` entry points.
_ASYNC_MARKERS = (
    "AsyncSession",
    "create_async_engine",
    "async_engine_from_config",
    "async_sessionmaker",
    "AsyncEngine",
    "AsyncConnection",
)
_SQLALCHEMY = re.compile(r"^sqlalchemy\b", re.IGNORECASE | re.MULTILINE)
_GREENLET_SPEC = re.compile(r"^greenlet\s*(==|>=)\s*\d", re.IGNORECASE)


def _declares_greenlet_unconditionally(text: str) -> bool:
    """A greenlet line with a floor and **no environment marker** (#17433 review).

    The old check was a regex over the whole file and accepted
    `greenlet>=3.1.0; python_version < "3.0"` -- a declaration that can never
    install on the 3.14 runtime, counted as satisfying the rule. Verified: the
    prior pattern matched that line.

    The rule is unconditional declaration, because **conditionality is the
    defect**. greenlet went missing precisely because SQLAlchemy declared it
    behind an extra and a `platform_machine` marker, so a marker here rebuilds
    the failure this guard exists to catch. A marker requires a PEP 508
    evaluation against the target environment to judge, and this guard does not
    know the target environment -- so it refuses markers rather than guessing
    which are benign.
    """
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not _GREENLET_SPEC.match(line):
            continue
        if ";" in line:
            continue  # carries an environment marker: conditional again
        return True
    return False


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
        if _references_async_marker(text):
            return True
    return False


def _references_async_marker(text: str) -> bool:
    """Whether the module REFERENCES an async-engine name, rather than mentioning it (#17433 review).

    The previous check was `any(marker in text ...)` over the raw file, so a
    comment or docstring saying "AsyncSession" made a purely synchronous service
    require greenlet. That is a false positive, and an over-strict guard gets
    narrowed by whoever it inconveniences.

    Identifiers are the right unit here and `ast` gives them exactly: an import
    alias, a bare name, or an attribute access. Prose produces no `Name` node,
    so a docstring describing the async engine is correctly silent. Substring
    first for speed -- a file not mentioning the name at all cannot reference
    it, and parsing every module is what took a sibling guard past 120s.
    """
    if not any(marker in text for marker in _ASYNC_MARKERS):
        return False
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        # Unparseable: fall back to the substring answer rather than silently
        # reporting "no async usage", which would be a pass by failure to read.
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.alias) and node.name in _ASYNC_MARKERS:
            return True
        if isinstance(node, ast.Name) and node.id in _ASYNC_MARKERS:
            return True
        if isinstance(node, ast.Attribute) and node.attr in _ASYNC_MARKERS:
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
    return not _declares_greenlet_unconditionally((root / relative).read_text(encoding="utf-8"))


def _violations(root: pathlib.Path) -> List[str]:
    return [rel for rel in _declares_sqlalchemy(root) if _violates(root, rel)]


def _service_fixture(
    root: pathlib.Path,
    *,
    greenlet: str | None = None,
    marker: str = "AsyncSession",
    mention_only: bool = False,
) -> pathlib.Path:
    """A minimal service: requirements declaring SQLAlchemy, and code touching the async engine.

    *greenlet* is the literal requirements line, so a fixture can supply a
    marker-carrying declaration. *mention_only* names the async marker in a
    docstring without referencing it, which must NOT count as usage.
    """
    service = root / "svc"
    service.mkdir(parents=True, exist_ok=True)
    body = (
        f'"""This module deliberately does not use {marker}."""\nimport os\n'
        if mention_only
        else (f"from sqlalchemy.ext.asyncio import {marker}\n\n\ndef f(): return {marker}\n")
    )
    (service / "app.py").write_text(body, encoding="utf-8")
    lines = ["sqlalchemy>=2.0.54\n"]
    if greenlet is not None:
        lines.append(greenlet if greenlet.endswith("\n") else greenlet + "\n")
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
    _service_fixture(tmp_path)

    assert _violations(tmp_path) == ["svc/requirements.txt"]


def test_the_detector_passes_a_service_that_declares_greenlet(tmp_path: pathlib.Path) -> None:
    """The other half. Without it, "flags the bad fixture" is satisfied by flagging everything."""
    _service_fixture(tmp_path, greenlet="greenlet>=3.1.0")

    assert _violations(tmp_path) == []


def test_the_exemption_list_still_matches_the_tree() -> None:
    """An exemption naming a file the tree no longer has is a hole nobody reopened."""
    present = set(_declares_sqlalchemy())
    stale = sorted(set(_NO_SIBLING_SOURCE) - present)
    assert not stale, f"exempted requirements files are gone; delete the entries: {stale}"


@pytest.mark.parametrize("marker", _ASYNC_MARKERS)
def test_every_async_marker_is_detected(marker: str, tmp_path: pathlib.Path) -> None:
    """Each entry in the marker set must actually make a service require greenlet.

    Parametrised so the set cannot quietly shrink: `async_engine_from_config`
    was missing and is the async-engine entry point
    `autobot-backend/migrations/env.py` uses, so a service reaching it only
    that way passed this guard (#17433 review). An unexercised entry is
    indistinguishable from an absent one.
    """
    _service_fixture(tmp_path, marker=marker)

    assert _violations(tmp_path) == ["svc/requirements.txt"], f"{marker} is not detected as async usage"


def test_a_greenlet_declaration_behind_an_environment_marker_is_refused(tmp_path: pathlib.Path) -> None:
    """`greenlet>=3.1.0; python_version < "3.0"` can never install on the 3.14 runtime.

    The prior floor regex accepted it -- verified against the old pattern before
    changing it. Conditionality is the defect this guard exists for: greenlet
    went missing because SQLAlchemy declared it behind an extra and a
    `platform_machine` marker, so a marker here rebuilds exactly that.
    """
    _service_fixture(tmp_path, greenlet='greenlet>=3.1.0; python_version < "3.0"')

    assert _violations(tmp_path) == ["svc/requirements.txt"]


def test_naming_the_async_engine_in_prose_is_not_using_it(tmp_path: pathlib.Path) -> None:
    """A docstring mentioning `AsyncSession` must not make a sync service require greenlet.

    The prior check was `any(marker in text ...)` over the raw file. An
    over-strict guard is not the safe direction -- it gets narrowed by whoever
    it inconveniences, and the narrowing is where the real coverage is lost.
    """
    _service_fixture(tmp_path, mention_only=True)

    assert _violations(tmp_path) == []


def test_the_marker_set_still_detects_the_real_migrations_module() -> None:
    """An anchor OUTSIDE `_ASYNC_MARKERS`, because the parametrised test is inside it.

    `test_every_async_marker_is_detected` is parametrised over `_ASYNC_MARKERS`,
    so deleting an entry deletes its own test case -- a mutation proved that
    dropping `async_engine_from_config` left 15 tests passing. **A set that
    supplies its own test cases cannot notice becoming smaller.**

    `autobot-backend/migrations/env.py` references exactly one async-engine
    name, `async_engine_from_config`, and no other marker in the set (verified:
    every other marker has zero occurrences in that file). So it is a real-code
    anchor for the entry the review found missing -- remove that entry and this
    fails, where the parametrised test cannot.
    """
    env = repo_root() / "autobot-backend" / "migrations" / "env.py"
    assert env.is_file(), "the anchor file is gone; re-point this test rather than deleting it"

    assert _references_async_marker(env.read_text(encoding="utf-8")), (
        "migrations/env.py reaches SQLAlchemy's async engine and is no longer detected -- "
        "an entry has been dropped from _ASYNC_MARKERS"
    )
