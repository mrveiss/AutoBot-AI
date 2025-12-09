# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import logging
from typing import Any, Dict

from fastapi import APIRouter

from backend.services.config_service import ConfigService
from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PathConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_project_config() -> Dict[str, Any]:
    """
    Build static project configuration section.

    Issue #281: Extracted helper for project config.
    """
    return {
        "root_path": str(PathConstants.PROJECT_ROOT),
        "name": "AutoBot",
        "version": "1.5.0",
    }


def _build_features_config(source: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build features configuration section from any config source.

    Issue #281: Extracted helper for features config.

    Args:
        source: Config dict (either full_config.get("features", {}) or features section)
    """
    return {
        "chat_enabled": source.get("chat_enabled", True),
        "knowledge_base_enabled": source.get("knowledge_base_enabled", True),
        "terminal_enabled": source.get("terminal_enabled", True),
        "desktop_enabled": source.get("desktop_enabled", True),
        "system_monitoring_enabled": source.get("system_monitoring_enabled", True),
    }


def _build_ui_config(source: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build UI configuration section from any config source.

    Issue #281: Extracted helper for UI config.

    Args:
        source: Config dict (either full_config.get("ui", {}) or ui section)
    """
    return {
        "theme": source.get("theme", "light"),
        "language": source.get("language", "en"),
        "auto_scroll": source.get("auto_scroll", True),
        "notifications": source.get("notifications", True),
    }


def _build_performance_config(source: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build performance configuration section from any config source.

    Issue #281: Extracted helper for performance config.

    Args:
        source: Config dict (either full_config.get("performance", {}) or performance section)
    """
    return {
        "cache_enabled": source.get("cache_enabled", True),
        "lazy_loading": source.get("lazy_loading", True),
        "chunk_loading": source.get("chunk_loading", True),
    }


def _build_fallback_config() -> Dict[str, Any]:
    """
    Build fallback frontend config when primary config fails.

    Issue #281: Extracted helper for fallback config building.

    Returns:
        Complete fallback frontend configuration dict
    """
    from src.unified_config_manager import unified_config_manager

    backend_config = unified_config_manager.get_backend_config()

    # Get defaults from config manager
    api_config = unified_config_manager.get_config_section("api") or {}
    websocket_config = unified_config_manager.get_config_section("websocket") or {}
    features_config = unified_config_manager.get_config_section("features") or {}
    ui_config = unified_config_manager.get_config_section("ui") or {}
    performance_config = unified_config_manager.get_config_section("performance") or {}

    return {
        "project": _build_project_config(),
        "api": {
            "base_url": backend_config.get("host"),
            "port": backend_config.get("port"),
            "timeout": api_config.get("timeout", 30),
            "retry_attempts": api_config.get("retry_attempts", 3),
        },
        "websocket": {
            "url": f"ws://{backend_config.get('host')}:{backend_config.get('port')}/ws",
            "reconnect_attempts": websocket_config.get("reconnect_attempts", 5),
            "reconnect_delay": websocket_config.get("reconnect_delay", 1000),
        },
        "features": _build_features_config(features_config),
        "ui": _build_ui_config(ui_config),
        "performance": _build_performance_config(performance_config),
        # Issue #372: Use NetworkConstants method for host configs
        "hosts": NetworkConstants.get_host_configs(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_frontend_config",
    error_code_prefix="FRONTEND_CONFIG",
)
@router.get("/frontend-config")
async def get_frontend_config():
    """
    Get frontend-specific configuration.

    Issue #281: Refactored from 139 lines to use extracted helper methods.
    """
    try:
        # Get the full config and extract frontend-relevant settings
        full_config = ConfigService.get_full_config()

        # Extract frontend-relevant configuration using NetworkConstants methods
        # and extracted helpers (Issue #281, Issue #372)
        api_config = NetworkConstants.get_api_config()
        frontend_config = {
            "project": _build_project_config(),
            "api": {
                **api_config,
                "timeout": full_config.get("api", {}).get("timeout", 30),
                "retry_attempts": full_config.get("api", {}).get("retry_attempts", 3),
            },
            "websocket": {
                "url": NetworkConstants.get_websocket_url(),
                "reconnect_attempts": full_config.get("websocket", {}).get(
                    "reconnect_attempts", 5
                ),
                "reconnect_delay": full_config.get("websocket", {}).get(
                    "reconnect_delay", 1000
                ),
            },
            "features": _build_features_config(full_config.get("features", {})),
            "ui": _build_ui_config(full_config.get("ui", {})),
            "performance": _build_performance_config(full_config.get("performance", {})),
            # Issue #372: Use NetworkConstants method for host configs
            "hosts": NetworkConstants.get_host_configs(),
        }

        logger.info("Frontend configuration provided successfully")
        return frontend_config

    except Exception as e:
        logger.error(f"Error getting frontend config: {str(e)}")
        # Return fallback config (Issue #281: uses extracted helper)
        logger.warning(f"Returning default frontend config due to error: {str(e)}")
        return _build_fallback_config()
