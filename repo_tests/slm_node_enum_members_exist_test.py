# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every SLM reference to a node enum member names a member that exists.

``api/nodes.py`` re-enroll used ``EventType.STATUS_CHANGED``; the member is
``STATE_CHANGE``. Python resolves enum attributes only when the line runs, so
the route raised ``AttributeError`` after deleting the node's credentials and
before its commit: every re-enroll of a decommissioned node was a 500, since
#2681 shipped it, and nothing failed until a user pressed the button.

The members are read from ``models/database.py`` by AST, so this guard needs
neither the ORM nor the SLM's stubbed test packages.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-slm-backend",)
_ENUM_HOME = "autobot-slm-backend/models/database.py"
#: The node-event enums defined in ``models/database.py`` and referenced by member across the SLM.
_ENUMS = ("EventType", "EventSeverity")


def _is_source(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return (
        rel.endswith(".py") and "/tests/" not in rel and not name.startswith("test_") and not name.endswith("_test.py")
    )


def _source_population(root: Path) -> list[str]:
    try:
        return [rel for rel in tracked_paths(root, *_ROOTS) if _is_source(rel)]
    except EmptyEnumeration:
        return []


def _all_python(root: Path) -> int:
    try:
        return sum(1 for rel in tracked_paths(root, *_ROOTS) if rel.endswith(".py"))
    except EmptyEnumeration:
        return 0


#: Measured 2026-10-17: 562 tracked SLM .py files, roughly half non-test source.
REACH = declare(
    "slm-node-enum-members-exist",
    discover=_source_population,
    reference=_all_python,
    min_fraction=0.35,
    what="non-test SLM python source",
    roots=_ROOTS,
)


def enum_members(source: str) -> dict[str, set[str]]:
    """``{enum: {member names}}`` for the node enums defined in *source*."""
    found: dict[str, set[str]] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef) and node.name in _ENUMS:
            found[node.name] = {
                t.id for b in node.body if isinstance(b, ast.Assign) for t in b.targets if isinstance(t, ast.Name)
            }
    return found


def unknown_members(source: str, members: dict[str, set[str]]) -> list[tuple[int, str]]:
    """``(line, "Enum.MEMBER")`` for every reference to a member the enum lacks."""
    bad = []
    for enum, names in members.items():
        for match in re.finditer(rf"\b{enum}\.([A-Z][A-Z0-9_]*)\b", source):
            if match.group(1) not in names:
                bad.append((source.count("\n", 0, match.start()) + 1, f"{enum}.{match.group(1)}"))
    return bad


def imports_node_enums(source: str) -> bool:
    """True for every import form that can reach the enums, qualified ``import models.database`` included."""
    return bool(re.search(r"^\s*(from models(\.database)? import|import models(\.database)?\b)", source, re.M))


def _members() -> dict[str, set[str]]:
    return enum_members((repo_root() / _ENUM_HOME).read_text(encoding="utf-8"))


def test_the_node_enums_are_found():
    members = _members()
    assert set(members) == set(_ENUMS), sorted(members)
    assert "STATE_CHANGE" in members["EventType"]


def test_every_referenced_node_enum_member_exists():
    root, members, bad = repo_root(), _members(), []
    examined = REACH.examined(root)
    for rel in examined:
        source = (root / rel).read_text(encoding="utf-8")
        if imports_node_enums(source):
            bad += [f"{rel}:{line} {ref}" for line, ref in unknown_members(source, members)]
    REACH.completed(len(examined), root)
    assert not bad, f"references to node enum members that do not exist: {bad}"


def test_every_import_form_is_recognised_and_an_unrelated_one_is_not():
    for form in (
        "from models.database import EventType",
        "from models import EventType",
        "import models.database",
        "import models.database as db",
        "import models",
    ):
        assert imports_node_enums(f"{form}\n"), form
    assert not imports_node_enums("from my_models.database import EventType\nimport modelsx\n")
    members = {"EventType": {"STATE_CHANGE"}}
    qualified = "import models.database\nx = models.database.EventType.GONE\n"
    assert unknown_members(qualified, members) == [(2, "EventType.GONE")]


def test_a_planted_missing_member_is_caught():
    members = {"EventType": {"STATE_CHANGE"}}
    assert unknown_members("x = EventType.STATUS_CHANGED\n", members) == [(1, "EventType.STATUS_CHANGED")]
    assert unknown_members("x = EventType.STATE_CHANGE\n", members) == []
