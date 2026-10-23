# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The GitHub REST client and its constructor are defined once (#15411).

`GitHubApi` lived inside `ci_dispatch_watchdog.py`, frozen at its #14236 size ceiling, so
the shared client could not gain a method; `ci_red_cause.py` and `release_sync_main.py`
each carried a copy of the `build_api()` that turns the environment into a client. Both
now live in `pipeline-scripts/github_api.py`.

The detector reads the syntax tree: a `class GitHubApi` or `def build_api` statement. An
import, a re-export, or prose naming them is not a definition.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "pipeline-scripts/github_api.py"
_NAMES = frozenset({"GitHubApi", "build_api"})


def _defined_names(source: str) -> set[str]:
    """The guarded names that `source` defines as a class or function."""
    return {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _NAMES
    }


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("the client class", "class GitHubApi:\n    pass\n", {"GitHubApi"}),
        ("a constructor copy", "def build_api():\n    return 1\n", {"build_api"}),
        ("both", "class GitHubApi: ...\ndef build_api(): ...\n", {"GitHubApi", "build_api"}),
        ("an import", "from github_api import GitHubApi, build_api\n", set()),
        ("a call and an annotation", "def f(api: GitHubApi):\n    return build_api()\n", set()),
        ("a comment", "# class GitHubApi:\n# def build_api():\nx = 1\n", set()),
        ("a similarly named function", "def build_api_key(): ...\n", set()),
    ],
)
def test_the_matcher_tells_a_definition_from_a_use(label: str, source: str, expected: set[str]) -> None:
    assert _defined_names(source) == expected, label


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "pipeline-scripts", "scripts")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "github-api-single-module",
    discover=_source_population,
    # Mid-window, from REACH.window().
    floor=60,
    what="non-test python source",
    roots=("pipeline-scripts", "scripts"),
    growth=20,
)


@functools.lru_cache(maxsize=1)
def _definers() -> dict[str, tuple[str, ...]]:
    found: dict[str, list[str]] = {}
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if not any(name in source for name in _NAMES):
            continue
        for name in _defined_names(source):
            found.setdefault(name, []).append(rel)
    return {name: tuple(paths) for name, paths in found.items()}


def test_the_canonical_module_defines_both() -> None:
    assert set(_definers()) == _NAMES, f"nothing defines {sorted(_NAMES - set(_definers()))}: the scan is blind"


@pytest.mark.parametrize("name", sorted(_NAMES))
def test_each_name_is_defined_only_in_the_canonical_module(name: str) -> None:
    assert _definers().get(name) == (_CANONICAL,), (
        f"#15411: {name} is defined in {list(_definers().get(name, ()))}; it lives once in {_CANONICAL}. "
        "Import it instead of copying it."
    )
