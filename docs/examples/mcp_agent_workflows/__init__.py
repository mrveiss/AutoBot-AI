"""
MCP Agent Workflow Examples

This package contains example workflows demonstrating how to use
AutoBot's MCP tools with LangChain agents for autonomous multi-step tasks.

Examples:
- research_workflow.py: Knowledge search + structured thinking + file writing
- code_analysis.py: File system navigation + sequential thinking + knowledge updates
- vnc_monitoring.py: Desktop observation + browser context + activity logging

Shared Utilities:
- base.py: Reusable MCPClient, WorkflowResult, and helper functions

Issue: #48 - LangChain Agent Integration Examples for MCP Tools
"""

from .base import (
    AUTOBOT_BACKEND_URL,
    MCPClient,
    MCPToolError,
    WorkflowResult,
    call_mcp_tool,
    call_mcp_tool_safe,
    default_client,
    ensure_directory_exists,
    format_iso_timestamp,
    format_timestamp,
    generate_session_id,
    logger,
    read_file_safe,
    write_file_safe,
)

__all__ = [
    # Core client
    "MCPClient",
    "MCPToolError",
    "default_client",
    # Convenience functions
    "call_mcp_tool",
    "call_mcp_tool_safe",
    # Workflow tracking
    "WorkflowResult",
    # Utilities
    "format_timestamp",
    "format_iso_timestamp",
    "generate_session_id",
    "ensure_directory_exists",
    "write_file_safe",
    "read_file_safe",
    # Configuration
    "AUTOBOT_BACKEND_URL",
    "logger",
]

__version__ = "1.0.0"
__author__ = "mrveiss"
