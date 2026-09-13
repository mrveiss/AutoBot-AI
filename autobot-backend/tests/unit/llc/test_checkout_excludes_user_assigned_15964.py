# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent must not claim a work item assigned to a user (#15964, CWE-863).

`checkout_next`'s eligibility predicate originally tested only
`assignee_agent_id IS NULL` for "unassigned". An item assigned to a *user* has
that column null, so it matched, and `checkout` then wrote
`assignee_type = agent` over it while leaving `assignee_user_id` populated —
a row naming both an agent and a user, its type agreeing with one of them.

These assertions read the predicate's expression TREE rather than the compiled
SQL string. A string test passes on `... IS NULL` appearing anywhere in the
statement, including inside the unrelated `checkout_run_id` filter; the shape
is what carries the rule.

The behavioural path needs a real Postgres (postgresql.UUID/JSONB do not
compile on SQLite) and would skip everywhere else. A security regression test
that skips reports clean while proving nothing, so the rule is pinned here,
unconditionally, and the writer half is pinned by AST below.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

from sqlalchemy import or_

from llc.models.work_item import LLCWorkItem
from llc.services.work_item_queue import claimable_by

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _columns_compared_to_null(clause) -> set[str]:
    """Names of columns this clause tree tests with `IS NULL`."""
    found: set[str] = set()
    stack = [clause]
    while stack:
        node = stack.pop()
        clauses = getattr(node, "clauses", None)
        if clauses is not None:
            stack.extend(clauses)
            continue
        if getattr(node, "operator", None) is not None or hasattr(node, "left"):
            left, right = getattr(node, "left", None), getattr(node, "right", None)
            if left is not None and right is not None:
                is_null = right.__class__.__name__ == "Null" or getattr(right, "value", ...) is None
                if is_null and hasattr(left, "key"):
                    found.add(left.key)
    return found


def test_unassigned_branch_requires_both_assignee_columns_null() -> None:
    """The "unassigned" branch must test the user column as well as the agent one."""
    predicate = claimable_by(uuid.uuid4())

    branches = list(predicate.clauses)
    assert len(branches) == 2, f"expected an OR of 2 branches, got {len(branches)}"

    unassigned = next(
        (b for b in branches if _columns_compared_to_null(b)),
        None,
    )
    assert unassigned is not None, "no branch tests any column for NULL"

    null_tested = _columns_compared_to_null(unassigned)
    assert null_tested == {"assignee_agent_id", "assignee_user_id"}, (
        "The unassigned branch of the checkout predicate must require BOTH "
        f"assignee columns to be NULL; it tests {sorted(null_tested)}. Testing "
        "only assignee_agent_id lets an agent claim a user-assigned item "
        "(#15964, CWE-863)."
    )


def test_the_rule_rejects_the_predicate_this_issue_was_filed_about() -> None:
    """Contrast pair: the OLD, agent-only predicate must NOT satisfy the rule.

    Without this, the assertion above is indistinguishable from one that
    reports "both columns" for any shape it is handed — the test would pass on
    the vulnerable predicate just as happily as on the fixed one.
    """
    vulnerable = or_(
        LLCWorkItem.assignee_agent_id.is_(None),  # the pre-#15964 predicate
        LLCWorkItem.assignee_agent_id == uuid.uuid4(),
    )

    branches = list(vulnerable.clauses)
    unassigned = next(b for b in branches if _columns_compared_to_null(b))
    null_tested = _columns_compared_to_null(unassigned)

    assert null_tested == {"assignee_agent_id"}, (
        "The reader must see the old predicate as testing ONLY the agent "
        f"column; it reported {sorted(null_tested)}. If it cannot tell the two "
        "predicates apart, the test above proves nothing about the fixed one."
    )


def test_checkout_clears_the_user_assignee_when_an_agent_claims() -> None:
    """`checkout` must not leave `assignee_user_id` set on an agent-claimed row.

    Read from the source: the write sits inside an async method that needs a
    session and a live row. What matters for the invariant is that the
    assignment exists at all, next to the `assignee_agent_id` write.
    """
    source = (BACKEND_ROOT / "llc" / "services" / "work_item_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    checkout = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "checkout"),
        None,
    )
    assert checkout is not None, "checkout() not found — this test's anchor moved"

    cleared = any(
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and node.value.value is None
        and any(isinstance(t, ast.Attribute) and t.attr == "assignee_user_id" for t in node.targets)
        for node in ast.walk(checkout)
    )
    assert cleared, (
        "checkout() sets assignee_agent_id and assignee_type = agent but never "
        "clears assignee_user_id, so an agent-claimed row keeps naming a user "
        "assignee too (#15964)."
    )
