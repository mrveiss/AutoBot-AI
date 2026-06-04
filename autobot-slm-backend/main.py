# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Backend - Service Lifecycle Manager

Main FastAPI application entry point.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import (
    agents_router,
    api_keys_router,
    auth_router,
    autobot_teams_router,
    autobot_users_router,
    blue_green_router,
    browser_router,
    code_sync_router,
    config_router,
    deployments_router,
    discovery_router,
    errors_router,
    events_router,
    external_agents_router,
    fleet_services_router,
    health_router,
    infrastructure_router,
    llm_config_router,
    maintenance_router,
    mfa_router,
    monitoring_router,
    node_config_router,
    node_rdp_router,
    node_tls_router,
    node_vnc_router,
    nodes_execution_router,
    nodes_router,
    npu_router,
    orchestration_router,
    rdp_router,
    secrets_router,
    security_router,
    services_router,
    settings_router,
    setup_wizard_router,
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
from api.personality_proxy import router as personality_proxy_router
from api.roles import router as roles_router
from api.voice_proxy import router as voice_proxy_router
from config import settings
from middleware import SecurityHeadersMiddleware
from services.a2a_card_fetcher import start_card_refresh_task
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


def _check_tablename_collisions() -> None:
    """Detect shared tablenames across both SQLAlchemy Base MetaData objects (#1878).

    Delegates to :func:`autobot_shared.tablename_validator.check_tablename_collisions`
    after resolving the two application-specific ``MetaData`` objects.  The heavy
    detection + logging logic lives in autobot_shared so it can be tested in
    isolation without importing this module's full dependency tree (#2413).
    """
    # Import after path is set up so this function is safe to call early in lifespan.
    import user_management.models  # noqa: F401 — registers all UM models with UMBase
    from autobot_shared.tablename_validator import check_tablename_collisions
    from models.database import Base as SLMBase
    from user_management.models.base import Base as UMBase

    check_tablename_collisions(SLMBase.metadata, UMBase.metadata)


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
        logger.info("Starting database migrations")
        results = await run_migrations_async()
        for name, success, message in results:
            if success:
                logger.info("Migration: %s", message)
            else:
                logger.error("Migration failed: %s", message)
                raise RuntimeError(f"Migration failed: {name}")
        if results:
            logger.info("Applied %d migration(s)", len(results))
        else:
            logger.info("All migrations already applied")
    except Exception as e:
        logger.error("Migration error: %s", e, exc_info=True)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Reconfigure root logger AFTER uvicorn's setup so application
    # logs (code_sync, git_tracker, etc.) are visible in service logs.
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logger.info("Starting SLM Backend v1.0.0")
    logger.info("Debug mode: %s", settings.debug)

    # Validate that the two Base MetaData objects share no tablenames (#1878).
    # Must run before create_all / migrations so conflicts are caught immediately.
    try:
        logger.info("Checking for table name collisions")
        _check_tablename_collisions()
        logger.info("Table collision check passed")
    except Exception as e:
        logger.error("Table collision check failed: %s", e, exc_info=True)
        raise

    # Create base tables first, then apply incremental migrations
    try:
        logger.info("Initializing database connection")
        await db_service.initialize()
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database initialization failed: %s", e, exc_info=True)
        raise

    try:
        logger.info("Initializing user management tables")
        await _init_user_management_tables()
        logger.info("User management tables initialized")
    except Exception as e:
        logger.error("User management table initialization failed: %s", e, exc_info=True)
        raise

    try:
        await _run_migrations()
    except Exception:
        logger.error("Database migrations failed during startup", exc_info=True)
        raise

    try:
        await _ensure_admin_user()
        await _seed_default_roles()
        await _seed_default_agents()
        await _ensure_local_node()
    except Exception as e:
        logger.error("Data seeding failed: %s", e, exc_info=True)
        raise

    # Reconcile stale fleet sync jobs from prior crash (#1729)
    try:
        from api.code_sync import reconcile_stale_fleet_sync_jobs

        reconciled = await reconcile_stale_fleet_sync_jobs()
        if reconciled:
            logger.warning("Reconciled %d stale fleet sync job(s)", reconciled)
    except Exception:
        logger.exception("Failed to reconcile stale fleet sync jobs")

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

    # Start A2A card refresh background task (Issue #962)
    a2a_card_task = start_card_refresh_task()
    logger.info("A2A card refresh task started")

    logger.info("SLM Backend ready")

    yield

    logger.info("Shutting down SLM Backend")
    version_checker_task.cancel()
    a2a_card_task.cancel()
    try:
        await version_checker_task
    except asyncio.CancelledError:
        logger.info("Version checker stopped")
    try:
        await a2a_card_task
    except asyncio.CancelledError:
        logger.info("A2A card refresh task stopped")
    stop_schedule_executor()
    logger.info("Schedule executor stopped")
    await reconciler_service.stop()
    await db_service.close()


async def _ensure_local_node() -> None:
    """Self-register the SLM manager node on startup if not already in the DB.

    install.sh's register_local_node() is the primary registration path, but it
    can be silently skipped when HTTPS is not ready in time (e.g. nginx cert path
    issues on a fresh install).  This function is an idempotent fallback that runs
    every startup so the node is always present regardless of install.sh outcome.

    Also self-heals a stale IP: if slm-secrets.env was corrected after a reinstall
    picked the wrong interface (#3194), the next backend restart updates the DB
    record to match the current SLM_EXTERNAL_URL.
    """
    import re
    import socket

    from sqlalchemy import select

    from models.database import Node, NodeRole, NodeStatus

    _SLM_NODE_ID = "00-SLM-Manager"
    _SLM_ROLES = ["slm-backend", "slm-frontend", "slm-database", "slm-monitoring"]

    # Derive IP from SLM_EXTERNAL_URL (written by install.sh) or fall back to probe.
    external_url = os.getenv("SLM_EXTERNAL_URL", "")
    ip_match = re.search(r"https?://([^/:]+)", external_url)
    if ip_match:
        local_ip = ip_match.group(1)
    else:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                local_ip = sock.getsockname()[0]
        except OSError:
            local_ip = "127.0.0.1"

    hostname = socket.gethostname()

    async with db_service.session() as session:
        existing = (await session.execute(select(Node).where(Node.node_id == _SLM_NODE_ID))).scalar_one_or_none()

        if existing:
            # Heal stale IP — happens when slm-secrets.env has a wrong IP from
            # a previous install (e.g. wrong interface selected) and was corrected.
            if existing.ip_address != local_ip:
                logger.info(
                    "Updating SLM manager IP: %s -> %s (slm-secrets.env changed)",
                    existing.ip_address,
                    local_ip,
                )
                existing.ip_address = local_ip
                await session.commit()
            return

        node = Node(
            node_id=_SLM_NODE_ID,
            ansible_name=_SLM_NODE_ID,
            hostname=hostname,
            ip_address=local_ip,
            ssh_user="autobot",
            ssh_port=22,
            auth_method="key",
            status=NodeStatus.ONLINE.value,
            roles=_SLM_ROLES,
        )
        session.add(node)
        for role_name in _SLM_ROLES:
            session.add(
                NodeRole(
                    node_id=_SLM_NODE_ID,
                    role_name=role_name,
                    status="active",
                    assignment_type="auto",
                )
            )
        await session.commit()
        logger.info("Auto-registered SLM manager node (%s / %s)", hostname, local_ip)


async def _ensure_admin_user():
    """Create or sync the admin user.

    When SLM_ADMIN_PASSWORD is set (Ansible-managed), ensures the
    admin password always matches. This makes the secrets file the
    single source of truth for the admin credential.

    Uses the user_management UserService and slm_users database (Issue #1900).
    """
    import os
    import secrets

    from services.auth import auth_service
    from user_management.database import get_slm_session
    from user_management.services import TenantContext, UserService
    from user_management.services.user_service import DuplicateUserError

    env_password = os.getenv("SLM_ADMIN_PASSWORD", "")

    async with get_slm_session() as db:
        context = TenantContext(is_platform_admin=True)
        user_service = UserService(db, context)

        existing = await user_service.get_user_by_username("admin")

        if existing:
            if env_password:
                existing.password_hash = auth_service.hash_password(env_password)
                await db.flush()
                logger.info("Admin password synced from SLM_ADMIN_PASSWORD")
            return

        password = env_password
        if not password:
            password = secrets.token_urlsafe(16)
            logger.critical("Initial admin password set — CHANGE IMMEDIATELY")

        try:
            await user_service.create_user(
                email="admin@slm.local",
                username="admin",
                password=password,
                display_name="SLM Admin",
                is_platform_admin=True,
            )
            logger.warning("Created default admin user (username: admin)")
        except DuplicateUserError:
            logger.info("Admin user already exists (race condition avoided)")


async def _seed_default_roles():
    """Seed default roles if they don't exist (Issue #779)."""
    from services.role_registry import seed_default_roles

    async with db_service.session() as db:
        created = await seed_default_roles(db)
        if created > 0:
            logger.info("Seeded %d default roles", created)


async def _seed_default_agents():
    """Seed all 29 AutoBot agents if the agents table is empty (Issue #939)."""
    from services.agent_seeder import seed_default_agents

    async with db_service.session() as db:
        created = await seed_default_agents(db)
        if created > 0:
            logger.info("Seeded %d default agents", created)


app = FastAPI(
    title="SLM Backend",
    description="Service Lifecycle Manager for AutoBot",
    version="1.0.0",
    lifespan=lifespan,
    root_path=os.getenv("SLM_ROOT_PATH", ""),
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
# Issue #2858 — explicit CSRF mitigation + security headers.
# Registered after CORSMiddleware so CORS headers are already present.
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(health_router, prefix="/api")
app.include_router(browser_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(nodes_router, prefix="/api")
app.include_router(nodes_execution_router, prefix="/api")  # Issue #3406
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
app.include_router(events_router, prefix="/api")
app.include_router(external_agents_router, prefix="/api")
app.include_router(websocket_router, prefix="/api")
app.include_router(node_rdp_router, prefix="/api")
app.include_router(rdp_router, prefix="/api")
app.include_router(node_vnc_router, prefix="/api")
app.include_router(vnc_router, prefix="/api")
app.include_router(node_tls_router, prefix="/api")
app.include_router(tls_router, prefix="/api")
app.include_router(secrets_router, prefix="/api")
app.include_router(security_router, prefix="/api")
app.include_router(code_sync_router, prefix="/api")
app.include_router(roles_router, prefix="/api")
app.include_router(code_source_router, prefix="/api")
app.include_router(personality_proxy_router, prefix="/api")  # Issue #1145
app.include_router(voice_proxy_router, prefix="/api")  # Voice proxy for personality voice assignment
app.include_router(orchestration_router, prefix="/api")
app.include_router(discovery_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(node_config_router, prefix="/api/nodes")
app.include_router(npu_router, prefix="/api")
# Issue #786: Infrastructure setup playbooks
app.include_router(infrastructure_router, prefix="/api")
# User Management routers (Issue #576)
app.include_router(slm_users_router, prefix="/api")
app.include_router(autobot_users_router, prefix="/api")
app.include_router(autobot_teams_router, prefix="/api")
# SSO Integration (Issue #576 Phase 4)
app.include_router(sso_router, prefix="/api")
app.include_router(sso_auth_router, prefix="/api")
# MFA and API Keys (Issue #576 Phase 5)
app.include_router(mfa_router, prefix="/api")
app.include_router(api_keys_router, prefix="/api")
# Setup Wizard (Issue #1294)
app.include_router(setup_wizard_router, prefix="/api")
# LLM Configuration (Issue #2371)
app.include_router(llm_config_router, prefix="/api")


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
