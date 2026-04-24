# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills DB engine — uses autobot_data.db (same as main backend)."""

import os
import threading
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class _SkillsEngineManager:
    """Owns the async SQLite engine lifecycle under a single internal lock.

    Supports lazy construction (get) and disposal with reset (close),
    which prevents use of the stateless lazy_singleton primitive.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._engine: Optional[AsyncEngine] = None

    def get(self) -> AsyncEngine:
        """Return the singleton engine, constructing it on first call."""
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
                    db_path = os.path.join(base, "data", "autobot_data.db")
                    self._engine = create_async_engine(
                        f"sqlite+aiosqlite:///{db_path}"
                    )
        return self._engine

    async def close(self) -> None:
        """Dispose the engine and reset the reference for future reuse."""
        with self._lock:
            engine, self._engine = self._engine, None
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
