# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secure Sandbox API

API endpoints for executing commands in the secure Docker sandbox environment.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.utils.response_builder import (
    error_response,
    service_unavailable_response,
    success_response,
)
from auth_middleware import check_admin_permission, get_current_user
from backend.constants.network_constants import NetworkConstants
from secure_sandbox_executor import (
    SandboxConfig,
    SandboxExecutionMode,
    SandboxSecurityLevel,
    get_secure_sandbox,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)


class SandboxExecuteRequest(BaseModel):
    command: str
    security_level: str = "high"  # low, medium, high
    timeout: int = 300  # 5 minutes default
    execution_mode: str = "command"  # command, script, batch
    enable_network: bool = False
    environment: Optional[dict] = None


class SandboxScriptRequest(BaseModel):
    script_content: str
    language: str = "bash"  # bash, python, etc.
    security_level: str = "high"
    timeout: int = 300
    enable_network: bool = False
    environment: Optional[dict] = None


class SandboxBatchRequest(BaseModel):
    commands: List[str]
    security_level: str = "high"
    timeout: int = 600  # 10 minutes for batch
    stop_on_error: bool = True
    enable_network: bool = False


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_command",
    error_code_prefix="SANDBOX",
)
@router.post("/execute")
async def execute_command(
    request: SandboxExecuteRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Execute a command in the secure sandbox.

    Features:
    - Multi-level security isolation (low, medium, high)
    - Resource usage monitoring
    - Command validation
    - Security event logging

    Issue #744: Requires admin authentication.
    """
    try:
        logger.info("Sandbox execution request: %s...", request.command[:50])

        # Validate security level
        try:
            security_level = SandboxSecurityLevel(request.security_level)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid security level. Must be one of: {[level.value for level in SandboxSecurityLevel]}",
            )

        # Create sandbox configuration
        config = SandboxConfig(
            security_level=security_level,
            execution_mode=SandboxExecutionMode(request.execution_mode),
            timeout=request.timeout,
            enable_network=request.enable_network,
            environment=request.environment,
        )

        # Get sandbox instance with lazy initialization
        sandbox = get_secure_sandbox()
        if sandbox is None:
            raise HTTPException(
                status_code=503,
                detail="Secure sandbox unavailable - command execution blocked for security",
            )

        # Execute command
        result = await sandbox.execute_command(request.command, config)

        data = {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time": result.execution_time,
            "container_id": result.container_id,
            "security_events": result.security_events,
            "resource_usage": result.resource_usage,
            "metadata": result.metadata,
        }
        if result.success:
            return success_response(data=data, message="Command executed successfully")
        return error_response(
            error="Command execution failed",
            status_code=400,
            error_code="EXECUTION_FAILED",
            details=data,
        )

    except Exception as e:
        logger.error("Sandbox execution error: %s", e)
        return error_response(
            error=f"Sandbox execution failed: {str(e)}",
            status_code=500,
            error_code="SANDBOX_ERROR",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_script",
    error_code_prefix="SANDBOX",
)
@router.post("/execute/script")
async def execute_script(
    request: SandboxScriptRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Execute a script in the secure sandbox.

    Supports multiple languages:
    - bash/sh: Shell scripts
    - python/python3: Python scripts

    Issue #744: Requires admin authentication.
    """
    try:
        logger.info("Sandbox script execution: %s", request.language)

        # Validate security level
        try:
            security_level = SandboxSecurityLevel(request.security_level)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid security level. Must be one of: {[level.value for level in SandboxSecurityLevel]}",
            )

        # Create sandbox configuration
        config = SandboxConfig(
            security_level=security_level,
            execution_mode=SandboxExecutionMode.SCRIPT,
            timeout=request.timeout,
            enable_network=request.enable_network,
            environment=request.environment,
        )

        # Get sandbox instance with lazy initialization
        sandbox = get_secure_sandbox()
        if sandbox is None:
            raise HTTPException(
                status_code=503,
                detail="Secure sandbox unavailable - script execution blocked for security",
            )

        # Execute script
        result = await sandbox.execute_script(
            request.script_content, request.language, config
        )

        data = {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time": result.execution_time,
            "container_id": result.container_id,
            "security_events": result.security_events,
            "resource_usage": result.resource_usage,
            "metadata": result.metadata,
        }
        if result.success:
            return success_response(data=data, message="Script executed successfully")
        return error_response(
            error="Script execution failed",
            status_code=400,
            error_code="SCRIPT_EXECUTION_FAILED",
            details=data,
        )

    except Exception as e:
        logger.error("Script execution error: %s", e)
        return error_response(
            error=f"Script execution failed: {str(e)}",
            status_code=500,
            error_code="SANDBOX_ERROR",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_batch",
    error_code_prefix="SANDBOX",
)
@router.post("/execute/batch")
async def execute_batch(
    request: SandboxBatchRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Execute multiple commands in sequence within a single sandbox (Issue #665: refactored).

    Features:
    - Sequential command execution
    - Optional stop on error
    - Aggregate results

    Issue #744: Requires admin authentication.
    """
    try:
        logger.info("Batch execution: %s commands", len(request.commands))

        # Validate security level
        security_level = _validate_batch_security_level(request.security_level)

        # Create batch script
        script_content = _build_batch_script(request.commands, request.stop_on_error)

        # Create sandbox configuration
        config = SandboxConfig(
            security_level=security_level,
            execution_mode=SandboxExecutionMode.BATCH,
            timeout=request.timeout,
            enable_network=request.enable_network,
        )

        # Get sandbox instance with lazy initialization
        sandbox = get_secure_sandbox()
        if sandbox is None:
            raise HTTPException(
                status_code=503,
                detail="Secure sandbox unavailable - batch execution blocked for security",
            )

        # Execute as script
        result = await sandbox.execute_script(script_content, "bash", config)

        data = _build_batch_result_data(request.commands, result)
        if result.success:
            return success_response(data=data, message="Batch executed successfully")
        return error_response(
            error="Batch execution failed",
            status_code=400,
            error_code="BATCH_EXECUTION_FAILED",
            details=data,
        )

    except Exception as e:
        logger.error("Batch execution error: %s", e)
        return error_response(
            error=f"Batch execution failed: {str(e)}",
            status_code=500,
            error_code="SANDBOX_ERROR",
        )


def _validate_batch_security_level(security_level_str: str) -> SandboxSecurityLevel:
    """Validate and parse security level (Issue #665: extracted helper)."""
    try:
        return SandboxSecurityLevel(security_level_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid security level. Must be one of: {[level.value for level in SandboxSecurityLevel]}",
        )


def _build_batch_script(commands: List[str], stop_on_error: bool) -> str:
    """Build batch script from commands (Issue #665: extracted helper)."""
    script_lines = ["#!/bin/bash", "set -e" if stop_on_error else ""]

    for i, command in enumerate(commands):
        script_lines.append(f"echo '=== Executing command {i+1}/{len(commands)} ==='")
        script_lines.append(command)
        script_lines.append("echo '=== Command completed ==='")
        script_lines.append("")

    return "\n".join(script_lines)


def _build_batch_result_data(commands: List[str], result: Any) -> Dict[str, Any]:
    """Build batch result data (Issue #665: extracted helper)."""
    return {
        "commands_count": len(commands),
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "execution_time": result.execution_time,
        "container_id": result.container_id,
        "security_events": result.security_events,
        "resource_usage": result.resource_usage,
        "metadata": result.metadata,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_sandbox_stats",
    error_code_prefix="SANDBOX",
)
@router.get("/stats")
async def get_sandbox_stats(
    current_user: dict = Depends(get_current_user),
):
    """
    Get sandbox execution statistics.

    Returns:
    - Successful/failed execution counts
    - Active container count
    - Available security levels

    Issue #744: Requires authenticated user.
    """
    try:
        # Get sandbox instance with lazy initialization
        sandbox = get_secure_sandbox()
        if sandbox is None:
            return service_unavailable_response(
                service="Secure sandbox",
                retry_after=30,
            )

        stats = await sandbox.get_sandbox_stats()

        return success_response(
            data={
                "status": "operational",
                "statistics": stats,
                "capabilities": {
                    "security_levels": ["low", "medium", "high"],
                    "execution_modes": ["command", "script", "batch", "interactive"],
                    "supported_languages": ["bash", "sh", "python", "python3"],
                    "monitoring_enabled": True,
                    "network_isolation": True,
                    "resource_limits": True,
                },
            },
            message="Sandbox stats retrieved",
        )

    except Exception as e:
        logger.error("Stats retrieval error: %s", e)
        return error_response(
            error=f"Failed to get stats: {str(e)}",
            status_code=500,
            error_code="STATS_ERROR",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_levels",
    error_code_prefix="SANDBOX",
)
@router.get("/security-levels")
async def get_security_levels(
    current_user: dict = Depends(get_current_user),
):
    """
    Get detailed information about available security levels.

    Issue #744: Requires authenticated user.
    """
    return success_response(
        data={
            "levels": {
                "high": {
                    "description": "Maximum isolation with strict command whitelist",
                    "features": [
                        "Command whitelist enforcement",
                        "No network access",
                        "Read-only filesystem",
                        "Minimal capabilities",
                        "Resource monitoring",
                        "Security event logging",
                    ],
                    "use_cases": [
                        "Untrusted code execution",
                        "User-submitted scripts",
                        "Security testing",
                    ],
                },
                "medium": {
                    "description": "Balanced security with controlled network access",
                    "features": [
                        "Command validation",
                        "Limited network access",
                        "Restricted filesystem",
                        "Basic capabilities",
                        "Resource limits",
                    ],
                    "use_cases": [
                        "Package installation",
                        "Build processes",
                        "Data processing",
                    ],
                },
                "low": {
                    "description": "Permissive mode for trusted operations",
                    "features": [
                        "Most commands allowed",
                        "Network access permitted",
                        "Filesystem access",
                        "Extended capabilities",
                    ],
                    "use_cases": [
                        "Development tasks",
                        "System maintenance",
                        "Trusted automation",
                    ],
                },
            },
            "default": "high",
        },
        message="Security levels retrieved",
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_sandbox_examples",
    error_code_prefix="SANDBOX",
)
@router.get("/examples")
async def get_sandbox_examples(
    current_user: dict = Depends(get_current_user),
):
    """
    Get example sandbox execution requests.

    Issue #744: Requires authenticated user.
    """
    return success_response(
        data={
            "examples": {
                "simple_command": {
                    "description": "Execute a simple command",
                    "request": {
                        "command": "echo 'Hello from secure sandbox!'",
                        "security_level": "high",
                    },
                },
                "python_script": {
                    "description": "Execute a Python script",
                    "request": {
                        "script_content": (
                            "import sys\nlogger.info('Python {sys.version}')\n"
                            "logger.info('Secure execution successful!')"
                        ),
                        "language": "python",
                        "security_level": "medium",
                    },
                },
                "batch_commands": {
                    "description": "Execute multiple commands in sequence",
                    "request": {
                        "commands": [
                            "echo 'Starting batch execution'",
                            "ls -la /sandbox",
                            "python3 -c 'print(\"Python is available\")'",
                            "echo 'Batch completed'",
                        ],
                        "security_level": "high",
                        "stop_on_error": True,
                    },
                },
                "network_enabled": {
                    "description": (
                        "Execute with network access (medium/low security only)"
                    ),
                    "request": {
                        "command": f"ping -c 3 {NetworkConstants.PUBLIC_DNS_IP}",
                        "security_level": "medium",
                        "enable_network": True,
                    },
                },
            },
            "usage_tips": [
                "Always use the highest security level that meets your needs",
                "Monitor security events for suspicious activity",
                "Set appropriate timeouts to prevent resource exhaustion",
                "Use batch execution for related commands",
                "Enable network only when absolutely necessary",
            ],
        },
        message="Examples retrieved",
    )
