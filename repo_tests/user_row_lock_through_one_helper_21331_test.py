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
"""

from __future__ import annotations

import ast
import re

from repo_tests._infra_backend_names import tracked_py
from repo_tests._paths import repo_root

ROOT = repo_root()
TREES = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
USER_MODEL = re.compile(r"\b(User|user_model|user|users)\b")

#: The one set-lock helper.
HELPER = "autobot_shared/user_management/last_platform_admin.py"
#: Single-row locks of the user model: file -> number of sites.
SINGLE_ROW = {
    "autobot-backend/user_management/services/session_successor.py": 2,
    "autobot_shared/user_management/user_service_lifecycle.py": 1,
}


def user_row_locks(source: str) -> int:
    """How many ``with_for_update`` uses in *source* sit in a statement that names the user model."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    found = 0
    for node in ast.walk(tree):
        if not (
            (isinstance(node, ast.Attribute) and node.attr == "with_for_update")
            or (isinstance(node, ast.keyword) and node.arg == "with_for_update")
        ):
            continue
        stmt = node
        while not isinstance(stmt, ast.stmt):
            stmt = parents[stmt]
        found += bool(USER_MODEL.search(ast.get_source_segment(source, stmt) or ""))
    return found


def _census() -> dict[str, int]:
    census = {}
    for rel in tracked_py(ROOT, *TREES):
        if "test" in rel.lower():
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
