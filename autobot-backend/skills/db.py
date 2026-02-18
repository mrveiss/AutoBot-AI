# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills DB engine — uses autobot_data.db (same as main backend)."""
import os
import threading

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_engine: AsyncEngine | None = None
_engine_lock = threading.Lock()


def get_skills_engine() -> AsyncEngine:
    """Get or create the async SQLite engine for skills tables.

    Thread-safe singleton. Uses AUTOBOT_BASE_DIR env var for DB path.
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
                db_path = os.path.join(base, "data", "autobot_data.db")
                _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    return _engine


async def close_skills_engine() -> None:
    """Dispose the engine on application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
