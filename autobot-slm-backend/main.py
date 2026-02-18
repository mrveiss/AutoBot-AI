# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Backend - Service Lifecycle Manager

Main FastAPI application entry point.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from api import (
    agents_router,
    api_keys_router,
    auth_router,
    autobot_teams_router,
    autobot_users_router,
    blue_green_router,
    code_sync_router,
    config_router,
    deployments_router,
    discovery_router,
    errors_router,
    fleet_services_router,
    health_router,
    infrastructure_router,
    maintenance_router,
    mfa_router,
    monitoring_router,
    node_config_router,
    node_tls_router,
    node_vnc_router,
    nodes_router,
    npu_router,
    orchestration_router,
    security_router,
    services_router,
    settings_router,
    slm_auth_router,
    slm_users_router,
    sso_auth_router,
    sso_router,
    stateful_router,
    tls_router,
    updates_router,
    vnc_router,
    websocket_router,
)
from api.code_source import router as code_source_router
from api.performance import router as performance_router
from api.roles import router as roles_router
from config import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.database import db_service
from services.git_tracker import start_version_checker
from services.reconciler import reconciler_service
from services.schedule_executor import start_schedule_executor, stop_schedule_executor

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def _init_user_management_tables() -> None:
    """Create user management tables (SSO, organizations, users, etc.) (#921).

    The user_management models use a separate Base and engine from the main
    SLM backend.  Without this call the sso_providers table (and others)
    would not exist, causing 502 errors on /api/auth/sso/providers.
    """
    try:
        # Import all models so they register with the Base metadata
        import user_management.models  # noqa: F401  (registers all UM models)
        from user_management.database import get_slm_engine
        from user_management.models.base import Base as UMBase

        engine = get_slm_engine()
        async with engine.begin() as conn:
            await conn.run_sync(UMBase.metadata.create_all)
        logger.info("User management tables initialised")
    except Exception as exc:
        logger.error("User management table init failed: %s", exc)
        raise


async def _run_migrations():
    """Run pending database migrations on startup."""
    from migrations.runner import run_migrations_async

    try:
        results = await run_migrations_async()
        for name, success, message in results:
            if success:
                logger.info("Migration: %s", message)
            else:
                logger.error("Migration failed: %s", message)
                raise RuntimeError(f"Migration failed: {name}")
        if results:
            logger.info("Applied %d migration(s)", len(results))
    except Exception as e:
        logger.error("Migration error: %s", e)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting SLM Backend v1.0.0")
    logger.info("Debug mode: %s", settings.debug)

    # Create base tables first, then apply incremental migrations
    await db_service.initialize()
    await _init_user_management_tables()
    await _run_migrations()
    await _ensure_admin_user()
    await _seed_default_roles()

    # Initialize manifest loader singleton (Issue #926 Phase 3)
    from services.manifest_loader import init_manifest_loader

    init_manifest_loader()

    await reconciler_service.start()

    # Start version checker background task (Issue #741)
    version_checker_task = start_version_checker()
    logger.info("Version checker started")

    # Start schedule executor background task (Issue #741 - Phase 7)
    start_schedule_executor()
    logger.info("Schedule executor started")

    logger.info("SLM Backend ready")

    yield

    logger.info("Shutting down SLM Backend")
    version_checker_task.cancel()
    try:
        await version_checker_task
    except asyncio.CancelledError:
        logger.info("Version checker stopped")
    stop_schedule_executor()
    logger.info("Schedule executor stopped")
    await reconciler_service.stop()
    await db_service.close()


async def _ensure_admin_user():
    """Create or sync the admin user.

    When SLM_ADMIN_PASSWORD is set (Ansible-managed), ensures the
    admin password always matches. This makes the secrets file the
    single source of truth for the admin credential.
    """
    import os
    import secrets

    from models.database import User
    from services.auth import auth_service
    from sqlalchemy import select

    env_password = os.getenv("SLM_ADMIN_PASSWORD", "")

    async with db_service.session() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        existing = result.scalar_one_or_none()

        if existing:
            if env_password:
                existing.password_hash = auth_service.hash_password(env_password)
                await db.commit()
                logger.info("Admin password synced from SLM_ADMIN_PASSWORD")
            return

        password = env_password
        if not password:
            password = secrets.token_urlsafe(16)
            logger.critical(
                "Initial admin password: %s — CHANGE IMMEDIATELY",
                password,
            )

        admin_user = User(
            username="admin",
            password_hash=auth_service.hash_password(password),
            is_admin=True,
        )
        db.add(admin_user)
        await db.commit()
        logger.warning("Created default admin user (username: admin)")


async def _seed_default_roles():
    """Seed default roles if they don't exist (Issue #779)."""
    from services.role_registry import seed_default_roles

    async with db_service.session() as db:
        created = await seed_default_roles(db)
        if created > 0:
            logger.info("Seeded %d default roles", created)


app = FastAPI(
    title="SLM Backend",
    description="Service Lifecycle Manager for AutoBot",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(nodes_router, prefix="/api")
app.include_router(services_router, prefix="/api")
app.include_router(fleet_services_router, prefix="/api")
app.include_router(deployments_router, prefix="/api")
app.include_router(blue_green_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(stateful_router, prefix="/api")
app.include_router(updates_router, prefix="/api")
app.include_router(maintenance_router, prefix="/api")
app.include_router(monitoring_router, prefix="/api")
app.include_router(performance_router, prefix="/api")
app.include_router(errors_router, prefix="/api")
app.include_router(websocket_router, prefix="/api")
app.include_router(node_vnc_router, prefix="/api")
app.include_router(vnc_router, prefix="/api")
app.include_router(node_tls_router, prefix="/api")
app.include_router(tls_router, prefix="/api")
app.include_router(security_router, prefix="/api")
app.include_router(code_sync_router, prefix="/api")
app.include_router(roles_router, prefix="/api")
app.include_router(code_source_router, prefix="/api")
app.include_router(orchestration_router, prefix="/api")
app.include_router(discovery_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(node_config_router, prefix="/api/nodes")
app.include_router(npu_router, prefix="/api")
# Issue #786: Infrastructure setup playbooks
app.include_router(infrastructure_router, prefix="/api")
# User Management routers (Issue #576)
app.include_router(slm_users_router, prefix="/api")
app.include_router(slm_auth_router, prefix="/api")
app.include_router(autobot_users_router, prefix="/api")
app.include_router(autobot_teams_router, prefix="/api")
# SSO Integration (Issue #576 Phase 4)
app.include_router(sso_router, prefix="/api")
app.include_router(sso_auth_router, prefix="/api")
# MFA and API Keys (Issue #576 Phase 5)
app.include_router(mfa_router, prefix="/api")
app.include_router(api_keys_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint redirect to API docs or status."""
    return {
        "name": "SLM Backend",
        "version": "1.0.0",
        "status": "running",
        "docs": "/api/docs" if settings.debug else "disabled",
    }


if __name__ == "__main__":
    import os

    import uvicorn

    # TLS Configuration - Issue #725 Phase 5
    tls_enabled = os.getenv("SLM_TLS_ENABLED", "false").lower() == "true"
    ssl_keyfile = None
    ssl_certfile = None
    port = settings.port

    if tls_enabled:
        cert_dir = os.getenv("AUTOBOT_TLS_CERT_DIR", "/etc/autobot/certs")
        ssl_keyfile = os.path.join(cert_dir, "server-key.pem")
        ssl_certfile = os.path.join(cert_dir, "server-cert.pem")
        port = int(os.getenv("SLM_TLS_PORT", "8443"))
        logger.info("TLS enabled - using HTTPS on port %s", port)

    uvicorn_config = {
        "app": "main:app",
        "host": settings.host,
        "port": port,
        "reload": settings.debug,
        "log_level": "debug" if settings.debug else "info",
    }

    if tls_enabled and ssl_keyfile and ssl_certfile:
        uvicorn_config["ssl_keyfile"] = ssl_keyfile
        uvicorn_config["ssl_certfile"] = ssl_certfile

    uvicorn.run(**uvicorn_config)
