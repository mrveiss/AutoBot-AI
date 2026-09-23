# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A test may stub a production enum, but never invent one of its members (#14881).

THE CONTRACT THAT WAS NOT ENFORCED
-----------------------------------
`api/marketplace_422_test.py` stated it in a comment: *"Local re-definition of
the enums (same values as api/marketplace.py). These are kept in sync by the
test assertions below."* The assertions it referred to compared that file's copy
against a THIRD hardcoded literal set a few lines further down, and never
imported the production module at all. A manual-sync contract whose enforcement
is itself a copy cannot see drift. That file now imports the real enums and the
parity class is gone.

WHY THE OTHER COPIES ARE NOT SIMPLY DELETED
--------------------------------------------
The remaining ones are not laziness. They are harness scaffolding: the test
registers a stub in ``sys.modules`` so a route module can be imported without
its real dependency graph, and FastAPI rejects anything but a real ``str``-enum
subclass as a Query-parameter type, so the stub must contain actual enum
classes. Importing the production enum there would defeat the isolation the
stub exists to provide. Telling those tests to "just import it" would be a
worse codebase, so this guard does not.

THE RULE, WHICH IS ASYMMETRIC ON PURPOSE
-----------------------------------------
For a test-local enum whose name matches a production enum:

* **A SUBSET is fine.** A stub only needs the members its test exercises.
  ``_SSOProviderType`` declares 5 of production's 9 and that is not a defect.
* **An EXTRA member is a failure.** A member production does not have is a
  value the real system cannot produce, so any test exercising it asserts
  against a fiction and passes while the behaviour is unreachable.
* **An EXACT copy is a failure unless declared scaffolding.** If the member
  sets match and nothing forces a stub, the copy should be an import.

MEASURED, NOT ASSUMED (origin/main at the time of #14881)
----------------------------------------------------------
The rule was written after running it: 436 production enum names, 10 test-local
ones, 7 sharing a name. It found two real defects that the issue predicted in
the opposite direction -- it expected production to gain values invisible to the
copies, and what had actually happened was the copies carrying values production
never had:

* ``BatchJobType`` stubs declared ``ai_task`` and ``report``. Production
  (`api/schemas_workflows.py`) has neither, and has ``file_conversion``,
  ``report_generation``, ``backup`` and ``custom``, which the stubs omitted.
* ``_ErrorCategory`` stubs declared ``CLIENT_ERROR``. Production's
  ``ErrorCategory`` has 18 members and that is not one of them.

Neither invented member was referenced by any test, which is why nothing failed
and why only a census found them.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Dict, FrozenSet, List, Set, Tuple

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()

_ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "IntFlag", "Flag"}

#: Test-local enums that MUST stay, with the reason. Each is injected into a
#: ``sys.modules`` stub so a production module can be imported without its real
#: dependency graph; FastAPI requires a real str-enum for Query parameters, so a
#: Mock cannot serve. Being listed here does NOT exempt them from the
#: no-invented-member rule below -- it only permits the copy to exist.
_DECLARED_SCAFFOLDING: Dict[Tuple[str, str], str] = {
    (
        "autobot-backend/api/batch_jobs_schedules_test.py",
        "BatchJobStatus",
    ): "stubs api.schemas_workflows for a route import; FastAPI needs a real str-enum Query type",
    (
        "autobot-backend/tests/test_health_probe_data_contract.py",
        "BatchJobStatus",
    ): "same stub, same reason (#12463 real-load path falls back to it)",
    (
        "autobot-backend/api/batch_jobs_schedules_test.py",
        "BatchJobType",
    ): "same api.schemas_workflows stub as BatchJobStatus above; exact only since #14881 aligned it",
    (
        "autobot-backend/tests/test_health_probe_data_contract.py",
        "BatchJobType",
    ): "same api.schemas_workflows stub as BatchJobStatus above; exact only since #14881 aligned it",
    (
        "autobot-slm-backend/tests/api/test_node_update_availability_11964.py",
        "CodeStatus",
    ): "injected into a MagicMock stub of models.database",
    (
        "autobot-slm-backend/tests/api/test_apply_secrets.py",
        "_NodeStatus",
    ): "injected into a MagicMock stub of models.database",
    (
        "autobot-slm-backend/tests/api/test_apply_secrets.py",
        "_BackupServiceType",
    ): "injected into a MagicMock stub of models.database",
}

#: Genuine name collisions: a test enum that shares a production enum's NAME
#: while meaning something else. Empty today -- the sweep found none -- and kept
#: so that the honest answer to one is a declared exemption rather than deleting
#: the guard (#14881 acceptance criterion 4). Adding an entry requires saying
#: what the two concepts are.
_DISTINCT_CONCEPTS: Dict[Tuple[str, str], str] = {}

#: A sweep that reads nothing reports clean over anything. Measured at 6,000+
#: tracked .py files; the floor sits well below that so ordinary growth never
#: trips it while a broken `git ls-files` does.
_MIN_SOURCE_FILES = 3000


def _tracked_python() -> List[str]:
    """Tracked ``.py`` paths, through the one canonical enumeration (#15926).

    Not a direct ``git ls-files``: ``one_git_enumeration_15926_test`` counts
    those across ``repo_tests/`` and its floor only ever shrinks, so a new guard
    that shells out for itself is a regression even when it works. ``exclude``
    becomes a git ``:(exclude)`` pathspec, so git does the matching rather than
    a second matcher in Python disagreeing with the first (#15510).
    """
    return tracked_paths(REPO_ROOT, "*.py", exclude=(".worktrees",))


def is_test_path(rel: str) -> bool:
    base = rel.rsplit("/", 1)[-1]
    return base.startswith("test_") or base.endswith("_test.py") or "/tests/" in f"/{rel}"


def enum_members(source: str) -> Dict[str, FrozenSet[str]]:
    """Every enum class in *source*, mapped to its member names.

    Raises ``SyntaxError`` on unparseable input rather than returning empty: a
    file the sweep could not read is not a file with no enums in it.
    """
    tree = ast.parse(source)
    found: Dict[str, FrozenSet[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id for b in node.bases if isinstance(b, ast.Name)} | {
            b.attr for b in node.bases if isinstance(b, ast.Attribute)
        }
        if not (bases & _ENUM_BASES):
            continue
        members = frozenset(
            t.id for stmt in node.body if isinstance(stmt, ast.Assign) for t in stmt.targets if isinstance(t, ast.Name)
        )
        if members:
            found[node.name] = members
    return found


def _scan() -> Tuple[Dict[str, Set[str]], Dict[Tuple[str, str], FrozenSet[str]], List[str]]:
    """Return (production name -> union of members, (test file, name) -> members, unreadable)."""
    production: Dict[str, Set[str]] = defaultdict(set)
    tests: Dict[Tuple[str, str], FrozenSet[str]] = {}
    unreadable: List[str] = []
    for rel in _SOURCES:
        try:
            found = enum_members((REPO_ROOT / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            unreadable.append(f"{rel}: {exc}")
            continue
        for name, members in found.items():
            if is_test_path(rel):
                tests[(rel, name)] = members
            else:
                # Union across every production definition of that name: a member
                # is only "invented" when NO production enum of that name has it.
                production[name].update(members)
    return production, tests, unreadable


_SOURCES = _tracked_python()


def test_the_sweep_reached_the_tree() -> None:
    assert len(_SOURCES) >= _MIN_SOURCE_FILES, (
        f"only {len(_SOURCES)} tracked .py files found, floor is {_MIN_SOURCE_FILES}. "
        "FIX THE SWEEP — a guard that reads nothing reports clean over anything."
    )


def test_the_scan_could_read_every_file() -> None:
    """An unparseable file is a failure, never a clean report."""
    _, _, unreadable = _scan()
    assert not unreadable, f"could not examine {len(unreadable)} file(s): {unreadable[:5]}"


def _production_for(production: Dict[str, Set[str]], name: str) -> Set[str] | None:
    return production.get(name) or production.get(name.lstrip("_"))


def test_no_test_enum_invents_a_member_production_lacks() -> None:
    """The defect class this guard exists for: asserting against a value that cannot exist."""
    production, tests, _ = _scan()
    offenders: List[str] = []
    for (rel, name), members in sorted(tests.items()):
        if (rel, name) in _DISTINCT_CONCEPTS:
            continue
        real = _production_for(production, name)
        if real is None:
            continue
        invented = members - real
        if invented:
            offenders.append(f"{rel}::{name} declares {sorted(invented)}, which production's {name} does not have")
    assert not offenders, (
        "A test-local enum declares members production does not have. A test exercising one "
        "asserts against a value the real system cannot produce:\n  " + "\n  ".join(offenders) + "\n\n"
        "Fix the stub to mirror production. A stub may be a SUBSET — it only needs the members "
        "its test uses — but it may never invent one. If the name is a genuine collision with an "
        "unrelated concept, add it to _DISTINCT_CONCEPTS with both concepts named."
    )


def test_an_exact_copy_is_imported_rather_than_redeclared() -> None:
    """An identical copy with no stubbing reason should be an import."""
    production, tests, _ = _scan()
    offenders: List[str] = []
    for (rel, name), members in sorted(tests.items()):
        if (rel, name) in _DECLARED_SCAFFOLDING or (rel, name) in _DISTINCT_CONCEPTS:
            continue
        real = _production_for(production, name)
        if real is not None and members == set(real):
            offenders.append(f"{rel}::{name}")
    assert not offenders, (
        "These test-local enums exactly duplicate a production enum with no declared reason:\n  "
        + "\n  ".join(offenders)
        + "\n\nImport the production enum instead — api/marketplace_422_test.py is the worked "
        "example. If the test must stub the module (FastAPI Query types need a real str-enum, "
        "and a Mock will not do), add it to _DECLARED_SCAFFOLDING with the reason."
    )


def test_declared_scaffolding_is_not_stale() -> None:
    """An entry whose file or enum is gone must be removed, not left to rot."""
    _, tests, _ = _scan()
    stale = sorted(f"{rel}::{name}" for (rel, name) in _DECLARED_SCAFFOLDING if (rel, name) not in tests)
    assert not stale, (
        f"_DECLARED_SCAFFOLDING names {len(stale)} entry/entries that no longer exist: {stale}. "
        "The copy was removed — drop the exemption with it."
    )


# ---------------------------------------------------------------------------
# The rule itself, on synthetic sources, so each branch is proven independently
# of whatever the tree happens to contain today.
# ---------------------------------------------------------------------------

_PROD = """
from enum import Enum


class Colour(str, Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
"""


@pytest.mark.parametrize(
    "label,source,expect_members",
    [
        ("subset stub is legitimate", "from enum import Enum\n\nclass Colour(str, Enum):\n    RED = 'red'\n", {"RED"}),
        (
            "invented member",
            "from enum import Enum\n\nclass Colour(str, Enum):\n    RED = 'red'\n    MAUVE = 'mauve'\n",
            {"RED", "MAUVE"},
        ),
    ],
)
def test_rule_classifies_a_stub(label: str, source: str, expect_members: Set[str]) -> None:
    real = set(enum_members(_PROD)["Colour"])
    members = set(enum_members(source)["Colour"])
    assert members == expect_members, label
    invented = members - real
    assert bool(invented) is ("invented" in label), label


def test_an_unparseable_source_raises_rather_than_reporting_no_enums() -> None:
    with pytest.raises(SyntaxError):
        enum_members("class Broken(:\n")
