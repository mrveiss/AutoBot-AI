# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# flake8: noqa: F811 -- fixtures imported from the #21586 batch are re-bound as parameters
"""A gated handoff enforces the policy's reviewer role (#21588); an approval needs an item in review (#21632).

Real services and a real in-memory database (the fixtures of the #21586 batch); only what leaves the process is faked.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import update

from llc.models.enums import MembershipRole, WorkItemStatus, WorkItemType
from llc.models.membership import LLCCompanyMembership
from llc.models.review_gate import LLCReviewGatePolicy
from llc.models.work_item import LLCWorkItem
from llc.services.handoff import HandoffService, ReviewerLacksRole
from llc.services.work_item_own_task import InvalidTransition
from llc.tests.test_review_handoff_batch_21586 import effects  # noqa: F401 -- autouse fixture
from llc.tests.test_review_handoff_batch_21586 import factory  # noqa: F401 -- fixture
from llc.tests.test_review_handoff_batch_21586 import (
    _COMPANY,
    _ITEM,
    _NODE,
    _REVIEWER,
    _STRANGER,
    _agent_sets,
    _post,
    _row,
    _seed,
    _snapshot,
)

pytestmark = pytest.mark.asyncio


async def _policy(
    factory, role: str | None, *, reviewer_holds: MembershipRole = MembershipRole.MEMBER
) -> None:  # noqa: ANN001
    """A bug policy that requires review and names *role*; the reviewer's company role is *reviewer_holds*."""
    async with factory() as session:
        session.add(
            LLCReviewGatePolicy(
                company_id=_COMPANY,
                item_type=WorkItemType.BUG,
                requires_human_review=True,
                reviewer_role=role,
                requires_cross_vendor_review=False,
            )
        )
        await session.execute(
            update(LLCCompanyMembership).where(LLCCompanyMembership.user_id == _REVIEWER).values(role=reviewer_holds)
        )
        await session.commit()


async def _hand_off(factory) -> None:  # noqa: ANN001
    async with factory() as session:
        await HandoffService().agent_to_human(session, str(_ITEM), str(_NODE), str(_REVIEWER), str(_COMPANY))
        await session.commit()


# --- #21588: the policy's reviewer_role ---------------------------------------------------------------------------


async def test_the_gated_done_path_refuses_a_reviewer_without_the_role(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER)
    await _policy(factory, "admin")

    with pytest.raises(HTTPException) as refused:
        await _agent_sets(_ITEM, "done")

    assert refused.value.status_code == 409 and "'admin'" in refused.value.detail
    assert (await _row(factory)).status == WorkItemStatus.IN_PROGRESS


async def test_the_gated_done_path_accepts_a_reviewer_with_the_role(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER)
    await _policy(factory, "admin", reviewer_holds=MembershipRole.ADMIN)

    assert (await _agent_sets(_ITEM, "done"))["status"] == "in_review"


async def test_the_manual_handoff_refuses_a_reviewer_without_the_role(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG)
    await _policy(factory, "admin")
    await _promote(factory, _STRANGER)  # the caller manages agent work; the named reviewer does not hold the role

    response = await _post(factory, _STRANGER, "handoff/to-human", {"reviewer_user_id": str(_REVIEWER)})

    assert response.status_code == 403, response.text
    assert "'admin'" in response.json()["detail"]
    assert (await _row(factory)).status == WorkItemStatus.IN_PROGRESS


async def test_the_manual_handoff_accepts_a_reviewer_with_the_role(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG)
    await _policy(factory, "admin", reviewer_holds=MembershipRole.ADMIN)
    await _promote(factory, _STRANGER)

    response = await _post(factory, _STRANGER, "handoff/to-human", {"reviewer_user_id": str(_REVIEWER)})

    assert response.status_code == 200, response.text
    assert (await _row(factory)).status == WorkItemStatus.IN_REVIEW


async def test_a_policy_without_a_role_changes_nothing(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER)
    await _policy(factory, None)

    await _hand_off(factory)

    assert (await _row(factory)).status == WorkItemStatus.IN_REVIEW


async def test_a_role_on_a_policy_that_needs_no_review_changes_nothing(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER)
    await _policy(factory, "admin")
    async with factory() as session:
        await session.execute(update(LLCReviewGatePolicy).values(requires_human_review=False))
        await session.commit()

    await _hand_off(factory)

    assert (await _row(factory)).status == WorkItemStatus.IN_REVIEW


@pytest.mark.parametrize("holds", [MembershipRole.OWNER, MembershipRole.ADMIN])
@pytest.mark.parametrize("gate", ["member", "lead"])
async def test_an_owner_or_admin_qualifies_for_any_role(factory, holds, gate) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER)
    await _policy(factory, gate, reviewer_holds=holds)

    await _hand_off(factory)

    assert (await _row(factory)).status == WorkItemStatus.IN_REVIEW


@pytest.mark.parametrize("holds", [MembershipRole.MEMBER, MembershipRole.LEAD, MembershipRole.GUEST])
async def test_a_role_below_owner_and_admin_must_match_exactly(factory, holds) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER)
    await _policy(factory, "admin", reviewer_holds=holds)

    with pytest.raises(ReviewerLacksRole):
        await _hand_off(factory)


async def test_the_webhook_route_gives_the_lacks_role_reason(factory) -> None:  # noqa: ANN001
    from llc.api.github_webhooks import _REFUSAL_TEXT
    from llc.api.github_webhooks import _hand_off as webhook_hand_off
    from llc.services.work_item_gated_done import ReviewRefused

    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER)
    await _policy(factory, "admin")
    async with factory() as session:
        item = await _loaded(session)
        why = await webhook_hand_off(session, item)

    assert why == _REFUSAL_TEXT[ReviewRefused.LACKS_ROLE]
    assert (await _row(factory)).status == WorkItemStatus.IN_PROGRESS


async def test_a_reviewer_demoted_after_the_handoff_cannot_approve(factory, effects) -> None:  # noqa: ANN001
    await _seed(
        factory, type_=WorkItemType.BUG, agent=None, user=_REVIEWER, status=WorkItemStatus.IN_REVIEW, reviewer=_REVIEWER
    )
    await _policy(factory, "lead", reviewer_holds=MembershipRole.MEMBER)
    before = await _snapshot(factory)

    with pytest.raises(ReviewerLacksRole):
        async with factory() as session:
            await HandoffService().approve(session, str(_ITEM), str(_REVIEWER), str(_COMPANY))

    assert await _snapshot(factory) == before


async def _loaded(session):  # noqa: ANN001, ANN202
    from sqlalchemy import select

    from llc.models.work_item import LLCWorkItem

    return (await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == _ITEM))).scalar_one()


async def test_the_service_names_the_role_it_refuses_for(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER)
    await _policy(factory, "lead")
    before = await _snapshot(factory)

    with pytest.raises(ReviewerLacksRole, match="'lead'"):
        await _hand_off(factory)

    assert await _snapshot(factory) == before


async def _created_by_reviewer(factory) -> None:  # noqa: ANN001
    """The reviewer also created the item: with the assignee, that makes them its own-task owner."""
    async with factory() as session:
        await session.execute(update(LLCWorkItem).where(LLCWorkItem.id == _ITEM).values(created_by_user_id=_REVIEWER))
        await session.commit()


async def _promote(factory, user: uuid.UUID) -> None:  # noqa: ANN001
    async with factory() as session:
        await session.execute(
            update(LLCCompanyMembership).where(LLCCompanyMembership.user_id == user).values(role=MembershipRole.ADMIN)
        )
        await session.commit()


# --- #21632: an approval needs an item in review ------------------------------------------------------------------


@pytest.mark.parametrize("status", [WorkItemStatus.BACKLOG, WorkItemStatus.READY, WorkItemStatus.IN_PROGRESS])
async def test_a_creator_reviewer_cannot_approve_an_item_that_is_not_in_review(factory, status) -> None:  # noqa: ANN001
    # the reviewer also holds the item, so the allowed-transition table alone would let them finish it
    await _seed(factory, agent=None, user=_REVIEWER, status=status, reviewer=_REVIEWER)
    await _created_by_reviewer(factory)
    before = await _snapshot(factory)

    with pytest.raises(InvalidTransition, match="not in_review"):
        async with factory() as session:
            await HandoffService().approve(session, str(_ITEM), str(_REVIEWER), str(_COMPANY))

    assert await _snapshot(factory) == before


async def test_an_approval_keeps_the_assignee_and_bumps_the_version_once(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, agent=None, user=_REVIEWER, status=WorkItemStatus.IN_REVIEW, reviewer=_REVIEWER)
    await _created_by_reviewer(factory)
    before = await _row(factory)

    async with factory() as session:
        await HandoffService().approve(session, str(_ITEM), str(_REVIEWER), str(_COMPANY))
        await session.commit()

    after = await _row(factory)
    assert after.status == WorkItemStatus.DONE
    assert (after.assignee_user_id, after.assignee_type) == (before.assignee_user_id, before.assignee_type)
    assert after.version == before.version + 1
