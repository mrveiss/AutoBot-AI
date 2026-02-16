# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
PostgreSQL Database Connection Utilities

Provides async SQLAlchemy session management with connection pooling.
Follows the canonical client pattern established by Redis utilities.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.user_management.config import get_deployment_config

logger = logging.getLogger(__name__)

# Singleton engine instance
_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine() -> AsyncEngine:
    """
    Get the async SQLAlchemy engine singleton.

    Creates the engine on first call with connection pooling configured
    to match the Redis pool size (20 connections).
    """
    global _async_engine

    if _async_engine is not None:
        return _async_engine

    config = get_deployment_config()

    if not config.postgres_enabled:
        raise RuntimeError(
            "PostgreSQL is not enabled for deployment mode: "
            f"{config.mode.value}. Set AUTOBOT_DEPLOYMENT_MODE to "
            "single_company, multi_company, or provider."
        )

    _async_engine = create_async_engine(
        config.postgres_url,
        pool_size=5,  # Number of connections to maintain
        max_overflow=10,  # Max additional connections under load
        pool_pre_ping=True,  # Verify connections before use
        echo=False,  # Set to True for SQL debugging
        future=True,
    )

    logger.info(
        "PostgreSQL async engine created: %s:%d/%s",
        config.postgres_host,
        config.postgres_port,
        config.postgres_db,
    )

    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the async session factory singleton."""
    global _async_session_factory

    if _async_session_factory is not None:
        return _async_session_factory

    engine = get_async_engine()

    _async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
        sync_session_class=None,  # Issue #898: Disable sync session fallback
    )

    return _async_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints to get an async database session.

    Usage:
        @router.get("/users")
        async def get_users(session: AsyncSession = Depends(get_async_session)):
            ...
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def db_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.

    Usage:
        async with db_session_context() as session:
            result = await session.execute(query)
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database() -> None:
    """
    Initialize the database connection and verify connectivity.

    Call this during application startup.
    """
    logger.info("🔍 DEBUG: init_database() called")
    config = get_deployment_config()
    logger.info(
        f"🔍 DEBUG: Got deployment config - postgres_enabled={config.postgres_enabled}"
    )

    if not config.postgres_enabled:
        logger.info(
            "PostgreSQL disabled for deployment mode: %s",
            config.mode.value,
        )
        return

    logger.info("🔍 DEBUG: PostgreSQL enabled, proceeding with initialization")
    logger.info(
        "🔍 DEBUG: Connection string: postgresql+asyncpg://"
        f"{config.postgres_user}@{config.postgres_host}:"
        f"{config.postgres_port}/{config.postgres_db}"
    )

    try:
        from sqlalchemy import text

        logger.info("🔍 DEBUG: About to call get_async_engine()")
        engine = get_async_engine()
        logger.info(f"🔍 DEBUG: Engine created: {engine}")

        logger.info(
            "🔍 DEBUG: About to begin connection (this may hang if DB unreachable)"
        )
        async with engine.begin() as conn:
            logger.info("🔍 DEBUG: Connection established, executing SELECT 1")
            # Simple connectivity check
            await conn.execute(text("SELECT 1"))
            logger.info("🔍 DEBUG: SELECT 1 executed successfully")
        logger.info("PostgreSQL connection verified successfully")
    except Exception as e:
        logger.error("Failed to connect to PostgreSQL: %s", e)
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


async def close_database() -> None:
    """
    Close the database connection pool.

    Call this during application shutdown.
    """
    global _async_engine, _async_session_factory

    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
        logger.info("PostgreSQL connection pool closed")


async def check_database_health() -> dict:
    """
    Check database health status.

    Returns:
        dict with health status information
    """
    config = get_deployment_config()

    if not config.postgres_enabled:
        return {
            "status": "disabled",
            "mode": config.mode.value,
            "message": "PostgreSQL not enabled for this deployment mode",
        }

    try:
        from sqlalchemy import text

        engine = get_async_engine()
        pool = engine.pool

        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.close()

        return {
            "status": "healthy",
            "mode": config.mode.value,
            "host": config.postgres_host,
            "port": config.postgres_port,
            "database": config.postgres_db,
            "pool_size": pool.size() if pool else 0,
            "pool_checked_in": pool.checkedin() if pool else 0,
            "pool_checked_out": pool.checkedout() if pool else 0,
            "pool_overflow": pool.overflow() if pool else 0,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "mode": config.mode.value,
            "error": str(e),
        }
