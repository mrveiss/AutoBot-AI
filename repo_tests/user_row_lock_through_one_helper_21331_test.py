# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``FOR UPDATE`` over the user model goes through one helper, or is a single-row lock (#21331).

Two code paths that lock the same set of platform-admin rows in different orders can deadlock. The set lock
is ``autobot_shared.user_management.last_platform_admin.lock_platform_admin_rows`` (id-ordered), taken by the
last-admin guard and the four-eyes approval check alike. A new ``with_for_update`` over the user model fails
here unless it is that helper or one of the named single-row locks below (one row cannot deadlock on order
among itself, and each takes its row after the set lock).

Trade-off: the bare name ``user`` also counts as the user model, so a function that merely has a variable called
``user`` and locks another table is flagged and must be named below. That is noisy but safe (a miss would hide a
real lock), and the repo has no such function today.
"""

from __future__ import annotations

import ast
import re

from repo_tests._infra_backend_names import tracked_py
from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache

ROOT = repo_root()
TREES = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
USER_MODEL = frozenset({"User", "user_model", "user"})

#: The one set-lock helper.
HELPER = "autobot_shared/user_management/last_platform_admin.py"
#: Single-row locks of the user model: file -> number of sites.
SINGLE_ROW = {
    "autobot-backend/user_management/services/session_successor.py": 2,
    "autobot_shared/user_management/user_service_lifecycle.py": 1,
    # One row (an owner must exist), taken after ``is_self_approval`` has taken the admin set lock.
    "autobot-backend/services/chat_session_owner_action.py": 1,
}
#: Test files, by name or directory (a bare "test" substring would skip ``latest_*`` and ``attestation*``).
_TEST_PATH = re.compile(r"(_test\.py$|(^|/)test_[^/]*\.py$|(^|/)tests/)")


def _names(scope: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(scope) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(scope) if isinstance(n, ast.Attribute)
    }


def user_row_locks(source: str) -> int:
    """How many ``with_for_update`` uses in *source* sit in a function (or module) that references the user model.

    The whole enclosing function counts, not only the statement: ``query = select(User.id)`` then
    ``query.with_for_update()`` is the split form that a statement-level check misses. Only code names count
    (``ast.Name``), so a message that says "User 7 ..." does not.
    """
    tree = parse_cache.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    found = 0
    for node in ast.walk(tree):
        if not (
            (isinstance(node, ast.Attribute) and node.attr == "with_for_update")
            or (isinstance(node, ast.keyword) and node.arg == "with_for_update")
        ):
            continue
        scope = node
        while not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            scope = parents[scope]
        found += bool(_names(scope) & USER_MODEL)
    return found


def _census() -> dict[str, int]:
    census = {}
    for rel in tracked_py(ROOT, *TREES):
        if _TEST_PATH.search(rel):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "with_for_update" in text and (count := user_row_locks(text)):
            census[rel] = count
    return census


def test_user_row_locks_go_through_the_one_helper_or_are_named_single_row_locks():
    census = _census()
    assert HELPER in census, "the helper is not found: the detector has stopped seeing the lock it guards"
    census.pop(HELPER)
    assert census == SINGLE_ROW, (
        f"a FOR UPDATE over the user model outside the helper: {sorted(set(census) ^ set(SINGLE_ROW))}"
        f" (or a changed count); use lock_platform_admin_rows (#21331)"
    )


def test_control_a_planted_set_lock_outside_the_helper_is_counted():
    planted = "q = select(User.id).filter_by(is_platform_admin=True).with_for_update()\n"
    assert user_row_locks(planted) == 1
    assert user_row_locks("q = select(Approval).with_for_update()\n") == 0


def test_control_the_split_form_is_counted_and_a_message_naming_user_is_not():
    split = "def f(s, lock):\n    q = select(User.id)\n    return s.execute(q.with_for_update() if lock else q)\n"
    assert user_row_locks(split) == 1
    assert user_row_locks("def f():\n    q = select(Item).with_for_update()\n    raise E('User 7 is not here')\n") == 0


def test_the_test_path_filter_skips_tests_but_not_latest_or_attestation():
    assert _TEST_PATH.search("a/b/x_test.py") and _TEST_PATH.search("a/test_x.py") and _TEST_PATH.search("a/tests/x.py")
    assert not _TEST_PATH.search("a/latest_x.py") and not _TEST_PATH.search("a/attestation.py")
