# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No two tracked scripts share one filename (#14873, #15580).

Scope is the whole `scripts/` tree, which includes the two roots #15580 names (`scripts/` and
`scripts/utilities/`), for every script suffix, not only `.py`.

`shared/scripts` is a flat sys.path root: its tests load siblings by bare name, so two files
called `optimize_agents.py` bound one `sys.modules` slot and the loser's tests ran against the
other tool. They were the same concept (optimise `.claude/agents/*.md`), so #14873 merged the
older class-based copy into the newer atomic/dry-run one. This guard keeps the import name
unique, and pins the survivor's path so a second `optimize_agents` cannot return.
"""

from __future__ import annotations

import collections
from pathlib import PurePosixPath

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = "autobot-infrastructure/shared/scripts"

#: Basenames that are legitimately repeated (package markers, pytest plumbing).
_EXEMPT_NAMES = frozenset({"__init__.py", "conftest.py"})

#: Script suffixes whose basename is the name an operator types or a test imports.
_SCRIPT_SUFFIXES = (".py", ".sh", ".bash", ".js")

#: Known forks not yet resolved. May only shrink; empty means every script name is unique.
_GRANDFATHERED: dict[str, tuple[str, ...]] = {}


def _script_files(root) -> list[str]:
    try:
        return [p for p in tracked_paths(root, _ROOT) if p.endswith(_SCRIPT_SUFFIXES)]
    except EmptyEnumeration:
        return []


REACH = declare(
    "script-module-name-scan",
    discover=_script_files,
    # Mid-window, from REACH.window().
    floor=285,
    what="tracked scripts (py, sh, bash, js)",
    roots=(_ROOT,),
    growth=100,
)


def shared_names(paths: list[str]) -> dict[str, tuple[str, ...]]:
    """Basename -> the paths sharing it, for every basename held by more than one file."""
    by_name: dict[str, list[str]] = collections.defaultdict(list)
    for rel in paths:
        name = PurePosixPath(rel).name
        if name not in _EXEMPT_NAMES:
            by_name[name].append(rel)
    return {n: tuple(sorted(v)) for n, v in by_name.items() if len(v) > 1}


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["a/optimize_agents.py", "a/utilities/optimize_agents.py"], {"optimize_agents.py"}),
        (["a/optimize_agents_test.py", "a/utilities/optimize_agents_test.py"], {"optimize_agents_test.py"}),
        (["a/optimize_agents.py", "a/utilities/other_tool.py"], set()),
        (["a/sync.sh", "a/utilities/sync.sh"], {"sync.sh"}),
        (["a/__init__.py", "a/b/__init__.py", "a/conftest.py", "a/b/conftest.py"], set()),
    ],
)
def test_the_matcher_tells_a_shared_name_from_distinct_ones(paths: list[str], expected: set[str]) -> None:
    assert set(shared_names(paths)) == expected


def test_no_two_scripts_share_an_import_name() -> None:
    found = shared_names(list(REACH.examined(repo_root())))
    new = {n: v for n, v in found.items() if _GRANDFATHERED.get(n) != v}
    assert not new, (
        f"#14873: {new} share an import name; the second one to import it shadows the first. "
        "Different tools: rename one. Same concept: merge onto one module."
    )
    stale = [n for n in _GRANDFATHERED if n not in found]
    assert not stale, f"{stale} are no longer forked: drop them from _GRANDFATHERED"


_OPTIMIZE_AGENTS = f"{_ROOT}/optimize_agents.py"


def test_the_matcher_finds_a_second_optimize_agents() -> None:
    """Contrast pair: a module at another path is the fork; the survivor alone is not."""
    assert _stray_optimize_agents([_OPTIMIZE_AGENTS, f"{_ROOT}/utilities/optimize_agents.py"]) == [
        f"{_ROOT}/utilities/optimize_agents.py"
    ]
    assert _stray_optimize_agents([_OPTIMIZE_AGENTS, f"{_ROOT}/utilities/agent-optimize.sh"]) == []


def _stray_optimize_agents(paths: list[str]) -> list[str]:
    return [p for p in paths if PurePosixPath(p).stem == "optimize_agents" and p != _OPTIMIZE_AGENTS]


def test_optimize_agents_is_one_module_at_the_surviving_path() -> None:
    """#14873: the newer atomic/dry-run copy is the only `optimize_agents` (+ its one test)."""
    paths = list(REACH.examined(repo_root()))
    assert _OPTIMIZE_AGENTS in paths, f"#14873: the surviving module {_OPTIMIZE_AGENTS} is missing"
    stray = _stray_optimize_agents(paths)
    assert not stray, f"#14873: {stray} is a second optimize_agents module; extend {_OPTIMIZE_AGENTS} instead"
