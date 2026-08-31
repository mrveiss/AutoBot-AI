# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Terminal tool management endpoints.

This module contains tool installation and validation endpoints
extracted from terminal.py (Issue #185).

Endpoints:
----------
- POST /install-tool - Install a tool with terminal streaming
- POST /check-tool - Check if a tool is installed
- POST /validate-command - Validate command safety
- GET /package-managers - Get available package managers

These endpoints are imported into terminal.py via router inclusion, and are
also registered as a standalone top-level router
(``initialization/router_registry/terminal_routers.py``). Gating must not
depend on which parent mounts this router (#15084): install/check/validate
run system commands and package installs, so the dependency lives here,
on the router itself.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from api.schemas_terminal import PackageManagersResponse, ToolInstallRequest
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Create router for tool management endpoints. Carries its own admin gate
# (#15084) so every mount point is protected by declaration, not by whichever
# parent router happens to include it -- terminal.py's admin router also
# carries this dependency, and FastAPI's dependency cache (same callable, same
# security scopes, default use_cache=True) resolves it once per request even
# when it appears on both routers, so declaring it here costs nothing extra
# on that path while closing the direct, dependency-free top-level mount.
router = APIRouter(tags=["terminal-tools"], dependencies=[Depends(check_admin_permission)])


# Tool Management endpoints


@router.post("/install-tool", response_model=Dict[str, Any])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="install_tool",
    error_code_prefix="TERMINAL_TOOLS",
)
async def install_tool(request: ToolInstallRequest):
    """Install a tool with terminal streaming"""
    # Import system command agent for tool installation
    from agents.system_command_agent import SystemCommandAgent

    system_command_agent = SystemCommandAgent()

    tool_info = {
        "name": request.tool_name,
        "package_name": request.package_name or request.tool_name,
        "install_method": request.install_method,
        "custom_command": request.custom_command,
        "update_first": request.update_first,
    }

    result = await system_command_agent.install_tool(tool_info, "default")
    return result


@router.post("/check-tool", response_model=Dict[str, Any])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_tool_installed",
    error_code_prefix="TERMINAL_TOOLS",
)
async def check_tool_installed(tool_name: str):
    """Check if a tool is installed"""
    from agents.system_command_agent import SystemCommandAgent

    system_command_agent = SystemCommandAgent()
    result = await system_command_agent.check_tool_installed(tool_name)
    return result


@router.post("/validate-command", response_model=Dict[str, Any])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="validate_command",
    error_code_prefix="TERMINAL_TOOLS",
)
async def validate_command(command: str):
    """Validate command safety"""
    from agents.system_command_agent import SystemCommandAgent

    system_command_agent = SystemCommandAgent()
    result = await system_command_agent.validate_command_safety(command)
    return result


@router.get("/package-managers", response_model=PackageManagersResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_package_managers",
    error_code_prefix="TERMINAL_TOOLS",
)
async def get_package_managers():
    """Get available package managers"""
    from agents.system_command_agent import SystemCommandAgent

    system_command_agent = SystemCommandAgent()
    detected = await system_command_agent.detect_package_manager()
    all_managers = list(system_command_agent.PACKAGE_MANAGERS.keys())

    return {
        "detected": detected,
        "available": all_managers,
        "package_managers": system_command_agent.PACKAGE_MANAGERS,
    }
