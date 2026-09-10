# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSH connection-test helpers for the nodes API.

Extracted verbatim from api/nodes.py, which sat at exactly its recorded size
ceiling (3017/3017). ``scripts/python_file_size_known_large.py`` says that
mapping ONLY SHRINKS -- "never add an entry to make a new file pass; split the
file instead" -- so the block had to move out before anything could be added.

These five build or interpret an ``ssh``/``sshpass`` invocation for the
test-connection route and touch no router, session or model state, which is
what made them separable. Pure move: no behaviour change.
"""

from __future__ import annotations

from models.schemas import ConnectionTestRequest, ConnectionTestResponse


def _build_password_ssh_command(request: ConnectionTestRequest, remote_cmd: str) -> list[str]:
    """
    Build SSH command with sshpass for password authentication.

    Helper for test_connection (Issue #665).
    """
    return [
        "sshpass",
        "-p",
        request.password,
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "PubkeyAuthentication=no",
        "-p",
        str(request.ssh_port),
        f"{request.ssh_user}@{request.ip_address}",
        remote_cmd,
    ]


def _build_key_ssh_command(request: ConnectionTestRequest, remote_cmd: str) -> list[str]:
    """
    Build SSH command with BatchMode for key-based authentication.

    Helper for test_connection (Issue #665).
    """
    return [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        "-p",
        str(request.ssh_port),
        f"{request.ssh_user}@{request.ip_address}",
        remote_cmd,
    ]


def _build_ssh_success_response(stdout: bytes, latency_ms: float) -> ConnectionTestResponse:
    """
    Create success ConnectionTestResponse from SSH stdout.

    Helper for test_connection (Issue #665).
    """
    os_info = stdout.decode("utf-8", errors="replace").strip()
    return ConnectionTestResponse(
        success=True,
        message="Connection successful",
        latency_ms=round(latency_ms, 2),
        os_info=os_info[:500] if os_info else None,
    )


def _build_ssh_failure_response(stderr: bytes, latency_ms: float) -> ConnectionTestResponse:
    """
    Create failure ConnectionTestResponse from SSH stderr with cleaned error.

    Helper for test_connection (Issue #665).
    """
    error_msg = stderr.decode("utf-8", errors="replace").strip()
    # Clean up error message - don't expose password details
    if "sshpass" in error_msg.lower():
        error_msg = "SSH authentication failed. Check credentials."
    return ConnectionTestResponse(
        success=False,
        message="Connection failed",
        latency_ms=round(latency_ms, 2),
        error=error_msg[:500] if error_msg else "SSH connection refused",
    )


def _handle_file_not_found_error(error: FileNotFoundError) -> ConnectionTestResponse:
    """
    Handle FileNotFoundError for missing SSH tools.

    Helper for test_connection (Issue #665).
    """
    error_msg = str(error)
    if "ssh" in error_msg.lower():
        return ConnectionTestResponse(
            success=False,
            message="Connection failed",
            error="SSH client not found. Install: sudo apt install openssh-client",
        )
    return ConnectionTestResponse(
        success=False,
        message="Connection failed",
        error=f"Required tool not found: {error_msg}",
    )
