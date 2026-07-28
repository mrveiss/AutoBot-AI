# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
PostgreSQL Database Connection Utilities

Provides async SQLAlchemy session management with connection pooling.
Follows the canonical client pattern established by Redis utilities.
Pool sizes are coordinated via SSOT config (#2860).
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import database_pool_settings
from user_management.config import get_deployment_config

logger = get_logger(__name__)

# Singleton engine instance
_async_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def _env_int(name: str, default: int, minimum: int) -> int:
    """Parse a positive-integer env var, falling back safely on garbage (#12293)."""
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        logger.warning("Invalid %s — using default %d", name, default)
        return default


def _env_float(name: str, default: float, minimum: float) -> float:
    """Parse a non-negative-float env var, falling back safely on garbage (#12293)."""
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        logger.warning("Invalid %s — using default %s", name, default)
        return default


# Issue #12293: Bounded startup retry for *transient* DB unavailability (e.g. the
# database container is still coming up). Permanent credential/authorization
# faults fail fast with zero retries. Tunable via env — never hardcoded.
_DB_INIT_MAX_ATTEMPTS = _env_int("AUTOBOT_DB_INIT_MAX_ATTEMPTS", 5, minimum=1)
_DB_INIT_RETRY_DELAY_SECONDS = _env_float("AUTOBOT_DB_INIT_RETRY_DELAY_SECONDS", 3.0, minimum=0.0)

# PostgreSQL SQLSTATEs that signal a permanent credential / config fault where
# retrying can never succeed (#12293):
#   Class 28  — invalid authorization specification (28P01 = invalid_password)
#   3D000     — invalid_catalog_name (target database does not exist)
_PERMANENT_PG_SQLSTATES = frozenset({"3D000"})
_PERMANENT_PG_SQLSTATE_CLASSES = ("28",)
_PERMANENT_PG_ERROR_NAMES = frozenset(
    {
        "InvalidPasswordError",
        "InvalidAuthorizationSpecificationError",
        "InvalidCatalogNameError",
    }
)


def _is_permanent_db_error(exc: BaseException) -> bool:
    """Return True when a DB connection error is a permanent credential /
    authorization / missing-database fault that retrying cannot fix (#12293).

    Walks the full exception chain (``__cause__`` / ``__context__`` / SQLAlchemy
    ``orig``) to reach the underlying asyncpg error and inspects its SQLSTATE.
    """
    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        sqlstate = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if isinstance(sqlstate, str) and (
            sqlstate in _PERMANENT_PG_SQLSTATES or sqlstate.startswith(_PERMANENT_PG_SQLSTATE_CLASSES)
        ):
            return True
        if type(current).__name__ in _PERMANENT_PG_ERROR_NAMES:
            return True
        stack.extend((current.__cause__, current.__context__, getattr(current, "orig", None)))
    return False


def _get_pool_config() -> dict:
    """Database pool settings from SSOT config (#2860).

    Thin alias over the canonical ``autobot_shared.ssot_config`` helper: this
    body was byte-identical here and in the sibling backend (#12645), so a
    tuning change had to be made twice or it silently applied to one engine.
    Kept as a named function because callers reference it.
    """
    return database_pool_settings()


def get_async_engine() -> AsyncEngine:
    """
    Get the async SQLAlchemy engine singleton.

    Creates the engine on first call with connection pooling configured
    from SSOT config (#2860).
    """
    global _async_engine

    if _async_engine is not None:
        return _async_engine

    config = get_deployment_config()

    if not config.postgres_enabled:
        raise RuntimeError(
            "PostgreSQL is not enabled for deployment mode: "
            f"{config.mode.value}. Set AUTOBOT_USER_MODE to "
            "single_company, multi_company, or provider."
        )

    pool = _get_pool_config()

    _async_engine = create_async_engine(
        config.postgres_url,
        pool_size=pool["pool_size"],
        max_overflow=pool["max_overflow"],
        pool_recycle=pool["pool_recycle"],
        pool_timeout=pool["pool_timeout"],
        pool_pre_ping=True,
        # #10491: command_timeout bounds pre_ping so a WSL-dropped idle
        # connection fails fast instead of hanging ~30s on the dead socket.
        connect_args={"timeout": 10, "command_timeout": 10},
        echo=False,
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
        session.info["_post_commit_cbs"] = []
        try:
            yield session
            await session.commit()
            for cb in session.info.pop("_post_commit_cbs", []):
                await cb()
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
        session.info["_post_commit_cbs"] = []
        try:
            yield session
            await session.commit()
            for cb in session.info.pop("_post_commit_cbs", []):
                await cb()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def _verify_postgres_connection() -> None:
    """Open one connection and run ``SELECT 1`` to confirm reachability and
    credentials. Raises the underlying driver error on failure (#12293)."""
    from sqlalchemy import text

    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def init_database() -> None:
    """
    Initialize the database connection and verify connectivity.

    Call this during application startup.

    Issue #12293: distinguishes a *permanent* credential / authorization
    misconfiguration (bad password, missing role, missing database) from
    *transient* unavailability (the database is still coming up). Permanent
    faults fail fast with a single loud CRITICAL diagnosis — retrying can never
    help — so a stale password no longer produces an unbounded, silent crash
    loop. Transient faults get a bounded, clearly-logged retry then give up
    with a clear signal. Both raise ``RuntimeError`` so startup aborts loudly.
    """
    logger.info("init_database() called")
    config = get_deployment_config()
    logger.info(
        "Got deployment config - postgres_enabled=%s",
        config.postgres_enabled,
    )

    if not config.postgres_enabled:
        logger.info(
            "PostgreSQL disabled for deployment mode: %s",
            config.mode.value,
        )
        return

    logger.info("PostgreSQL enabled, proceeding with initialization")
    # Password-free target string — safe to log; never interpolate the password.
    safe_target = f"{config.postgres_user}@{config.postgres_host}:{config.postgres_port}/{config.postgres_db}"

    for attempt in range(1, _DB_INIT_MAX_ATTEMPTS + 1):
        try:
            await _verify_postgres_connection()
            logger.info("PostgreSQL connection verified successfully (attempt %d)", attempt)
            return
        except Exception as e:
            if _is_permanent_db_error(e):
                logger.critical(
                    "❌ FATAL: PostgreSQL rejected the backend's credentials — permanent "
                    "misconfiguration, retrying will NOT help. Target: postgresql://%s "
                    "(asyncpg). Underlying error: %s: %s. Likely fix: the password for DB "
                    "role '%s' is stale or wrong — update the backend's POSTGRES_PASSWORD "
                    "(or its service-keys env) to match the database, then restart "
                    "(see #12293, #12297).",
                    safe_target,
                    type(e).__name__,
                    e,
                    config.postgres_user,
                )
                raise RuntimeError(
                    f"PostgreSQL credential/authorization misconfiguration for role "
                    f"'{config.postgres_user}' at {safe_target}: {type(e).__name__}"
                ) from e
            if attempt >= _DB_INIT_MAX_ATTEMPTS:
                logger.critical(
                    "❌ FATAL: PostgreSQL unreachable at %s after %d bounded attempt(s) "
                    "~%.1fs apart. Giving up with a clear signal instead of looping "
                    "silently (#12293). Last error: %s: %s. Likely fix: ensure PostgreSQL "
                    "is running and reachable, then restart.",
                    safe_target,
                    _DB_INIT_MAX_ATTEMPTS,
                    _DB_INIT_RETRY_DELAY_SECONDS,
                    type(e).__name__,
                    e,
                )
                raise RuntimeError(
                    f"PostgreSQL unreachable at {safe_target} after "
                    f"{_DB_INIT_MAX_ATTEMPTS} attempt(s): {type(e).__name__}"
                ) from e
            logger.warning(
                "PostgreSQL not ready at %s (attempt %d/%d) — transient, retrying in " "%.1fs: %s: %s",
                safe_target,
                attempt,
                _DB_INIT_MAX_ATTEMPTS,
                _DB_INIT_RETRY_DELAY_SECONDS,
                type(e).__name__,
                e,
            )
            await asyncio.sleep(_DB_INIT_RETRY_DELAY_SECONDS)


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
    except Exception:
        return {
            "status": "unhealthy",
            "mode": config.mode.value,
            "error": "Database health check failed",
        }
