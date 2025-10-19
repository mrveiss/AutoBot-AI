import logging
from fastapi import APIRouter, HTTPException
from backend.services.config_service import ConfigService
from src.constants.network_constants import NetworkConstants

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/frontend-config")
async def get_frontend_config():
    """Get frontend-specific configuration"""
    try:
        # Get the full config and extract frontend-relevant settings
        full_config = ConfigService.get_full_config()

        # Get backend config from unified config manager for defaults
        from src.unified_config_manager import unified_config_manager

        backend_config = unified_config_manager.get_backend_config()

        # Extract frontend-relevant configuration
        frontend_config = {
            "api": {
                "base_url": full_config.get("backend", {}).get(
                    "host", backend_config.get("host")
                ),
                "port": full_config.get("backend", {}).get(
                    "port", backend_config.get("port")
                ),
                "timeout": full_config.get("api", {}).get("timeout", 30),
                "retry_attempts": full_config.get("api", {}).get("retry_attempts", 3),
            },
            "websocket": {
                "url": f"ws://{full_config.get('backend', {}).get('host', backend_config.get('host'))}:{full_config.get('backend', {}).get('port', backend_config.get('port'))}/ws",
                "reconnect_attempts": full_config.get("websocket", {}).get(
                    "reconnect_attempts", 5
                ),
                "reconnect_delay": full_config.get("websocket", {}).get(
                    "reconnect_delay", 1000
                ),
            },
            "features": {
                "chat_enabled": full_config.get("features", {}).get(
                    "chat_enabled", True
                ),
                "knowledge_base_enabled": full_config.get("features", {}).get(
                    "knowledge_base_enabled", True
                ),
                "terminal_enabled": full_config.get("features", {}).get(
                    "terminal_enabled", True
                ),
                "desktop_enabled": full_config.get("features", {}).get(
                    "desktop_enabled", True
                ),
                "system_monitoring_enabled": full_config.get("features", {}).get(
                    "system_monitoring_enabled", True
                ),
            },
            "ui": {
                "theme": full_config.get("ui", {}).get("theme", "light"),
                "language": full_config.get("ui", {}).get("language", "en"),
                "auto_scroll": full_config.get("ui", {}).get("auto_scroll", True),
                "notifications": full_config.get("ui", {}).get("notifications", True),
            },
            "performance": {
                "cache_enabled": full_config.get("performance", {}).get(
                    "cache_enabled", True
                ),
                "lazy_loading": full_config.get("performance", {}).get(
                    "lazy_loading", True
                ),
                "chunk_loading": full_config.get("performance", {}).get(
                    "chunk_loading", True
                ),
            },
        }

        logger.info("Frontend configuration provided successfully")
        return frontend_config

    except Exception as e:
        logger.error(f"Error getting frontend config: {str(e)}")
        # Return minimal default config from unified config manager instead of failing
        from src.unified_config_manager import unified_config_manager

        backend_config = unified_config_manager.get_backend_config()

        # Get defaults from config manager
        api_config = unified_config_manager.get_config_section("api") or {}
        websocket_config = unified_config_manager.get_config_section("websocket") or {}
        features_config = unified_config_manager.get_config_section("features") or {}
        ui_config = unified_config_manager.get_config_section("ui") or {}
        performance_config = (
            unified_config_manager.get_config_section("performance") or {}
        )

        default_config = {
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
            "features": {
                "chat_enabled": features_config.get("chat_enabled", True),
                "knowledge_base_enabled": features_config.get(
                    "knowledge_base_enabled", True
                ),
                "terminal_enabled": features_config.get("terminal_enabled", True),
                "desktop_enabled": features_config.get("desktop_enabled", True),
                "system_monitoring_enabled": features_config.get(
                    "system_monitoring_enabled", True
                ),
            },
            "ui": {
                "theme": ui_config.get("theme", "light"),
                "language": ui_config.get("language", "en"),
                "auto_scroll": ui_config.get("auto_scroll", True),
                "notifications": ui_config.get("notifications", True),
            },
            "performance": {
                "cache_enabled": performance_config.get("cache_enabled", True),
                "lazy_loading": performance_config.get("lazy_loading", True),
                "chunk_loading": performance_config.get("chunk_loading", True),
            },
        }
        logger.warning(f"Returning default frontend config due to error: {str(e)}")
        return default_config
