# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the KB write guard (GH#8598).

Verifies that assert_not_writing_to_ancestor_kb raises HTTP 403 when a
sub-company agent targets an ancestor org's KB, and passes in all other cases.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from llc.kb.write_guard import assert_not_writing_to_ancestor_kb

GRANDPARENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PARENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
CHILD_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
SIBLING_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")


def _session_for_chain(*parent_pairs: tuple[uuid.UUID, uuid.UUID | None]) -> AsyncMock:
    """Build a mock session that resolves parent_org_id lookups.

    Each tuple is (org_id, parent_org_id).  The session returns the matching
    parent for each execute() call in order.
    """
    lookup = {org_id: parent for org_id, parent in parent_pairs}

    async def _execute(stmt):
        # Extract the WHERE id == X clause to find which org is being queried.
        # We inspect the compiled params; simpler: capture calls in order.
        result = MagicMock()
        # We can't easily inspect SQLAlchemy statements in unit tests, so we
        # store the lookup table and return a sentinel that the mock resolves.
        result.scalar_one_or_none = MagicMock(return_value=None)
        return result

    session = AsyncMock()
    return session


def _session_with_ancestry(requester_id: uuid.UUID, ancestors: list[uuid.UUID]) -> AsyncMock:
    """Return a session mock that walks ancestry: requester → ancestors[0] → … → None."""
    chain = ancestors + [None]
    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        parent = chain[min(call_count, len(chain) - 1)]
        call_count += 1
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=parent)
        return result

    session = AsyncMock()
    session.execute.side_effect = _execute
    return session


class TestAssertNotWritingToAncestorKb:
    async def test_same_org_is_allowed(self):
        session = AsyncMock()
        # Should not raise and should not even query the DB.
        await assert_not_writing_to_ancestor_kb(str(CHILD_ID), str(CHILD_ID), session)
        session.execute.assert_not_called()

    async def test_missing_requester_org_is_allowed(self):
        session = AsyncMock()
        await assert_not_writing_to_ancestor_kb(None, str(PARENT_ID), session)
        session.execute.assert_not_called()

    async def test_missing_target_org_is_allowed(self):
        session = AsyncMock()
        await assert_not_writing_to_ancestor_kb(str(CHILD_ID), None, session)
        session.execute.assert_not_called()

    async def test_write_to_direct_parent_is_blocked(self):
        # CHILD's parent is PARENT — writing to PARENT must be blocked.
        session = _session_with_ancestry(CHILD_ID, [PARENT_ID])
        with pytest.raises(HTTPException) as exc_info:
            await assert_not_writing_to_ancestor_kb(str(CHILD_ID), str(PARENT_ID), session)
        assert exc_info.value.status_code == 403

    async def test_write_to_grandparent_is_blocked(self):
        # CHILD → PARENT → GRANDPARENT
        session = _session_with_ancestry(CHILD_ID, [PARENT_ID, GRANDPARENT_ID])
        with pytest.raises(HTTPException) as exc_info:
            await assert_not_writing_to_ancestor_kb(str(CHILD_ID), str(GRANDPARENT_ID), session)
        assert exc_info.value.status_code == 403

    async def test_write_to_unrelated_org_is_allowed(self):
        # CHILD's ancestors are PARENT only; SIBLING is not in the chain.
        session = _session_with_ancestry(CHILD_ID, [PARENT_ID])
        # Should not raise.
        await assert_not_writing_to_ancestor_kb(str(CHILD_ID), str(SIBLING_ID), session)

    async def test_root_org_write_to_any_org_is_allowed(self):
        # Root org has no parent — writing to any other org is not blocked by ancestry.
        session = _session_with_ancestry(PARENT_ID, [])  # no ancestors
        await assert_not_writing_to_ancestor_kb(str(PARENT_ID), str(SIBLING_ID), session)

    async def test_malformed_uuid_is_skipped(self):
        session = AsyncMock()
        # Should not raise, not query DB.
        await assert_not_writing_to_ancestor_kb("not-a-uuid", str(PARENT_ID), session)
        session.execute.assert_not_called()

    async def test_cycle_in_ancestry_does_not_loop_forever(self):
        # Simulate a corrupt cycle: CHILD → PARENT → CHILD (visited guard).
        call_count = 0
        cycle = [PARENT_ID, CHILD_ID]  # will trigger visited guard on CHILD_ID

        async def _execute(stmt):
            nonlocal call_count
            parent = cycle[min(call_count, len(cycle) - 1)]
            call_count += 1
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=parent)
            return result

        session = AsyncMock()
        session.execute.side_effect = _execute
        # SIBLING_ID is the target — it's not in the corrupt cycle, so no 403.
        await assert_not_writing_to_ancestor_kb(str(CHILD_ID), str(SIBLING_ID), session)
