# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin Manager API

FastAPI endpoints for managing plugins at runtime.

Issue #730 - Plugin SDK for extensible tool architecture.
"""

import json
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config
from plugin_install import install_from_git, install_from_zip
from plugin_sdk.base import PluginRegistry
from plugin_sdk.capabilities import Capability, CapabilityChecker, TrustTier
from plugin_sdk.loader import PluginLoader

logger = get_logger(__name__)

router = APIRouter()

# Global plugin loader instance
_plugin_loader: PluginLoader | None = None


def get_plugin_loader() -> PluginLoader:
    """Get or create plugin loader instance."""
    global _plugin_loader
    if _plugin_loader is None:
        # Define plugin directories using SSOT config (#3397)
        plugins_root = config.path.plugins_path
        plugin_dirs = [
            plugins_root / "core-plugins",
            plugins_root / "community-plugins",
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


class PluginInstallGitRequest(BaseModel):
    """Install a plugin from a Git URL."""

    url: str = Field(..., description="HTTP(S) Git repository URL")
    ref: str | None = Field(default=None, description="Branch or tag to clone (default: HEAD)")


class PluginInstallResponse(BaseModel):
    """Result of a plugin install operation."""

    name: str = Field(..., description="Installed plugin name")
    version: str = Field(..., description="Plugin version from manifest")
    path: str = Field(..., description="Filesystem path where the plugin was installed")
    source: str = Field(..., description="Install source: 'zip' or 'git'")
    message: str = Field(..., description="Human-readable status message")


class PluginEnvStatusEntry(BaseModel):
    """Per-env-var status (never contains the actual value)."""

    configured: bool
    secret: bool
    required: bool
    description: str
    docs_url: str | None = None
    obtain_steps: List[str] = []


class PluginEnvStatusResponse(BaseModel):
    """Response for GET /plugins/{plugin_name}/env-status."""

    plugin_name: str
    env_vars: Dict[str, PluginEnvStatusEntry]


class PluginCapabilitiesResponse(BaseModel):
    """Response for GET /plugins/{plugin_name}/capabilities.

    Shows required capabilities and current approval status.
    Issue #9049.
    """

    plugin_name: str
    trust_tier: str
    required_capabilities: List[str]
    granted_capabilities: List[str]
    pending_approval: List[str]


class ApproveCapabilitiesRequest(BaseModel):
    """Request to approve plugin capabilities.

    Issue #9049.
    """

    capabilities: List[str] = Field(
        ...,
        description="List of capability strings to approve (e.g. ['kb:read', 'llm:call'])",
    )


class CapabilityAuditEntry(BaseModel):
    """Single capability audit log entry.

    Issue #9049.
    """

    timestamp: str
    plugin_name: str
    capability: str
    granted: bool
    operation: str
    metadata: str


@router.post(
    "/plugins/install/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=PluginInstallResponse,
)
@with_error_handling(error_code_prefix="PLUGIN_INSTALL_UPLOAD")
async def install_plugin_zip(
    file: UploadFile = File(..., description="Plugin ZIP archive"),
    admin_check: bool = Depends(check_admin_permission),
) -> PluginInstallResponse:
    """Issue #6464: Install a 3rd-party plugin from a ZIP upload."""
    result = await install_from_zip(file)
    return PluginInstallResponse(
        name=result.name,
        version=result.version,
        path=result.path,
        source=result.source,
        message=f"Plugin '{result.name}' v{result.version} installed. Use Discover → Load to activate.",
    )


@router.post(
    "/plugins/install/git",
    status_code=status.HTTP_201_CREATED,
    response_model=PluginInstallResponse,
)
@with_error_handling(error_code_prefix="PLUGIN_INSTALL_GIT")
async def install_plugin_git(
    request: PluginInstallGitRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> PluginInstallResponse:
    """Issue #6464: Install a 3rd-party plugin by cloning a Git repository."""
    result = await install_from_git(request.url, request.ref)
    return PluginInstallResponse(
        name=result.name,
        version=result.version,
        path=result.path,
        source=result.source,
        message=f"Plugin '{result.name}' v{result.version} cloned from {request.url}.",
    )


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
    config: PluginConfigUpdate | None = None,
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

    # Load plugin without auto-granting capabilities (Issue #9049)
    # Operator must explicitly approve capabilities via /approve-capabilities
    # Auto-grant only for official plugins from core-plugins directory
    auto_grant = manifest.trust_tier == TrustTier.OFFICIAL
    plugin_config = config.config if config else {}
    plugin = await loader.load_plugin(manifest, plugin_config, grant_capabilities=auto_grant)

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


@router.get("/plugins/{plugin_name}/env-status")
@with_error_handling(error_code_prefix="PLUGIN_ENV_STATUS")
async def get_plugin_env_status(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> PluginEnvStatusResponse:
    """
    Return per-env-var configuration status for a loaded plugin.

    The response never contains env-var values, only the configured/missing
    state and manifest metadata. Designed for host UIs to surface install
    requirements without leaking secrets.

    Issue #6971.
    """
    loader = get_plugin_loader()
    status_data = loader.get_env_status(plugin_name)
    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )
    return PluginEnvStatusResponse(
        plugin_name=plugin_name,
        env_vars={k: PluginEnvStatusEntry(**v) for k, v in status_data.items()},
    )


@router.get("/plugins/{plugin_name}/capabilities")
@with_error_handling(error_code_prefix="PLUGIN_CAPABILITIES_GET")
async def get_plugin_capabilities(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> PluginCapabilitiesResponse:
    """
    Get plugin capability requirements and approval status.

    Returns what capabilities the plugin requires vs. what has been granted.
    Used by frontend to show permission approval dialog.

    Issue #9049.
    """
    loader = get_plugin_loader()
    registry = PluginRegistry()
    checker = CapabilityChecker()

    plugin = registry.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    manifest = plugin.manifest
    required = [cap.value for cap in manifest.capabilities]
    granted = [cap.value for cap in checker.get_granted_capabilities(plugin_name)]
    pending = [cap for cap in required if cap not in granted]

    return PluginCapabilitiesResponse(
        plugin_name=plugin_name,
        trust_tier=manifest.trust_tier.value,
        required_capabilities=required,
        granted_capabilities=granted,
        pending_approval=pending,
    )


@router.post("/plugins/{plugin_name}/approve-capabilities")
@with_error_handling(error_code_prefix="PLUGIN_CAPABILITIES_APPROVE")
async def approve_plugin_capabilities(
    plugin_name: str,
    request: ApproveCapabilitiesRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Approve capabilities for a plugin.

    Operator explicitly grants permissions after reviewing capability requirements.
    This is the manual approval flow (vs. auto-approve for official plugins).

    Issue #9049.
    """
    loader = get_plugin_loader()
    registry = PluginRegistry()
    checker = CapabilityChecker()

    plugin = registry.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    # Validate requested capabilities
    try:
        capabilities = [Capability(cap) for cap in request.capabilities]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability: {exc}",
        ) from exc

    # Grant capabilities
    checker.grant_capabilities(plugin_name, capabilities)

    return {
        "status": "success",
        "message": f"Granted {len(capabilities)} capabilities to plugin {plugin_name}",
        "granted": [cap.value for cap in capabilities],
    }


@router.get("/plugins/audit")
@with_error_handling(error_code_prefix="PLUGIN_AUDIT_GET")
async def get_capability_audit_log(
    limit: int = 100,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, List[CapabilityAuditEntry]]:
    """
    Fetch capability audit log from Redis.

    Returns recent capability usage attempts (both granted and denied).
    Used by operators to monitor plugin behavior and detect violations.

    Issue #9049.

    Args:
        limit: Maximum number of audit entries to return (default 100)

    Returns:
        List of audit entries ordered by timestamp descending
    """
    redis = await get_async_redis_client(database="main")
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )

    # Fetch from Redis stream
    entries = await redis.xrevrange(
        "plugin:capability:audit",
        count=min(limit, 1000),  # Cap at 1000
    )

    audit_entries = []
    for entry_id, data in entries:
        audit_entries.append(
            CapabilityAuditEntry(
                timestamp=data.get(b"timestamp", b"").decode("utf-8"),
                plugin_name=data.get(b"plugin_name", b"").decode("utf-8"),
                capability=data.get(b"capability", b"").decode("utf-8"),
                granted=data.get(b"granted", b"false").decode("utf-8") == "true",
                operation=data.get(b"operation", b"").decode("utf-8"),
                metadata=data.get(b"metadata", b"").decode("utf-8"),
            )
        )

    return {"entries": audit_entries, "total": len(audit_entries)}


async def _save_plugin_config(plugin_name: str, config: Dict) -> None:
    """Save plugin configuration to Redis."""
    redis = await get_async_redis_client(database="main")
    key = f"plugin:config:{plugin_name}"
    await redis.set(key, json.dumps(config))


async def _load_plugin_config(plugin_name: str) -> Dict | None:
    """Load plugin configuration from Redis."""
    redis = await get_async_redis_client(database="main")
    key = f"plugin:config:{plugin_name}"
    data = await redis.get(key)
    return json.loads(data) if data else None
