# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An A2A task claims scopes as ITS peer, not as one shared executor (#16950).

The ingress gate identifies the peer correctly (`api/a2a.py`
`require_capability(x_a2a_agent_id, ...)`, anonymous callers hard-denied), and
then the identity was dropped one layer in: every admitted peer's task claimed
its scopes as the literal `"a2a-executor"`.

**What that cost is attribution, not a scope bypass** — recorded here because
the obvious guess is wrong and I made it first. `work_claims`' Lua treats a
holder as the same only when `agent_id` AND `task_id` both match
(`same_holder = held.agent_id == agent and held.task_id == task`), so two peers'
tasks always conflicted: their task ids differ. One peer could never act on
another's hold at this layer.

What the shared identity destroyed is WHO. A refusal named `a2a-executor`
instead of the peer actually holding the scope, so an operator cannot tell which
peer to talk to and cannot tell contention from a misbehaving peer; and any
policy keyed on `agent_id` — rate, budget, audit — saw every peer as one. That
is #16950's FIRST criterion (identity end to end), not its fourth.

This distinction is load-bearing for the test below: the refusal itself does not
tell a fixed tree from a broken one, because both refuse. The assertion that
does is the one naming the holder.

`chat_workflow/delegation_laundering_test.py` already covers the parent/child
subagent path. It does not touch A2A: before this change, `"a2a-executor"`
appeared in exactly one file in the tree and no test asserted anything about it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from a2a.peer_identity import CLAIM_PREFIX, claim_identity


@pytest_asyncio.fixture
async def claim_registry(monkeypatch):
    """A real work-claim registry over an in-process Redis, so a hold really conflicts."""
    fakeredis_async = pytest.importorskip("fakeredis.aioredis")
    from autobot_shared.coordination import work_claims

    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)
    monkeypatch.setattr(work_claims, "get_async_redis_client", AsyncMock(return_value=client))
    yield client
    await client.flushall()


# ---------------------------------------------------------------------------
# The identity itself
# ---------------------------------------------------------------------------


def test_two_peers_get_two_identities() -> None:
    """The whole defect in one assertion: these used to be the same string."""
    assert claim_identity("peer-a", "task-1") != claim_identity("peer-b", "task-1")


def test_one_peer_keeps_one_identity_across_tasks() -> None:
    """The other half. A per-task identity would make a peer unable to conflict
    with ITSELF, which is a different bug in the same place."""
    assert claim_identity("peer-a", "task-1") == claim_identity("peer-a", "task-2")


def test_an_unidentified_caller_aliases_nobody() -> None:
    """No peer id must not mean one shared name.

    Anonymous callers are refused at ingress, so this is defence in depth — but
    a fallback constant would rebuild exactly the aliasing this fix removes, so
    an unidentified caller is unique to its own task instead.
    """
    assert claim_identity(None, "task-1") != claim_identity(None, "task-2")
    assert claim_identity(None, "task-1") != claim_identity("peer-a", "task-1")


@pytest.mark.parametrize(
    ("left", "right"),
    [("a/b", "a%2Fb"), ("a:b", "a%3Ab"), ("x", "x ")],
    ids=["slash", "colon", "trailing-space"],
)
def test_two_different_peer_ids_cannot_collide(left: str, right: str) -> None:
    """Percent-encoded for the same reason as `peer_trust_key`: a separator
    inside an id must not let two peers produce one key."""
    assert claim_identity(left, "t") != claim_identity(right, "t")


def test_the_identity_is_namespaced_away_from_internal_agents() -> None:
    """A peer must not be able to present an id that claims as an internal agent."""
    assert claim_identity("orchestrator", "t").startswith(f"{CLAIM_PREFIX}:")


# ---------------------------------------------------------------------------
# The behaviour, against a real registry
# ---------------------------------------------------------------------------


def _task_manager_mock():
    tm = MagicMock()
    tm.get_task.return_value = MagicMock(status=MagicMock(state="working"))
    return tm


@pytest.mark.asyncio
async def test_a_refusal_names_the_peer_that_holds_the_scope(claim_registry) -> None:
    """The refusal must say WHO, which the shared identity made impossible.

    Peer B is refused either way — `same_holder` needs the task ids to match too,
    so the flattening never let B act on A's hold. The assertion that separates a
    fixed tree from a broken one is the second: before this change the artifact
    named `a2a-executor`, and an operator reading it could not tell which peer to
    talk to, nor ordinary contention from one peer wedging every other.
    """
    from a2a.task_executor import execute_a2a_task
    from agents.scope_enforcement import hold_scopes

    scope = "path:shared/thing"
    tm = _task_manager_mock()

    async with hold_scopes(
        [scope], agent_id=claim_identity("peer-a", "task-a"), task_id="task-a", intent="a holds it"
    ) as held_by_a:
        assert held_by_a.granted, "premise: peer A must actually hold the scope"

        with (
            patch("a2a.task_executor.get_task_manager", return_value=tm),
            patch("a2a.task_executor.get_trust_manager", return_value=MagicMock()),
        ):
            await execute_a2a_task(
                "task-b", "do the same thing", context={"declared_scopes": [scope]}, peer_id="peer-b"
            )

    # `_report_refusal` records exactly "scope_conflict" and puts the holder in an
    # artifact; asserting the literal keeps this bound to the real refusal path
    # rather than to any message containing the word "refused".
    messages = [c.kwargs.get("message") for c in tm.update_state.call_args_list]
    assert "scope_conflict" in messages, (
        "peer B's task was not refused while peer A held the scope — the two peers are still "
        f"one claimant. States recorded: {messages}"
    )
    assert any("peer-a" in str(c) for c in tm.add_artifact.call_args_list), (
        "the refusal must name WHICH peer holds it; a bare conflict leaves the operator unable "
        "to tell laundering from ordinary contention"
    )


@pytest.mark.asyncio
async def test_the_same_peer_is_not_refused_by_its_own_hold(claim_registry) -> None:
    """The positive control, and the one that makes the test above mean something.

    "B is refused" is satisfied by a change that refuses everyone. A peer
    re-entering its own scope must still be granted.
    """
    from agents.scope_enforcement import hold_scopes

    scope = "path:its/own/thing"
    identity = claim_identity("peer-a", "task-a")

    async with hold_scopes([scope], agent_id=identity, task_id="task-a", intent="first") as first:
        assert first.granted
        async with hold_scopes([scope], agent_id=identity, task_id="task-a", intent="again") as again:
            assert again.granted, "a peer must not be refused by its own existing hold"
