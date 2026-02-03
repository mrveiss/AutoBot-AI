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
        """Initialize default settings and ensure all required settings exist."""
        async with self.session_factory() as session:
            from sqlalchemy import select

            # All required settings with defaults
            required_settings = {
                "initialized": ("true", "bool", "Database initialization flag"),
                "monitoring_location": (
                    "local", "string", "Monitoring services location (local/external)"
                ),
                "prometheus_url": (
                    "http://localhost:9090", "string", "Prometheus server URL"
                ),
                "grafana_url": (
                    "http://localhost:3000", "string", "Grafana server URL"
                ),
                "heartbeat_timeout": (
                    "60", "int", "Node heartbeat timeout in seconds"
                ),
                "auto_reconcile": (
                    "false", "bool", "Enable automatic role reconciliation"
                ),
                "auto_remediate": (
                    "true", "bool", "Enable auto-restart of SLM agent on degraded nodes"
                ),
                "auto_restart_services": (
                    "true", "bool", "Enable auto-restart of failed AutoBot services"
                ),
                "auto_rollback": (
                    "false", "bool", "Enable automatic deployment rollback on failure"
                ),
                "rollback_window_seconds": (
                    "600", "int", "Time window (seconds) for auto-rollback eligibility"
                ),
            }

            # Check which settings exist
            result = await session.execute(select(Setting))
            existing_keys = {s.key for s in result.scalars().all()}

            # Add missing settings
            added = []
            for key, (value, value_type, description) in required_settings.items():
                if key not in existing_keys:
                    session.add(Setting(
                        key=key,
                        value=value,
                        value_type=value_type,
                        description=description,
                    ))
                    added.append(key)

            if added:
                await session.commit()
                logger.info("Added missing settings: %s", ", ".join(added))

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
