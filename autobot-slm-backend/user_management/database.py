# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dual Database Engine Management for SLM

Two SQLAlchemy async engines:
- slm_engine: Local SLM admin users
- autobot_engine: Remote AutoBot application users

Pool sizes are coordinated via SSOT config (#2860).
"""

import logging
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from user_management.config import get_autobot_db_config, get_slm_db_config

logger = logging.getLogger(__name__)

# Global engine instances
_slm_engine: AsyncEngine | None = None
_autobot_engine: AsyncEngine | None = None

# Session makers
_slm_session_maker: async_sessionmaker[AsyncSession] | None = None
_autobot_session_maker: async_sessionmaker[AsyncSession] | None = None

# Locks for thread-safe lazy initialization (#2854).
# threading.Lock is required: these synchronous getters can be called from
# thread-pool workers (e.g. startup hooks) as well as the main asyncio thread.
_slm_engine_lock = threading.Lock()
_autobot_engine_lock = threading.Lock()
_slm_session_maker_lock = threading.Lock()
_autobot_session_maker_lock = threading.Lock()


def _get_pool_config() -> dict:
    """Get database pool settings from SSOT config (#2860)."""
    try:
        from autobot_shared.ssot_config import get_config

        pool_cfg = get_config().database_pool
        return {
            "pool_size": pool_cfg.pool_size,
            "max_overflow": pool_cfg.max_overflow,
            "pool_recycle": pool_cfg.pool_recycle,
            "pool_timeout": pool_cfg.pool_timeout,
        }
    except Exception:
        logger.warning("Could not load SSOT database pool config, using defaults")
        return {
            "pool_size": 10,
            "max_overflow": 10,
            "pool_recycle": 3600,
            "pool_timeout": 30,
        }


def get_slm_engine() -> AsyncEngine:
    """Get or create SLM database engine (local).

    Thread-safe: uses _slm_engine_lock to prevent double-initialization (#2854).
    """
    global _slm_engine
    if _slm_engine is None:
        with _slm_engine_lock:
            if _slm_engine is None:
                config = get_slm_db_config()
                pool = _get_pool_config()
                _slm_engine = create_async_engine(
                    config.url,
                    echo=False,
                    pool_size=pool["pool_size"],
                    max_overflow=pool["max_overflow"],
                    pool_recycle=pool["pool_recycle"],
                    pool_timeout=pool["pool_timeout"],
                    pool_pre_ping=True,
                    connect_args={"timeout": 10},
                )
                logger.info("Created SLM database engine")
    return _slm_engine


def get_autobot_engine() -> AsyncEngine:
    """Get or create AutoBot database engine (remote on Redis VM).

    Thread-safe: uses _autobot_engine_lock to prevent double-initialization (#2854).
    """
    global _autobot_engine
    if _autobot_engine is None:
        with _autobot_engine_lock:
            if _autobot_engine is None:
                config = get_autobot_db_config()
                pool = _get_pool_config()
                _autobot_engine = create_async_engine(
                    config.url,
                    echo=False,
                    pool_size=pool["pool_size"],
                    max_overflow=pool["max_overflow"],
                    pool_recycle=pool["pool_recycle"],
                    pool_timeout=pool["pool_timeout"],
                    pool_pre_ping=True,
                    connect_args={"timeout": 10},
                )
                logger.info("Created AutoBot database engine")
    return _autobot_engine


def get_slm_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get SLM session maker.

    Thread-safe: uses _slm_session_maker_lock to prevent double-initialization (#2854).
    """
    global _slm_session_maker
    if _slm_session_maker is None:
        with _slm_session_maker_lock:
            if _slm_session_maker is None:
                engine = get_slm_engine()
                _slm_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _slm_session_maker


def get_autobot_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get AutoBot session maker.

    Thread-safe: uses _autobot_session_maker_lock to prevent double-initialization (#2854).
    """
    global _autobot_session_maker
    if _autobot_session_maker is None:
        with _autobot_session_maker_lock:
            if _autobot_session_maker is None:
                engine = get_autobot_engine()
                _autobot_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _autobot_session_maker


@asynccontextmanager
async def get_slm_session() -> AsyncGenerator[AsyncSession, None]:
    """Get SLM database session (context manager)."""
    session_maker = get_slm_session_maker()
    async with session_maker() as session:
        session.info["_post_commit_cbs"] = []
        try:
            yield session
            await session.commit()
            for cb in session.info.pop("_post_commit_cbs", []):
                await cb()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_autobot_session() -> AsyncGenerator[AsyncSession, None]:
    """Get AutoBot database session (context manager)."""
    session_maker = get_autobot_session_maker()
    async with session_maker() as session:
        session.info["_post_commit_cbs"] = []
        try:
            yield session
            await session.commit()
            for cb in session.info.pop("_post_commit_cbs", []):
                await cb()
        except Exception:
            await session.rollback()
            raise


async def health_check_slm() -> bool:
    """Check SLM database connection health."""
    try:
        async with get_slm_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("SLM database health check failed: %s", e)
        return False


async def health_check_autobot() -> bool:
    """Check AutoBot database connection health."""
    try:
        async with get_autobot_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("AutoBot database health check failed: %s", e)
        return False


async def close_engines() -> None:
    """Close all database engines (for graceful shutdown)."""
    global _slm_engine, _autobot_engine
    if _slm_engine is not None:
        await _slm_engine.dispose()
        _slm_engine = None
        logger.info("Closed SLM database engine")
    if _autobot_engine is not None:
        await _autobot_engine.dispose()
        _autobot_engine = None
        logger.info("Closed AutoBot database engine")


# Alias for rbac_middleware compatibility (uses SLM database by default)
db_session_context = get_slm_session
