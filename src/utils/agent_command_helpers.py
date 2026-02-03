# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Command Helpers - Shared command execution utilities for agents.

This module provides common command execution patterns used across
security/network scanning agents and other shell-invoking agents.

Extracted to eliminate code duplication (Issue #292).
"""

from typing import Any, Dict, List

from src.constants.threshold_constants import TimingConstants
from src.utils.command_utils import execute_shell_command


async def run_agent_command(
    cmd: List[str],
    timeout: int = TimingConstants.STANDARD_TIMEOUT,
) -> Dict[str, Any]:
    """
    Run a shell command with timeout and return standardized result.

    This wrapper around execute_shell_command provides a simplified
    interface commonly used by security/network scanning agents.

    Args:
        cmd: Command and arguments as list
        timeout: Maximum execution time in seconds (default: 60)

    Returns:
        Dict with:
            - status: "success" or "error"
            - output: stdout on success
            - message: error message on failure
    """
    result = await execute_shell_command(cmd, timeout=timeout)

    # Convert to expected format for agents
    if result["status"] == "success":
        return {"status": "success", "output": result["stdout"]}
    else:
        # Combine stderr and error info for backward compatibility
        error_msg = (
            result["stderr"]
            or f"Command failed with return code {result['return_code']}"
        )
        if result["status"] == "timeout":
            error_msg = f"Command timed out after {timeout} seconds"

        return {
            "status": "error",
            "message": error_msg,
        }
