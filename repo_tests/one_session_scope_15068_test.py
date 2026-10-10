# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One user-management transaction scope (#15068).

Owner decision 2026-10-09: of the user-management modules shared by both services, only
`db_session_context` is consolidated. Its body -- seed the post-commit callbacks, commit,
run them, roll back on error -- was written four times across the two services'
`user_management/database.py`. It now lives once in
`autobot_shared/db_session.py`.

The marker is the SEEDING of the post-commit list: assigning to
`session.info["_post_commit_cbs"]`. Only a transaction scope does that. A reader such as
`UserService`, which appends a callback to the list, does not seed it and is not a copy.
The detector reads the syntax tree, so prose naming the key is not a definition.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot_shared/db_session.py"
_KEY = "_post_commit_cbs"
_KEY_CONSTANT = "POST_COMMIT_CALLBACKS"

#: Both services' modules must route their session helpers through the shared scope.
_CONSUMERS = ("autobot-backend/user_management/database.py", "autobot-slm-backend/user_management/database.py")


def _is_key(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return node.value == _KEY
    return isinstance(node, ast.Name) and node.id == _KEY_CONSTANT


def _seeds_post_commit_list(source: str) -> bool:
    """True when `source` assigns to `<x>.info[<the post-commit key>]`."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for tgt in targets:
            if isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Attribute) and tgt.value.attr == "info":
                if _is_key(tgt.slice):
                    return True
    return False


def _is_source_python(rel: str) -> bool:
    """A non-test Python file: the only kind that can be a second transaction scope."""
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("autobot-backend/user_management/database.py", True),
        ("autobot-backend/user_management/database_test.py", False),
        ("autobot-backend/tests/test_database.py", False),
        ("autobot-slm-backend/tests/conftest.py", False),
        ("autobot-backend/user_management/test_database.py", False),
        ("autobot-backend/user_management/schema.sql", False),
    ],
)
def test_the_test_path_filter_skips_tests_and_keeps_source(rel: str, expected: bool) -> None:
    assert _is_source_python(rel) is expected


def _source_population(root: Path) -> list[str]:
    """Non-test Python source in both backends and autobot_shared: the scan's whole input.

    `tracked_paths` refuses an empty enumeration; that refusal is relocated to REACH's
    floor (see `declare`), which needs an empty result rather than an exception.
    """
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "post-commit-seed-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=2846,
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _seeders() -> tuple[tuple[str, ...], int]:
    """Non-test Python files that seed the post-commit list, and how many were parsed."""
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = _read(rel)
        if _KEY not in source and _KEY_CONSTANT not in source:
            continue
        parsed += 1
        if _seeds_post_commit_list(source):
            found.append(rel)
    return tuple(found), parsed


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a literal seed", 'session.info["_post_commit_cbs"] = []\n', True),
        ("a constant seed", "session.info[POST_COMMIT_CALLBACKS] = []\n", True),
        ("a reader appending", 'cbs = session.info.get("_post_commit_cbs")\ncbs.append(f)\n', False),
        ("a comment naming it", '# session.info["_post_commit_cbs"] = []\nx = 1\n', False),
    ],
)
def test_the_matcher_tells_a_seed_from_a_use(label: str, source: str, expected: bool) -> None:
    assert _seeds_post_commit_list(source) is expected, label


def test_the_scan_is_not_vacuous() -> None:
    """The canonical seeder and UserService's reader both mention the key; fewer is a blind scan."""
    _, parsed = _seeders()
    assert parsed >= 2, f"parsed {parsed} files mentioning the post-commit key"


def test_one_transaction_scope_seeds_the_post_commit_list() -> None:
    seeders, _ = _seeders()
    assert seeders == (_CANONICAL,), (
        f"#15068: {list(seeders)} seed session.info['{_KEY}']; the transaction scope lives once in "
        f"{_CANONICAL}. Call `async_session_scope(<your session maker>)` instead of copying its body."
    )


#: Every provider that opens a session, per service. Checking the file for ANY call would let
#: one provider keep a hand-rolled body while another satisfies the check.
_PROVIDERS = {
    "autobot-backend/user_management/database.py": ("get_async_session", "db_session_context"),
    "autobot-slm-backend/user_management/database.py": ("get_slm_session", "get_autobot_session"),
}


def _providers_not_using_the_scope(source: str, names: tuple[str, ...]) -> list[str]:
    """Names of `names` that are missing or do not call `async_session_scope`."""
    funcs = {n.name: n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.AsyncFunctionDef)}
    bad = []
    for name in names:
        fn = funcs.get(name)
        calls = fn is not None and any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "async_session_scope"
            for n in ast.walk(fn)
        )
        if not calls:
            bad.append(name)
    return bad


def test_the_provider_check_names_the_one_that_does_not_use_the_scope() -> None:
    good = "async def a():\n    async with async_session_scope(m()) as s:\n        yield s\n"
    bad = "async def b():\n    async with m() as s:\n        yield s\n"
    assert _providers_not_using_the_scope(good + good.replace("def a", "def c"), ("a", "c")) == []
    assert _providers_not_using_the_scope(good + bad, ("a", "b")) == ["b"]
    assert _providers_not_using_the_scope(good, ("a", "gone")) == ["gone"]


@pytest.mark.parametrize("rel", _CONSUMERS)
def test_each_service_uses_the_shared_scope(rel: str) -> None:
    bad = _providers_not_using_the_scope(_read(rel), _PROVIDERS[rel])
    assert not bad, f"#15068: {rel}: {bad} no longer open their sessions through async_session_scope"
