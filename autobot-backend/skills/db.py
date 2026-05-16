# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills DB engine — uses autobot_data.db (same as main backend)."""

import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.ssot_config import config


class _SkillsEngineManager:
    """Owns the async SQLite engine lifecycle under a single internal lock.

    Supports lazy construction (get) and disposal with reset (close),
    which prevents use of the stateless lazy_singleton primitive.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def get(self) -> AsyncEngine:
        """Return the singleton engine, constructing it on first call."""
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    base = config.base_dir
                    db_path = os.path.join(base, "data", "autobot_data.db")
                    self._engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        return self._engine

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the singleton session factory, constructing it on first call."""
        if self._session_factory is None:
            with self._lock:
                if self._session_factory is None:
                    self._session_factory = async_sessionmaker(
                        bind=self.get(),
                        class_=AsyncSession,
                        expire_on_commit=False,
                        autocommit=False,
                        autoflush=False,
                    )
        return self._session_factory

    async def close(self) -> None:
        """Dispose the engine and reset the reference for future reuse."""
        with self._lock:
            engine, self._engine = self._engine, None
            self._session_factory = None
        if engine is not None:
            await engine.dispose()


_manager = _SkillsEngineManager()


def get_skills_engine() -> AsyncEngine:
    """Get or create the async SQLite engine for skills tables.

    Thread-safe singleton. Uses AUTOBOT_BASE_DIR env var for DB path.
    """
    return _manager.get()


async def close_skills_engine() -> None:
    """Dispose the engine on application shutdown."""
    await _manager.close()


@asynccontextmanager
async def skills_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Canonical session context manager for the skills SQLite database.

    Commits on clean exit, rolls back on any exception, and always closes.
    Mirrors db_session_context() from user_management.database for the
    skills subsystem (GH#7441).

    Usage:
        async with skills_session_context() as session:
            session.add(obj)
    """
    session_factory = _manager.get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
