# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A work item deleted between the ownership check and the cost event insert is a refusal, not a 500 (#20168)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from llc.exceptions import WorkItemNotInCompany
from llc.services import budget

pytestmark = pytest.mark.asyncio

COMPANY = str(uuid.uuid4())


def _session(*, flush_error=None):
    owner = MagicMock()
    owner.scalar_one_or_none.return_value = uuid.UUID(COMPANY)  # the ownership check passes
    session = MagicMock()
    session.execute = AsyncMock(return_value=owner)
    session.flush = AsyncMock(side_effect=flush_error)
    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=None)
    nested.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested)
    return session


async def test_a_foreign_key_failure_on_the_insert_names_the_item_as_not_found():
    session = _session(flush_error=IntegrityError("insert", {}, Exception("fk")))
    with pytest.raises(WorkItemNotInCompany):
        await budget._record_event(session, "agent", COMPANY, str(uuid.uuid4()), ("m", 1, 1, Decimal("0.01")))
    session.begin_nested.assert_called_once()  # the caller's transaction is not poisoned


async def test_a_clean_insert_records_the_event_and_an_unattributed_one_never_flushes_early():
    session = _session()
    await budget._record_event(session, "agent", COMPANY, str(uuid.uuid4()), ("m", 1, 1, Decimal("0.01")))
    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    other = _session()
    await budget._record_event(other, "agent", COMPANY, None, ("m", 1, 1, Decimal("0.01")))
    other.flush.assert_not_awaited()
