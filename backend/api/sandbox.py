"""
Secure Sandbox API

API endpoints for executing commands in the secure Docker sandbox environment.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.constants.network_constants import NetworkConstants
from src.secure_sandbox_executor import (
    SandboxConfig,
    SandboxExecutionMode,
    SandboxSecurityLevel,
    execute_in_sandbox,
    get_secure_sandbox,
)

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


@router.post("/execute")
async def execute_command(request: SandboxExecuteRequest):
    """
    Execute a command in the secure sandbox.

    Features:
    - Multi-level security isolation (low, medium, high)
    - Resource usage monitoring
    - Command validation
    - Security event logging
    """
    try:
        logger.info(f"Sandbox execution request: {request.command[:50]}...")

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
                detail="Secure sandbox unavailable - command execution blocked for security"
            )
        
        # Execute command
        result = await sandbox.execute_command(request.command, config)

        return JSONResponse(
            status_code=200 if result.success else 400,
            content={
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": result.execution_time,
                "container_id": result.container_id,
                "security_events": result.security_events,
                "resource_usage": result.resource_usage,
                "metadata": result.metadata,
            },
        )

    except Exception as e:
        logger.error(f"Sandbox execution error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Sandbox execution failed: {str(e)}"
        )


@router.post("/execute/script")
async def execute_script(request: SandboxScriptRequest):
    """
    Execute a script in the secure sandbox.

    Supports multiple languages:
    - bash/sh: Shell scripts
    - python/python3: Python scripts
    """
    try:
        logger.info(f"Sandbox script execution: {request.language}")

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
                detail="Secure sandbox unavailable - script execution blocked for security"
            )
        
        # Execute script
        result = await sandbox.execute_script(
            request.script_content, request.language, config
        )

        return JSONResponse(
            status_code=200 if result.success else 400,
            content={
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": result.execution_time,
                "container_id": result.container_id,
                "security_events": result.security_events,
                "resource_usage": result.resource_usage,
                "metadata": result.metadata,
            },
        )

    except Exception as e:
        logger.error(f"Script execution error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Script execution failed: {str(e)}"
        )


@router.post("/execute/batch")
async def execute_batch(request: SandboxBatchRequest):
    """
    Execute multiple commands in sequence within a single sandbox.

    Features:
    - Sequential command execution
    - Optional stop on error
    - Aggregate results
    """
    try:
        logger.info(f"Batch execution: {len(request.commands)} commands")

        # Validate security level
        try:
            security_level = SandboxSecurityLevel(request.security_level)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid security level. Must be one of: {[level.value for level in SandboxSecurityLevel]}",
            )

        # Create batch script
        script_lines = ["#!/bin/bash", "set -e" if request.stop_on_error else ""]

        for i, command in enumerate(request.commands):
            script_lines.append(
                f"echo '=== Executing command {i+1}/{len(request.commands)} ==='"
            )
            script_lines.append(command)
            script_lines.append("echo '=== Command completed ==='")
            script_lines.append("")

        script_content = "\n".join(script_lines)

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
                detail="Secure sandbox unavailable - batch execution blocked for security"
            )
        
        # Execute as script
        result = await sandbox.execute_script(script_content, "bash", config)

        return JSONResponse(
            status_code=200 if result.success else 400,
            content={
                "success": result.success,
                "commands_count": len(request.commands),
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": result.execution_time,
                "container_id": result.container_id,
                "security_events": result.security_events,
                "resource_usage": result.resource_usage,
                "metadata": result.metadata,
            },
        )

    except Exception as e:
        logger.error(f"Batch execution error: {e}")
        raise HTTPException(status_code=500, detail=f"Batch execution failed: {str(e)}")


@router.get("/stats")
async def get_sandbox_stats():
    """
    Get sandbox execution statistics.

    Returns:
    - Successful/failed execution counts
    - Active container count
    - Available security levels
    """
    try:
        # Get sandbox instance with lazy initialization
        sandbox = get_secure_sandbox()
        if sandbox is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "error": "Secure sandbox unavailable",
                    "statistics": {
                        "successful_executions": 0,
                        "failed_executions": 0,
                        "active_containers": 0
                    },
                    "capabilities": {
                        "security_levels": ["high", "medium", "low"],
                        "execution_modes": ["command", "script", "batch", "interactive"],
                        "supported_languages": ["bash", "sh", "python", "python3"],
                        "monitoring_enabled": False,
                        "network_isolation": False,
                        "resource_limits": False,
                    },
                }
            )
        
        stats = await sandbox.get_sandbox_stats()

        return JSONResponse(
            status_code=200,
            content={
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
        )

    except Exception as e:
        logger.error(f"Stats retrieval error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/security-levels")
async def get_security_levels():
    """
    Get detailed information about available security levels.
    """
    return JSONResponse(
        status_code=200,
        content={
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
    )


@router.get("/examples")
async def get_sandbox_examples():
    """
    Get example sandbox execution requests.
    """
    return JSONResponse(
        status_code=200,
        content={
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
                        "script_content": "import sys\nprint(f'Python {sys.version}')\nprint('Secure execution successful!')",
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
                    "description": "Execute with network access (medium/low security only)",
                    "request": {
                        "command": "ping -c 3 8.8.8.8",
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
    )
