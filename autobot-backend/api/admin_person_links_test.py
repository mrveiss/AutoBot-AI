# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: failed pushes are listed for admins."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from api import admin_person_links as route


async def test_a_failure_is_listed_by_name_and_time() -> None:
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=[("alice", since, "ConnectionError")]))
    )
    response = await route.person_push_failures(session)
    assert [(f.username, f.failed_since, f.error) for f in response.failures] == [("alice", since, "ConnectionError")]
