# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One declaration of what a tool does to the world (#18294).

``autobot_shared/tool_catalogue.py`` owns the per-tool effect facts (``TOOL_EFFECTS``). Four
sites used to keep their own tool-name literal for effect and disagreed (``create_directory``
write vs state, ``remove_directory`` vs ``delete_directory``, seven tools classified by one
site only). This guard fails when a module outside the catalogue assigns a literal
name -> effect table: a set/list/tuple/frozenset of tool names, or a dict keyed by tool names,
where at least three entries are catalogued tools and they are at least half the literal.

Sites that predate the guard are frozen in ``_GRANDFATHERED`` (count per file). The map may
only shrink: a new table anywhere fails, and a grandfathered file that stopped having one must
be removed from the map. Dicts whose values are callables (resource extractors, handler
tables) are dispatch, not classification, and are not counted.
"""

from __future__ import annotations

import ast
import functools
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CATALOGUE = "autobot_shared/tool_catalogue.py"
_MIN_HITS = 3
_WRAPPERS = {"frozenset", "set", "tuple", "list"}

#: Pre-#18294 effect tables awaiting derivation. EMPTY since #18294: the seven that existed now
#: derive from the catalogue. A new entry here is a regression of the fork, not a deferral.
_GRANDFATHERED: dict[str, int] = {}

#: Tables that name tools but do NOT classify what a tool does to the world, with the reason.
#: ``(count, reason)`` per file; a count above it fails, and an entry that no longer matches fails.
_NOT_AN_EFFECT_TABLE: dict[str, tuple[int, str]] = {
    "autobot-backend/async_chat_workflow.py": (
        1,
        "TERMINAL_KEYWORDS are words matched against the USER's message to classify intent; they are not tool names",
    ),
    "autobot-backend/chat_workflow/tool_handler.py": (
        3,
        "WEB_RESEARCH_TOOL_NAMES and the _handlers map route a tool to its web_fetch handler (dispatch), "
        "which says where a call goes, not what it does; _BUILTIN_TOOL_SCHEMAS maps a tool to its argument "
        "schema (what it accepts, not what it does)",
    ),
}


def _catalogue_names() -> frozenset[str]:
    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from autobot_shared.tool_catalogue import TOOL_ALIASES, TOOL_EFFECTS

    return frozenset(TOOL_EFFECTS) | frozenset(TOOL_ALIASES)


def _literal_strings(node: ast.AST) -> list[str] | None:
    """String entries of a name-table literal (looking through frozenset(...) etc.), else None."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _WRAPPERS and node.args:
        return _literal_strings(node.args[0])
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    if isinstance(node, ast.Dict) and not any(isinstance(v, (ast.Lambda, ast.Call)) for v in node.values):
        return [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    return None


def effect_tables(source: str, names: frozenset[str]) -> list[int]:
    """Line numbers of assigned literals that read as a tool-name classification table."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        strings = _literal_strings(node.value)
        hits = [s for s in strings or [] if s in names]
        if len(hits) >= _MIN_HITS and len(hits) * 2 >= len(strings or []):
            lines.append(node.lineno)
    return lines


_NAMES = frozenset({"read_file", "write_file", "edit_file", "delete_file", "web_search"})


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a frozenset of names", 'W = frozenset({"read_file", "write_file", "edit_file"})\n', 1),
        ("a bare set", 'W = {"read_file", "write_file", "edit_file"}\n', 1),
        ("a name->class dict", 'W = {"read_file": "r", "write_file": "w", "edit_file": "w"}\n', 1),
        ("an annotated tuple", 'W: tuple = ("read_file", "write_file", "delete_file")\n', 1),
        ("two names only", 'W = {"read_file", "write_file"}\n', 0),
        ("mostly other strings", 'W = {"a", "b", "c", "d", "read_file", "write_file", "edit_file"}\n', 0),
        ("a dispatch dict of callables", 'W = {"read_file": f, "write_file": lambda: 1, "edit_file": g()}\n', 0),
        ("a non-assigned literal", 'f(["read_file", "write_file", "edit_file"])\n', 0),
    ],
)
def test_the_detector_tells_an_effect_table_from_other_literals(label: str, source: str, expected: int) -> None:
    assert len(effect_tables(source, _NAMES)) == expected, label


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "tool-effect-table-scan",
    discover=_population,
    floor=2929,
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _tables_by_file() -> dict[str, int]:
    names = _catalogue_names()
    found: dict[str, int] = {}
    for rel in REACH.examined(repo_root()):
        if rel == _CATALOGUE:
            continue
        count = len(effect_tables((repo_root() / rel).read_text(encoding="utf-8"), names))
        if count:
            found[rel] = count
    return found


def _allowed(rel: str) -> int:
    return _GRANDFATHERED.get(rel, 0) + _NOT_AN_EFFECT_TABLE.get(rel, (0, ""))[0]


def test_no_module_outside_the_catalogue_grows_a_tool_effect_table() -> None:
    new = {f: n for f, n in _tables_by_file().items() if n > _allowed(f)}
    assert not new, (
        f"#18294: {new} define a tool-name classification table. Declare the tool's effect in "
        f"{_CATALOGUE} (TOOL_EFFECTS) and derive the set with tools_with()/has_effect()."
    )


def test_nothing_is_grandfathered() -> None:
    assert _GRANDFATHERED == {}, "#18294: derive the table from the catalogue instead of grandfathering it"


def test_every_exemption_still_matches_a_table_and_states_a_reason() -> None:
    found = _tables_by_file()
    stale = {f: n for f, (n, _) in _NOT_AN_EFFECT_TABLE.items() if found.get(f, 0) != n}
    assert not stale, f"#18294: exemptions that no longer match what the scan finds: {stale}"
    assert all(reason.strip() for _, reason in _NOT_AN_EFFECT_TABLE.values())


def test_the_scan_reaches_the_four_sites_this_issue_unified() -> None:
    reached = set(REACH.examined(repo_root()))
    for rel in (
        "autobot-backend/chat_workflow/code_exec/tool_policy.py",
        "autobot-backend/tools/parallel/analyzer.py",
        "autobot_shared/repetition_guard.py",
        _CATALOGUE,
    ):
        assert rel in reached, f"{rel} is outside the scan"
    assert not {r for r in reached if r.endswith("_test.py")}, "tests leaked into the scan"
