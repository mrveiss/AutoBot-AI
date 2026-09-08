# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A status transition's comment reaches the store rather than the floor (#16017).

`StatusUpdate.comment` was declared and read nowhere. An agent explaining a
transition got a `200` and the explanation was discarded on every call, and the
caller could not tell a `200` that stored the comment from one that dropped it.

It was **wired, not removed** — the opposite call from #16018, where four fields
on the same router were deleted. The difference is where the system of record
sits: those fields each had one elsewhere (`/cost-events` charges the budget;
duration is derivable from `started_at`/`finished_at`), so a second durable copy
was the wrong answer. This one had a store already built and unreached —
`LLCWorkItemComment` and `add_comment`, which `post_comment` on this same router
writes to.

These assertions read the SOURCE rather than exercising the route, because the
route needs a database session, an agent context and a work item. What is being
pinned is that the field reaches the service at all, which is exactly what was
missing and is visible statically.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_MODULE = repo_root() / "autobot-backend" / "llc" / "api" / "agent_api.py"


def _function(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {_MODULE}")


def test_the_transition_handler_reads_the_comment_field():
    """The regression: `body.comment` appeared nowhere in the module."""
    source = ast.unparse(_function("update_work_item_status"))
    assert "body.comment" in source, (
        "update_work_item_status does not read StatusUpdate.comment — an agent's "
        "explanation is accepted, answered 200, and discarded (#16017)"
    )


def test_the_comment_is_passed_to_add_comment():
    """Reading the field is not storing it. A handler that logged `body.comment`
    would satisfy the test above while dropping it exactly as before."""
    source = ast.unparse(_function("update_work_item_status"))
    assert "add_comment" in source, "the comment is read but never handed to the store"


def test_the_comment_is_stored_before_the_commit():
    """Ordering, not merely presence.

    A comment committed separately from the transition can outlive a transition
    that failed — a recorded reason for something that did not happen, which is
    worse than no reason. Both must ride one commit.
    """
    source = ast.unparse(_function("update_work_item_status"))
    assert source.index("add_comment") < source.rindex("session.commit"), (
        "the comment is stored after the commit, so a failed transition can still "
        "leave its explanation behind (#16017)"
    )


def test_the_response_distinguishes_stored_from_absent():
    """A caller could not tell a 200 that stored the comment from one that dropped it.

    That indistinguishability is the defect's shape, not an incidental detail:
    the handler's own docstring records that this route once echoed the requested
    status back without performing the transition.
    """
    source = ast.unparse(_function("update_work_item_status"))
    assert "comment_id" in source, (
        "the response carries no marker for whether a comment was stored (#16017)"
    )
