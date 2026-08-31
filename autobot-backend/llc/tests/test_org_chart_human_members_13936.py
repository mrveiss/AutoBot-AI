# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Org chart must show the company's people, not only its hired agents (#13936).

Before this fix, ``OrgChartNode.is_human`` was declared on the response model but
its only construction site hardcoded ``is_human=False``, and
``llc_company_memberships`` was never joined into the tree. The frontend already
rendered a human branch (``OrgTreeNode.vue`` styles ``is_human`` distinctly), so
that branch was unreachable — the org chart was structurally agents-only.

These tests pin BOTH sides, per the "verify against the reproduction, not the
predicate" rule: the case that was broken (a human must appear, flagged human)
AND the case that must stay caught (an agent must never be flagged human).
Reverting the fix must turn the first test red.

Fixtures are reused from ``test_org_chart_enrichment`` rather than copied a third
time — same in-memory SQLite harness, separate engine per test.
"""

from __future__ import annotations

import uuid

import pytest

from llc.models.enums import MembershipRole, WorkItemStatus
from llc.models.membership import LLCCompanyMembership
from llc.tests.test_org_chart_enrichment import (  # noqa: F401 — pytest fixtures
    _seed_org_node,
    _seed_work_item,
    app,
    client,
    engine,
    session_factory,
)
from user_management.models.user import User


async def _seed_human(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    *,
    display_name: str | None = "Ada Lovelace",
    username: str = "ada",
    role: str = MembershipRole.LEAD.value,
) -> uuid.UUID:
    """Seed a ``users`` row plus its company membership. Returns the user id."""
    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"{username}@example.test",
                username=username,
                display_name=display_name,
                is_active=True,
            )
        )
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_id,
                user_id=user_id,
                role=role,
            )
        )
        await session.commit()
    return user_id


def _flatten(nodes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for n in nodes:
        out.append(n)
        out.extend(_flatten(n.get("children") or []))
    return out


@pytest.mark.asyncio
async def test_human_member_appears_in_org_chart_flagged_human(client, session_factory):  # noqa: ANN001
    """The reproduction: a company member must appear, with is_human True.

    This is the assertion that fails against the pre-fix hardcoded
    ``is_human=False`` / never-joined memberships.
    """
    company_id = uuid.uuid4()
    user_id = await _seed_human(session_factory, company_id)

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text

    nodes = _flatten(resp.json()["nodes"])
    humans = [n for n in nodes if n["is_human"]]
    assert len(humans) == 1, f"expected exactly one human node, got {nodes}"

    human = humans[0]
    assert human["name"] == "Ada Lovelace"
    # Namespaced id so a person can never collide with an agent slug…
    assert human["id"] == f"user:{user_id}"
    # …while node_id stays the raw user id — the keyspace assignee_user_id uses.
    assert human["node_id"] == str(user_id)
    assert human["title"] == MembershipRole.LEAD.value
    assert human["last_heartbeat"] is None
    assert human["budget_total"] == 0.0


@pytest.mark.asyncio
async def test_agent_node_is_never_flagged_human(client, session_factory):  # noqa: ANN001
    """The case that must stay caught: agents keep is_human False.

    Guards against a fix that satisfies the predicate by flipping the flag on.
    """
    company_id = uuid.uuid4()
    await _seed_org_node(session_factory, company_id, name="worker-1")

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text

    nodes = _flatten(resp.json()["nodes"])
    assert len(nodes) == 1
    assert nodes[0]["is_human"] is False
    assert nodes[0]["name"] == "worker-1"


@pytest.mark.asyncio
async def test_people_and_agents_coexist(client, session_factory):  # noqa: ANN001
    """Adding people must not displace the agent forest."""
    company_id = uuid.uuid4()
    await _seed_org_node(session_factory, company_id, name="worker-1")
    await _seed_human(session_factory, company_id, username="grace", display_name="Grace Hopper")

    nodes = _flatten((await client.get(f"/api/llc/companies/{company_id}/org-chart")).json()["nodes"])

    # Keyed by is_human rather than by sort order: an assertion that relies on
    # "Grace Hopper" < "worker-1" only holds because of ASCII case ordering, and
    # would flip on a renamed fixture for reasons unrelated to the behaviour.
    by_kind = {n["is_human"]: n["name"] for n in nodes}
    assert by_kind == {True: "Grace Hopper", False: "worker-1"}


@pytest.mark.asyncio
async def test_people_of_another_company_never_leak(client, session_factory):  # noqa: ANN001
    """Row-level company scoping on the membership query.

    The route-level tenant gate is covered in ``test_llc_org_chart``; this pins
    the ``WHERE company_id`` predicate itself. Dropping it leaves every other
    test in this file green while leaking every user of every company into every
    org chart the caller can reach — so it needs its own two-company case.
    """
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()

    await _seed_human(session_factory, company_a, username="ada", display_name="Ada Lovelace")
    await _seed_human(session_factory, company_b, username="brian", display_name="Brian Kernighan")

    nodes = _flatten((await client.get(f"/api/llc/companies/{company_a}/org-chart")).json()["nodes"])

    names = [n["name"] for n in nodes]
    assert names == ["Ada Lovelace"], f"company B's person leaked into company A: {names}"


@pytest.mark.asyncio
async def test_work_items_of_another_company_never_inflate_counts(client, session_factory):  # noqa: ANN001
    """Row-level company scoping on the assigned-count query.

    Same shape as above for the second new query: the same person may hold
    memberships in two companies, and company A's chart must not count company
    B's work.
    """
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()

    user_id = await _seed_human(session_factory, company_a, username="ada")
    # Same human, also a member of company B.
    async with session_factory() as session:
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_b,
                user_id=user_id,
                role=MembershipRole.MEMBER.value,
            )
        )
        await session.commit()

    await _seed_work_item(session_factory, company_a, status=WorkItemStatus.IN_PROGRESS.value)
    await _seed_work_item(session_factory, company_b, status=WorkItemStatus.IN_PROGRESS.value)
    await _seed_work_item(session_factory, company_b, status=WorkItemStatus.IN_PROGRESS.value)

    from sqlalchemy import update

    from llc.models.work_item import LLCWorkItem

    async with session_factory() as session:
        await session.execute(update(LLCWorkItem).values(assignee_user_id=user_id))
        await session.commit()

    nodes = _flatten((await client.get(f"/api/llc/companies/{company_a}/org-chart")).json()["nodes"])
    human = next(n for n in nodes if n["is_human"])
    assert human["assigned_item_count"] == 1, "company B's work items inflated company A's count"


@pytest.mark.asyncio
async def test_human_falls_back_to_username_when_display_name_missing(client, session_factory):  # noqa: ANN001
    """A person must never render as a bare UUID."""
    company_id = uuid.uuid4()
    await _seed_human(session_factory, company_id, display_name=None, username="anon")

    nodes = _flatten((await client.get(f"/api/llc/companies/{company_id}/org-chart")).json()["nodes"])
    assert [n["name"] for n in nodes] == ["anon"]


@pytest.mark.asyncio
async def test_human_assigned_item_count_excludes_terminal_items(client, session_factory):  # noqa: ANN001
    """assigned_item_count mirrors the agent rule: non-terminal items only."""
    company_id = uuid.uuid4()
    user_id = await _seed_human(session_factory, company_id)

    await _seed_work_item(session_factory, company_id, status=WorkItemStatus.IN_PROGRESS.value)
    await _seed_work_item(session_factory, company_id, status=WorkItemStatus.DONE.value)

    # Point both items at the human (the seed helper only wires agent assignees).
    from sqlalchemy import update

    from llc.models.work_item import LLCWorkItem

    async with session_factory() as session:
        await session.execute(
            update(LLCWorkItem).where(LLCWorkItem.company_id == company_id).values(assignee_user_id=user_id)
        )
        await session.commit()

    nodes = _flatten((await client.get(f"/api/llc/companies/{company_id}/org-chart")).json()["nodes"])
    human = next(n for n in nodes if n["is_human"])
    assert human["assigned_item_count"] == 1, "DONE items must not be counted"
