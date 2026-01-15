# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Database Service

Database connection and session management.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models.database import Base, Setting

logger = logging.getLogger(__name__)


class DatabaseService:
    """Manages database connections and sessions."""

    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the database connection and create tables."""
        if self._initialized:
            return

        db_path = Path(settings.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        logger.info("Connecting to database: %s", db_path)

        self.engine = create_async_engine(
            database_url,
            echo=settings.debug,
            future=True,
        )

        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await self._initialize_defaults()
        self._initialized = True
        logger.info("Database initialized successfully")

    async def _initialize_defaults(self) -> None:
        """Initialize default settings and roles."""
        async with self.session_factory() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(Setting).where(Setting.key == "initialized")
            )
            if result.scalar_one_or_none():
                return

            default_settings = [
                Setting(
                    key="initialized",
                    value="true",
                    value_type="bool",
                    description="Database initialization flag",
                ),
                Setting(
                    key="monitoring_location",
                    value="local",
                    value_type="string",
                    description="Monitoring services location (local/external)",
                ),
                Setting(
                    key="prometheus_url",
                    value="http://localhost:9090",
                    value_type="string",
                    description="Prometheus server URL",
                ),
                Setting(
                    key="grafana_url",
                    value="http://localhost:3000",
                    value_type="string",
                    description="Grafana server URL",
                ),
                Setting(
                    key="heartbeat_timeout",
                    value="60",
                    value_type="int",
                    description="Node heartbeat timeout in seconds",
                ),
                Setting(
                    key="auto_reconcile",
                    value="false",
                    value_type="bool",
                    description="Enable automatic role reconciliation",
                ),
            ]

            for setting in default_settings:
                session.add(setting)

            await session.commit()
            logger.info("Default settings initialized")

    async def close(self) -> None:
        """Close the database connection."""
        if self.engine:
            await self.engine.dispose()
            self._initialized = False
            logger.info("Database connection closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self._initialized:
            await self.initialize()

        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


db_service = DatabaseService()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with db_service.session() as session:
        yield session
