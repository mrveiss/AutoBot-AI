# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every hand-maintained list of "all governed MCP bridges" agrees with disk (#14631).

WHAT WENT WRONG THAT THIS PREVENTS
-----------------------------------
Registering ``manual_mcp`` as the twelfth bridge (#14586) meant editing three
separately hand-maintained lists of "every governed bridge", and a fourth caught
the omission only by accident -- ``test_discover_bridges_known_names`` happened
to assert ``==`` against a literal set rather than a subset, so a shard failure,
not a design decision, is what surfaced it.

THE FILESYSTEM SCAN IS THE SSOT
--------------------------------
``autobot_shared.auth.mcp_bridge_scan.bridge_files()`` is the only one of the
four that cannot silently disagree with reality: it reads the files on disk
rather than a name someone remembered to type into a second place. So it is
imported here rather than re-derived -- re-globbing the directory inside this
test would make it a fifth copy of exactly what it is checking.

The two lists that carry metadata the glob cannot supply are compared on
MEMBERSHIP only. ``_BRIDGE_MODULE_REGISTRY`` legitimately owns endpoint URLs and
feature tags, and ``PER_BRIDGE_DISCOVERY_FLOOR`` legitimately owns per-bridge
tool counts; neither may own a different idea of which bridges exist.

They are read by AST rather than imported: ``api/mcp_registry.py`` pulls the
backend's dependency graph and ``tools/lint/...`` manipulates ``sys.path`` at
import time, and neither is needed to read a literal.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Set

import pytest
from repo_tests._paths import repo_root

from autobot_shared.auth.mcp_bridge_scan import bridge_files, bridge_name

REPO_ROOT = repo_root()

_REGISTRY_SRC = REPO_ROOT / "autobot-backend" / "api" / "mcp_registry.py"
_LINT_SRC = REPO_ROOT / "tools" / "lint" / "check_mcp_tool_permission_coverage.py"


def _module(path: Path) -> ast.Module:
    """Parse *path*, failing loudly rather than reporting an empty list."""
    assert path.is_file(), f"{path.relative_to(REPO_ROOT)} is missing — this guard cannot run"
    return ast.parse(path.read_text(encoding="utf-8"))


def _assigned(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        target = (
            node.targets[0]
            if isinstance(node, ast.Assign)
            else node.target if isinstance(node, ast.AnnAssign) else None
        )
        if isinstance(target, ast.Name) and target.id == name and node.value is not None:
            return node.value
    raise AssertionError(f"{name} not found at module level — it was renamed or moved, so this guard is blind")


def registry_bridge_names() -> Set[str]:
    """Second element of each ``_BRIDGE_MODULE_REGISTRY`` tuple."""
    value = _assigned(_module(_REGISTRY_SRC), "_BRIDGE_MODULE_REGISTRY")
    assert isinstance(value, (ast.List, ast.Tuple)), "_BRIDGE_MODULE_REGISTRY is no longer a literal sequence"
    names: Set[str] = set()
    for entry in value.elts:
        assert (
            isinstance(entry, ast.Tuple) and len(entry.elts) >= 2
        ), "registry entry is not a (module, name, ...) tuple"
        name_node = entry.elts[1]
        assert isinstance(name_node, ast.Constant) and isinstance(name_node.value, str)
        names.add(name_node.value)
    return names


def floor_bridge_names() -> Set[str]:
    """Keys of ``PER_BRIDGE_DISCOVERY_FLOOR``."""
    value = _assigned(_module(_LINT_SRC), "PER_BRIDGE_DISCOVERY_FLOOR")
    assert isinstance(value, ast.Dict), "PER_BRIDGE_DISCOVERY_FLOOR is no longer a dict literal"
    names: Set[str] = set()
    for key in value.keys:
        assert isinstance(key, ast.Constant) and isinstance(key.value, str)
        names.add(key.value)
    return names


def on_disk() -> Set[str]:
    return {bridge_name(path) for path in bridge_files()}


def membership_gaps(listed: Set[str], real: Set[str]) -> tuple[list[str], list[str]]:
    """(on disk but unlisted, listed but not on disk).

    Split out so the rule can be exercised on synthetic inputs below rather than
    only against whatever the tree happens to contain today.
    """
    return sorted(real - listed), sorted(listed - real)


def test_the_scan_found_bridges() -> None:
    """Runs first: an empty scan makes every comparison below vacuously true."""
    found = on_disk()
    assert len(found) >= 10, (
        f"the bridge scan found only {len(found)} bridge(s): {sorted(found)}. "
        "FIX THE SWEEP — a comparison against an empty set passes for any list."
    )


@pytest.mark.parametrize(
    "label,reader",
    [
        ("_BRIDGE_MODULE_REGISTRY (api/mcp_registry.py)", registry_bridge_names),
        ("PER_BRIDGE_DISCOVERY_FLOOR (tools/lint/check_mcp_tool_permission_coverage.py)", floor_bridge_names),
    ],
)
def test_hand_maintained_list_matches_disk(label: str, reader) -> None:
    listed, real = reader(), on_disk()
    missing, orphaned = membership_gaps(listed, real)
    assert not missing and not orphaned, (
        f"{label} disagrees with the bridge scan.\n"
        f"  on disk but not listed: {missing or 'none'}\n"
        f"  listed but not on disk: {orphaned or 'none'}\n\n"
        "A bridge missing from a governance list is ungoverned while looking covered — that is "
        "how manual_mcp landed (#14586). A stranded entry names a bridge that was renamed, "
        "removed, or added to EXCLUDED_BRIDGE_STEMS; drop it with the bridge."
    )


def test_the_two_lists_agree_with_each_other() -> None:
    """Transitively implied, asserted directly so a failure names the real pair."""
    assert registry_bridge_names() == floor_bridge_names()


@pytest.mark.parametrize(
    "label,listed,real,expect_missing,expect_orphaned",
    [
        ("lists agree", {"a_mcp", "b_mcp"}, {"a_mcp", "b_mcp"}, [], []),
        # The #14586 shape: a new bridge on disk that nobody added to the list.
        ("bridge added, list not updated", {"a_mcp"}, {"a_mcp", "b_mcp"}, ["b_mcp"], []),
        # A subset assertion would PASS this one, which is why the rule is ==.
        ("list is a strict subset of disk", {"a_mcp"}, {"a_mcp", "b_mcp", "c_mcp"}, ["b_mcp", "c_mcp"], []),
        ("floor stranded by a rename", {"a_mcp", "old_mcp"}, {"a_mcp"}, [], ["old_mcp"]),
        ("both directions at once", {"a_mcp", "old_mcp"}, {"a_mcp", "new_mcp"}, ["new_mcp"], ["old_mcp"]),
    ],
)
def test_the_rule_is_exact_in_both_directions(
    label: str, listed: Set[str], real: Set[str], expect_missing: list[str], expect_orphaned: list[str]
) -> None:
    """#14586's omission survived a list that CONTAINED the right names.

    A subset check passes case 3 below. Only an exact comparison fails it, so the
    rule is pinned here on synthetic inputs where both directions are visible.
    """
    missing, orphaned = membership_gaps(listed, real)
    assert (missing, orphaned) == (expect_missing, expect_orphaned), label
