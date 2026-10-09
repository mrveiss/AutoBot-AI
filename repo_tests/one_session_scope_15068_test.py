# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One user-management transaction scope (#15068).

Owner decision 2026-10-09: of the user-management modules shared by both services, only
`db_session_context` is consolidated. Its body -- seed the post-commit callbacks, commit,
run them, roll back on error -- was written four times across the two services'
`user_management/database.py`. It now lives once in
`autobot_shared/user_management/session_scope.py`.

The marker is the SEEDING of the post-commit list: assigning to
`session.info["_post_commit_cbs"]`. Only a transaction scope does that. A reader such as
`UserService`, which appends a callback to the list, does not seed it and is not a copy.
The detector reads the syntax tree, so prose naming the key is not a definition.
"""

from __future__ import annotations

import ast
import functools

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_CANONICAL = "autobot_shared/user_management/session_scope.py"
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


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _seeders() -> tuple[tuple[str, ...], int]:
    """Non-test Python files that seed the post-commit list, and how many were parsed."""
    found: list[str] = []
    parsed = 0
    for rel in tracked_paths(repo_root(), "autobot-backend", "autobot-slm-backend", "autobot_shared"):
        name = rel.rsplit("/", 1)[-1]
        if not rel.endswith(".py") or name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel:
            continue
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
        f"{_CANONICAL}. Call `session_scope(<your session maker>)` instead of copying its body."
    )


@pytest.mark.parametrize("rel", _CONSUMERS)
def test_each_service_uses_the_shared_scope(rel: str) -> None:
    tree = ast.parse(_read(rel))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "session_scope"
    ]
    assert calls, f"#15068: {rel} no longer opens its sessions through session_scope"
