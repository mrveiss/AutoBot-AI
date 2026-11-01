# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Void the earlier tokens of every member of an organisation that is deactivated or deleted (#20443).

A token is checked against a per-username epoch marker, never against its account's or organisation's
state, so deactivating an organisation revokes nothing until each member's marker is written. The
markers are written once the transaction commits, one per member
(:class:`~autobot_shared.user_management.password_epoch.MembersPasswordEpochMark`).

Who is a member: every row of the user table whose ``org_id`` is the organisation, active or not,
soft-deleted or not. An inactive member was marked when it was deactivated, but one deactivated before
that marking existed was not, and re-marking is harmless (the stored epoch only rises). A user of
another organisation who belongs to one of this one's teams is NOT a member: the token is the user's own
and its organisation is untouched, so voiding it would sign out an account this change does not affect.

Limit: the set is read when the organisation is deactivated or deleted. A member added to it afterwards
is not covered, and a token that member holds is not voided by this change.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.db_session import run_after_commit
from autobot_shared.user_management.models.user import UserCore
from autobot_shared.user_management.password_epoch import DEACTIVATION_EPOCH_LEAD_SECONDS, MembersPasswordEpochMark


async def queue_member_token_revocation(
    session: AsyncSession, user_model: type[UserCore], org_id: uuid.UUID, *, in_redis: bool = False
) -> dict:
    """Queue one post-commit epoch mark per member of *org_id*; return the audit details.

    Read while the member rows exist (a hard delete cascades them away). One query, however many
    members. The details say how many were queued, not that they were written: that happens after
    the commit and may fail, which the session scope reports as ``PostCommitCallbackError``.
    """
    rows = await session.execute(select(user_model.username).where(user_model.org_id == org_id))
    usernames = tuple(sorted(set(rows.scalars().all())))
    if usernames:
        run_after_commit(session, MembersPasswordEpochMark(usernames, DEACTIVATION_EPOCH_LEAD_SECONDS, in_redis))
    return {"sessions_revocation": "queued_after_commit", "members_queued": len(usernames)}
