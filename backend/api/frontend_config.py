import logging
from fastapi import APIRouter, HTTPException
from backend.services.config_service import ConfigService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/frontend-config")
async def get_frontend_config():
    """Get frontend-specific configuration"""
    try:
        # Get the full config and extract frontend-relevant settings
        full_config = ConfigService.get_full_config()

        # Extract frontend-relevant configuration
        frontend_config = {
            "api": {
                "base_url": full_config.get("backend", {}).get("host", "172.16.168.20"),
                "port": full_config.get("backend", {}).get("port", 8001),
                "timeout": full_config.get("api", {}).get("timeout", 30),
                "retry_attempts": full_config.get("api", {}).get("retry_attempts", 3)
            },
            "websocket": {
                "url": f"ws://{full_config.get('backend', {}).get('host', '172.16.168.20')}:{full_config.get('backend', {}).get('port', 8001)}/ws",
                "reconnect_attempts": full_config.get("websocket", {}).get("reconnect_attempts", 5),
                "reconnect_delay": full_config.get("websocket", {}).get("reconnect_delay", 1000)
            },
            "features": {
                "chat_enabled": full_config.get("features", {}).get("chat_enabled", True),
                "knowledge_base_enabled": full_config.get("features", {}).get("knowledge_base_enabled", True),
                "terminal_enabled": full_config.get("features", {}).get("terminal_enabled", True),
                "desktop_enabled": full_config.get("features", {}).get("desktop_enabled", True),
                "system_monitoring_enabled": full_config.get("features", {}).get("system_monitoring_enabled", True)
            },
            "ui": {
                "theme": full_config.get("ui", {}).get("theme", "light"),
                "language": full_config.get("ui", {}).get("language", "en"),
                "auto_scroll": full_config.get("ui", {}).get("auto_scroll", True),
                "notifications": full_config.get("ui", {}).get("notifications", True)
            },
            "performance": {
                "cache_enabled": full_config.get("performance", {}).get("cache_enabled", True),
                "lazy_loading": full_config.get("performance", {}).get("lazy_loading", True),
                "chunk_loading": full_config.get("performance", {}).get("chunk_loading", True)
            }
        }

        logger.info("Frontend configuration provided successfully")
        return frontend_config

    except Exception as e:
        logger.error(f"Error getting frontend config: {str(e)}")
        # Return minimal default config instead of failing
        default_config = {
            "api": {
                "base_url": "172.16.168.20",
                "port": 8001,
                "timeout": 30,
                "retry_attempts": 3
            },
            "websocket": {
                "url": "ws://172.16.168.20:8001/ws",
                "reconnect_attempts": 5,
                "reconnect_delay": 1000
            },
            "features": {
                "chat_enabled": True,
                "knowledge_base_enabled": True,
                "terminal_enabled": True,
                "desktop_enabled": True,
                "system_monitoring_enabled": True
            },
            "ui": {
                "theme": "light",
                "language": "en",
                "auto_scroll": True,
                "notifications": True
            },
            "performance": {
                "cache_enabled": True,
                "lazy_loading": True,
                "chunk_loading": True
            }
        }
        logger.warning(f"Returning default frontend config due to error: {str(e)}")
        return default_config