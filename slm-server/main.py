# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Backend - Service Lifecycle Manager

Main FastAPI application entry point.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import (
    auth_router,
    blue_green_router,
    deployments_router,
    health_router,
    maintenance_router,
    monitoring_router,
    nodes_router,
    settings_router,
    stateful_router,
    updates_router,
    websocket_router,
    services_router,
    fleet_services_router,
)
from config import settings
from services.database import db_service
from services.reconciler import reconciler_service

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting SLM Backend v1.0.0")
    logger.info("Debug mode: %s", settings.debug)

    await db_service.initialize()
    await _ensure_admin_user()
    await reconciler_service.start()

    logger.info("SLM Backend ready")

    yield

    logger.info("Shutting down SLM Backend")
    await reconciler_service.stop()
    await db_service.close()


async def _ensure_admin_user():
    """Create default admin user if none exists."""
    from sqlalchemy import select

    from models.database import User
    from services.auth import auth_service

    async with db_service.session() as db:
        result = await db.execute(select(User).where(User.is_admin == True))
        if result.scalar_one_or_none():
            return

        admin_user = User(
            username="admin",
            password_hash=auth_service.hash_password("admin"),
            is_admin=True,
        )
        db.add(admin_user)
        await db.commit()
        logger.warning("Created default admin user (username: admin, password: admin)")
        logger.warning("CHANGE THE DEFAULT PASSWORD IMMEDIATELY!")


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
app.include_router(websocket_router, prefix="/api")


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
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
