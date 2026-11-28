# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat message for an MCP bridge call that asked for approval (Issue #2622)."""

from typing import Any

from async_chat_workflow import WorkflowMessage
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def build_mcp_approval_message(
    tool_name: str,
    bridge: str,
    raw_result: dict,
    execution_results: list[dict[str, Any]],
) -> WorkflowMessage:
    """Build a WorkflowMessage for MCP bridge approval requests (Issue #2622)."""
    approval_msg = raw_result.get("message", "This operation requires approval.")
    execution_results.append(
        {
            "tool": tool_name,
            "bridge": bridge,
            "result": approval_msg,
            "status": "approval_required",
        }
    )
    logger.info(
        "[Issue #2622] MCP approval required: tool=%s bridge=%s",
        tool_name,
        bridge,
    )
    return WorkflowMessage(
        type="tool_result",
        content=(
            f"[{bridge}] **Approval required:** {approval_msg}\n"
            "Ask the user to confirm, then retry with `approved: true` "
            "in the arguments."
        ),
        metadata={
            "tool_name": tool_name,
            "bridge": bridge,
            "mcp_dispatch": True,
            "approval_required": True,
        },
    )
