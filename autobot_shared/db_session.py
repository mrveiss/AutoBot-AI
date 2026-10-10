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

from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: `session.info` key holding coroutines to run only after a successful commit.
#: `UserService` appends to it (e.g. cache invalidation), so the name is shared state.
POST_COMMIT_CALLBACKS = "_post_commit_cbs"


class PostCommitCallbackError(Exception):
    """One or more post-commit callbacks failed AFTER the transaction committed.

    The data is durable; `errors` holds every callback failure, in order.
    """

    def __init__(self, errors: list[Exception]) -> None:
        super().__init__(f"{len(errors)} post-commit callback(s) failed after the transaction committed: {errors!r}")
        self.errors = errors


def _rollback_sync(session: Session) -> None:
    """Roll back, logging a rollback failure so it cannot replace the original error."""
    try:
        session.rollback()
    except Exception:
        logger.error("session rollback failed; re-raising the original error", exc_info=True)


async def _rollback_async(session: AsyncSession) -> None:
    """Async twin of `_rollback_sync`."""
    try:
        await session.rollback()
    except Exception:
        logger.error("session rollback failed; re-raising the original error", exc_info=True)


async def _run_post_commit_callbacks(session: AsyncSession) -> None:
    """Run EVERY callback after a successful commit, then raise one `PostCommitCallbackError`.

    The data is already durable, so a failing callback must not roll anything back or
    stop the callbacks after it. Each failure is logged; the caller still learns of them.
    """
    errors: list[Exception] = []
    for cb in session.info.pop(POST_COMMIT_CALLBACKS, []):
        try:
            await cb()
        except Exception as exc:
            logger.error("post-commit callback failed after a successful commit", exc_info=True)
            errors.append(exc)
    if errors:
        raise PostCommitCallbackError(errors) from errors[0]


@contextmanager
def session_scope(session_factory: Callable[[], Session]) -> Generator[Session, None, None]:
    """Canonical sync session context manager.

    Commits on clean exit, rolls back on any exception, and always closes. A failing
    rollback is logged and never replaces the original exception.
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
        _rollback_sync(session)
        raise
    finally:
        session.close()


@asynccontextmanager
async def async_session_scope(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session that commits on success and rolls back on error (#15068).

    Seeds the post-commit callback list; the callbacks run only after the commit
    succeeds, so a rolled-back transaction never triggers them. Once the commit has
    succeeded nothing is rolled back: every callback runs, each failure is logged, and
    a `PostCommitCallbackError` carrying all of them is raised after all have run. A failing rollback is
    logged and never replaces the original exception. The `async with` on the factory
    closes the session on every path.
    """
    async with session_maker() as session:
        session.info[POST_COMMIT_CALLBACKS] = []
        try:
            yield session
            await session.commit()
        except Exception:
            await _rollback_async(session)
            raise
        await _run_post_commit_callbacks(session)
