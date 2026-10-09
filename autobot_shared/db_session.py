# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical SQLAlchemy session lifecycle helpers (GH#7441, #15068).

Provides session_scope() for sync callers and async_session_scope() for async ones,
each with commit-on-exit, rollback-on-error, and guaranteed close semantics in one place.

Async callers normally reach async_session_scope() through the hosting service's
db_session_context() in user_management.database, which passes that service's own
session maker (each service binds its own engine).
"""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Callable, Generator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

#: `session.info` key holding coroutines to run only after a successful commit.
#: `UserService` appends to it (e.g. cache invalidation), so the name is shared state.
POST_COMMIT_CALLBACKS = "_post_commit_cbs"


@contextmanager
def session_scope(session_factory: Callable[[], Session]) -> Generator[Session, None, None]:
    """Canonical sync session context manager.

    Commits on clean exit, rolls back on any exception, and always closes.
    Eliminates bare ``session_factory()`` calls that lack rollback protection.

    Args:
        session_factory: A SQLAlchemy ``sessionmaker`` instance (or any
            zero-argument callable returning a ``Session``).

    Usage::

        with session_scope(SessionLocal) as session:
            session.add(obj)
    """
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def async_session_scope(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session that commits on success and rolls back on error (#15068).

    Seeds the post-commit callback list; the callbacks run only after the commit
    succeeds, so a rolled-back transaction never triggers them. The `async with` on
    the factory closes the session on every path.
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
