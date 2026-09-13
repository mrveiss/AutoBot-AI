# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Core application-config routes: read and write the system config (#16278).

Split out of ``api/settings.py``, which sits at its frozen file-size ceiling,
so these routes could gain a gate without growing that file (the
``password_change.py`` precedent, #15743). ``settings.py`` includes this
router, so every path is unchanged: ``/api/settings/``, ``/settings``,
``/backend``, ``/config`` and ``/clear-cache``.

Every route here is admin-only (#16278). They used to carry no auth at all,
and ``/api/settings`` is in service-auth's ``EXEMPT_PATHS``, so nothing
covered them: an anonymous caller could read the full merged config and write
it, and each write was recorded as ``created_by="admin"``. The gate is a
declared dependency rather than a call in the handler body, so
``api/settings_route_posture_test.py`` can see it (#15737).
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_system import ClearCacheResponse
from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user, verify_internal_api_key
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.config_revision_service import ConfigRevisionService
from services.config_service import ConfigService
from utils.catalog_http_exceptions import raise_server_error

router = APIRouter()

logger = get_logger(__name__)

#: Revision author for a write made with the internal-service API key (#1145),
#: which ``check_admin_permission`` admits without a user behind it.
INTERNAL_SERVICE_ACTOR = "internal-service"


async def require_settings_admin(request: Request, _: bool = Depends(check_admin_permission)) -> str:
    """Admin gate for every route here; returns who a config revision records.

    ``check_admin_permission`` refuses anonymous (401) and non-admin (403)
    callers before this body runs. What reaches it is either an admin session
    or the internal-service key, and the revision names whichever it was
    instead of the literal ``"admin"`` every write used to record.
    """
    if verify_internal_api_key(request.headers.get("X-Internal-API-Key")):
        return INTERNAL_SERVICE_ACTOR
    user = await get_current_user(request)
    return user.get("username") or INTERNAL_SERVICE_ACTOR


@router.get("/", response_model=dict, dependencies=[Depends(require_settings_admin)])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_settings",
    error_code_prefix="SETTINGS",
)
async def get_settings():
    """Get application settings - now uses full config from config.yaml"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting settings: %s", str(e))
        raise_server_error("API_0003", "Error getting settings")


@router.get("/settings", response_model=dict, dependencies=[Depends(require_settings_admin)])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_settings_explicit",
    error_code_prefix="SETTINGS",
)
async def get_settings_explicit():
    """Get application settings.

    Issue #3334: Deprecated duplicate — use GET /api/settings/ instead.
    This endpoint remains for backward compatibility but will be removed in a
    future release.
    """
    logger.warning("Deprecated endpoint called: GET /api/settings/settings. " "Use GET /api/settings/ instead. (#3334)")
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting settings: %s", str(e))
        raise_server_error("API_0003", "Error getting settings")


@router.post("/", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_settings",
    error_code_prefix="SETTINGS",
)
async def save_settings(
    settings_data: dict,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_settings_admin),
):
    """Save application settings (#1747: records audit revision)."""
    try:
        if not settings_data:
            logger.warning("Received empty settings data, skipping save")
            return {"status": "skipped", "message": "No data to save"}

        before_config = ConfigService.get_full_config()
        result = ConfigService.save_full_config(settings_data)

        # Issue #1747: Record config revision
        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="settings",
            before_config=before_config,
            after_config=settings_data,
            source="api",
            created_by=actor,
        )
        return result
    except Exception as e:
        logger.error("Error saving settings: %s", str(e))
        raise_server_error("API_0003", "Error saving settings")


@router.post("/settings", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_settings_explicit",
    error_code_prefix="SETTINGS",
)
async def save_settings_explicit(
    settings_data: dict,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_settings_admin),
):
    """Save application settings.

    Issue #3334: Deprecated duplicate — use POST /api/settings/ instead.
    This endpoint remains for backward compatibility but will be removed in a
    future release.
    """
    logger.warning(
        "Deprecated endpoint called: POST /api/settings/settings. " "Use POST /api/settings/ instead. (#3334)"
    )
    try:
        if not settings_data:
            logger.warning("Received empty settings data, skipping save")
            return {"status": "skipped", "message": "No data to save"}

        before_config = ConfigService.get_full_config()
        result = ConfigService.save_full_config(settings_data)

        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="settings",
            before_config=before_config,
            after_config=settings_data,
            source="api",
            created_by=actor,
        )
        return result
    except Exception as e:
        logger.error("Error saving settings: %s", str(e))
        raise_server_error("API_0003", "Error saving settings")


@router.get("/backend", response_model=dict, dependencies=[Depends(require_settings_admin)])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_backend_settings",
    error_code_prefix="SETTINGS",
)
async def get_backend_settings():
    """Get backend-specific settings"""
    try:
        return ConfigService.get_backend_settings()
    except Exception as e:
        logger.error("Error getting backend settings: %s", str(e))
        raise_server_error("API_0003", "Error getting backend settings")


@router.post("/backend", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_backend_settings",
    error_code_prefix="SETTINGS",
)
async def save_backend_settings(
    backend_settings: dict,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_settings_admin),
):
    """Save backend-specific settings (#1747: audit trail)."""
    try:
        before_config = ConfigService.get_backend_settings()
        result = ConfigService.update_backend_settings(backend_settings)

        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="backend",
            before_config=before_config,
            after_config=backend_settings,
            source="api",
            created_by=actor,
        )
        return result
    except Exception as e:
        logger.error("Error saving backend settings: %s", str(e))
        raise_server_error("API_0003", "Error saving backend settings")


@router.get("/config", response_model=dict, dependencies=[Depends(require_settings_admin)])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_full_config",
    error_code_prefix="SETTINGS",
)
async def get_full_config():
    """Get complete application configuration"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting full config: %s", str(e))
        raise_server_error("API_0003", "Error getting full config")


@router.post("/config", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_full_config",
    error_code_prefix="SETTINGS",
)
async def save_full_config(
    config_data: dict,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_settings_admin),
):
    """Save complete application configuration (#1747: audit trail)."""
    try:
        before_config = ConfigService.get_full_config()
        result = ConfigService.save_full_config(config_data)

        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="config",
            before_config=before_config,
            after_config=config_data,
            source="api",
            created_by=actor,
        )
        return result
    except Exception as e:
        logger.error("Error saving full config: %s", str(e))
        raise_server_error("API_0003", "Error saving full config")


@router.post("/clear-cache", response_model=ClearCacheResponse, dependencies=[Depends(require_settings_admin)])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cache",
    error_code_prefix="SETTINGS",
)
async def clear_cache():
    """Clear application cache - includes config cache"""
    try:
        logger.info("Settings clear-cache endpoint called - clearing config cache")

        # Clear the ConfigService cache to force reload of settings
        ConfigService.clear_cache()

        return {
            "status": "success",
            "message": ("Configuration cache cleared. Settings will be reloaded on next request."),
            "available_endpoints": {
                "clear_all_redis": "/api/cache/redis/clear/all",
                "clear_specific_redis": "/api/cache/redis/clear/{database_name}",
                "clear_cache_type": "/api/cache/clear/{cache_type}",
            },
        }
    except Exception as e:
        logger.error("Error in clear-cache endpoint: %s", str(e))
        raise_server_error("API_0003", "Error clearing cache")
