# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin Manager API

FastAPI endpoints for managing plugins at runtime.

Issue #730 - Plugin SDK for extensible tool architecture.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException, status
from plugin_sdk.base import PluginRegistry
from plugin_sdk.loader import PluginLoader
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import with_error_handling
from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Global plugin loader instance
_plugin_loader: Optional[PluginLoader] = None


def get_plugin_loader() -> PluginLoader:
    """Get or create plugin loader instance."""
    global _plugin_loader
    if _plugin_loader is None:
        # Define plugin directories
        plugin_dirs = [
            Path("/opt/autobot/plugins/core-plugins"),
            Path("/opt/autobot/plugins/community-plugins"),
            # Development fallback
            Path("plugins/core-plugins"),
            Path("plugins/community-plugins"),
        ]
        _plugin_loader = PluginLoader(plugin_dirs)
    return _plugin_loader


class PluginConfigUpdate(BaseModel):
    """Plugin configuration update request."""

    config: Dict = Field(..., description="Plugin configuration")


class PluginListResponse(BaseModel):
    """List of plugins response."""

    plugins: List[Dict] = Field(..., description="Plugin information list")
    total: int = Field(..., description="Total plugin count")


@router.get("/plugins")
@with_error_handling(error_code_prefix="PLUGIN_LIST")
async def list_plugins(
    admin_check: bool = Depends(check_admin_permission),
) -> PluginListResponse:
    """
    List all loaded plugins.

    Returns:
        List of plugins with their status
    """
    loader = get_plugin_loader()
    plugins = loader.get_loaded_plugins()

    plugin_list = [plugin.get_info() for plugin in plugins.values()]

    return PluginListResponse(plugins=plugin_list, total=len(plugin_list))


@router.get("/plugins/discover")
@with_error_handling(error_code_prefix="PLUGIN_DISCOVER")
async def discover_plugins(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, List[Dict]]:
    """
    Discover available plugins from filesystem.

    Returns:
        List of discovered plugin manifests
    """
    loader = get_plugin_loader()
    manifests = loader.discover_plugins()

    return {
        "discovered": [manifest.model_dump() for manifest in manifests],
        "count": len(manifests),
    }


@router.post("/plugins/{plugin_name}/load")
@with_error_handling(error_code_prefix="PLUGIN_LOAD")
async def load_plugin(
    plugin_name: str,
    config: Optional[PluginConfigUpdate] = None,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Load a plugin.

    Args:
        plugin_name: Plugin name
        config: Optional plugin configuration

    Returns:
        Success message
    """
    loader = get_plugin_loader()

    # Discover plugin manifest
    manifests = loader.discover_plugins()
    manifest = next((m for m in manifests if m.name == plugin_name), None)

    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    # Load plugin
    plugin_config = config.config if config else {}
    plugin = await loader.load_plugin(manifest, plugin_config)

    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load plugin: {plugin_name}",
        )

    # Save config to Redis
    if plugin_config:
        await _save_plugin_config(plugin_name, plugin_config)

    return {
        "status": "success",
        "message": f"Plugin {plugin_name} loaded successfully",
    }


@router.post("/plugins/{plugin_name}/unload")
@with_error_handling(error_code_prefix="PLUGIN_UNLOAD")
async def unload_plugin(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Unload a plugin.

    Args:
        plugin_name: Plugin name

    Returns:
        Success message
    """
    loader = get_plugin_loader()

    success = await loader.unload_plugin(plugin_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    return {
        "status": "success",
        "message": f"Plugin {plugin_name} unloaded successfully",
    }


@router.post("/plugins/{plugin_name}/reload")
@with_error_handling(error_code_prefix="PLUGIN_RELOAD")
async def reload_plugin(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Reload a plugin.

    Args:
        plugin_name: Plugin name

    Returns:
        Success message
    """
    loader = get_plugin_loader()

    success = await loader.reload_plugin(plugin_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    return {
        "status": "success",
        "message": f"Plugin {plugin_name} reloaded successfully",
    }


@router.post("/plugins/{plugin_name}/enable")
@with_error_handling(error_code_prefix="PLUGIN_ENABLE")
async def enable_plugin(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Enable a plugin.

    Args:
        plugin_name: Plugin name

    Returns:
        Success message
    """
    registry = PluginRegistry()
    plugin = registry.get_plugin(plugin_name)

    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    await plugin.enable()

    return {
        "status": "success",
        "message": f"Plugin {plugin_name} enabled successfully",
    }


@router.post("/plugins/{plugin_name}/disable")
@with_error_handling(error_code_prefix="PLUGIN_DISABLE")
async def disable_plugin(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Disable a plugin.

    Args:
        plugin_name: Plugin name

    Returns:
        Success message
    """
    registry = PluginRegistry()
    plugin = registry.get_plugin(plugin_name)

    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    await plugin.disable()

    return {
        "status": "success",
        "message": f"Plugin {plugin_name} disabled successfully",
    }


@router.get("/plugins/{plugin_name}")
@with_error_handling(error_code_prefix="PLUGIN_GET")
async def get_plugin_info(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict:
    """
    Get plugin information.

    Args:
        plugin_name: Plugin name

    Returns:
        Plugin information
    """
    loader = get_plugin_loader()
    info = loader.get_plugin_info(plugin_name)

    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    return info


@router.get("/plugins/{plugin_name}/config")
@with_error_handling(error_code_prefix="PLUGIN_CONFIG_GET")
async def get_plugin_config(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict:
    """
    Get plugin configuration.

    Args:
        plugin_name: Plugin name

    Returns:
        Plugin configuration
    """
    config = await _load_plugin_config(plugin_name)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No configuration found for plugin: {plugin_name}",
        )

    return config


@router.put("/plugins/{plugin_name}/config")
@with_error_handling(error_code_prefix="PLUGIN_CONFIG_UPDATE")
async def update_plugin_config(
    plugin_name: str,
    config_update: PluginConfigUpdate,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Update plugin configuration.

    Args:
        plugin_name: Plugin name
        config_update: New configuration

    Returns:
        Success message
    """
    registry = PluginRegistry()
    plugin = registry.get_plugin(plugin_name)

    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    # Update plugin config
    plugin.config = config_update.config

    # Save to Redis
    await _save_plugin_config(plugin_name, config_update.config)

    return {
        "status": "success",
        "message": f"Configuration updated for plugin: {plugin_name}",
    }


async def _save_plugin_config(plugin_name: str, config: Dict) -> None:
    """Save plugin configuration to Redis."""
    redis = get_redis_client(async_client=True, database="main")
    key = f"plugin:config:{plugin_name}"
    await redis.set(key, json.dumps(config))


async def _load_plugin_config(plugin_name: str) -> Optional[Dict]:
    """Load plugin configuration from Redis."""
    redis = get_redis_client(async_client=True, database="main")
    key = f"plugin:config:{plugin_name}"
    data = await redis.get(key)
    return json.loads(data) if data else None
