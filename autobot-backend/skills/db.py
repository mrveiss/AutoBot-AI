# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills DB engine — uses autobot_data.db (same as main backend)."""
import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_engine: AsyncEngine | None = None


def get_skills_engine() -> AsyncEngine:
    """Get or create the async SQLite engine for skills tables."""
    global _engine
    if _engine is None:
        base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        db_path = os.path.join(base, "data", "autobot_data.db")
        _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    return _engine
