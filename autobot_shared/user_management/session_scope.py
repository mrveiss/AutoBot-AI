# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One transaction scope for a user-management database session (#15068).

Both services' `user_management.database` opened a session the same way: seed the
post-commit callback list, commit on success, then run the callbacks, and roll back
on any error. That body was written four times, twice in each service. This is it
once.

The session FACTORY stays per service on purpose, because each service binds its own
engine. So the shared piece takes the factory as an argument, and each service's
`db_session_context` passes its own. A plain re-export could not keep that binding.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

#: `session.info` key holding coroutines to run only after a successful commit.
#: `UserService` appends to it (e.g. cache invalidation), so the name is shared state.
POST_COMMIT_CALLBACKS = "_post_commit_cbs"


@asynccontextmanager
async def session_scope(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a session that commits on success and rolls back on error.

    Post-commit callbacks run only after the commit succeeds, so a rolled-back
    transaction never triggers them. The `async with` on the factory closes the
    session on every path.
    """
    async with session_maker() as session:
        session.info[POST_COMMIT_CALLBACKS] = []
        try:
            yield session
            await session.commit()
            for cb in session.info.pop(POST_COMMIT_CALLBACKS, []):
                await cb()
        except Exception:
            await session.rollback()
            raise
