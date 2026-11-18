# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20030: a removal locks the user row before it scans sessions, so an owner assignment waits or sees it."""

import uuid
from unittest.mock import AsyncMock, MagicMock

from user_management.services import session_successor


async def test_both_removal_entry_points_lock_the_user_row() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    await session_successor.check_user_sessions(db, uuid.uuid4(), "admin")
    await session_successor.reassign_user_sessions(db, uuid.uuid4(), "admin")
    assert [c.kwargs for c in db.get.await_args_list] == [{"with_for_update": True}] * 2
