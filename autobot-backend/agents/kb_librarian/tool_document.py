# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Builds the knowledge-base document text for a tool (moved verbatim out of ``librarian.py``)."""

from datetime import datetime, timezone
from typing import Any, Dict

from constants.threshold_constants import CategoryDefaults

from .formatters import ToolInfoFormatter


def _build_basic_info_section(tool_info: Dict[str, Any], tool_name: str) -> str:
    """
    Build the basic information section of tool documentation.

    Extracts tool name, type, category, platform, and purpose. Issue #620.

    Args:
        tool_info: Tool information dictionary
        tool_name: Name of the tool

    Returns:
        Formatted basic information section string
    """
    return f"""TOOL DOCUMENTATION: {tool_name}
==================================================

BASIC INFORMATION:
- Name: {tool_name}
- Type: {tool_info.get('type', 'command-line tool')}
- Category: {tool_info.get('category', CategoryDefaults.GENERAL)}
- Platform: {tool_info.get('platform', 'linux')}
- Purpose: {tool_info.get('purpose', 'N/A')}"""


def _build_installation_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the installation and requirements section of tool documentation.

    Covers installation instructions and system requirements. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted installation section string
    """
    return f"""INSTALLATION:
{tool_info.get('installation', 'No installation information available')}

SYSTEM REQUIREMENTS:
{tool_info.get('requirements', 'Standard Linux system')}"""


def _build_usage_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the usage and commands section of tool documentation.

    Covers basic usage, syntax, examples, and advanced usage. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted usage section string
    """
    return f"""BASIC USAGE:
{tool_info.get('usage', 'No usage information available')}

COMMAND SYNTAX:
{tool_info.get('syntax', 'See man page for syntax')}

COMMON COMMANDS & EXAMPLES:
{ToolInfoFormatter.format_command_examples(tool_info.get('command_examples', []))}

ADVANCED USAGE:
{tool_info.get('advanced_usage', 'See documentation for advanced features')}"""


def _build_troubleshooting_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the troubleshooting and operational section of tool documentation.

    Covers troubleshooting, output formats, integrations, security, errors,
    performance, limitations, and related tools. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted troubleshooting section string
    """
    return f"""TROUBLESHOOTING:
{tool_info.get('troubleshooting', 'Check man page and documentation for issues')}

OUTPUT FORMATS:
{tool_info.get('output_formats', 'Standard text output')}

INTEGRATION WITH OTHER TOOLS:
{tool_info.get('integrations', 'Can be used with standard Unix tools via pipes')}

SECURITY CONSIDERATIONS:
{tool_info.get('security_notes', 'Use with appropriate permissions')}

ERROR CODES & MEANINGS:
{tool_info.get('error_codes', 'Standard Unix exit codes')}

PERFORMANCE NOTES:
{tool_info.get('performance', 'Performance varies with input size')}

KNOWN LIMITATIONS:
{tool_info.get('limitations', 'See documentation for limitations')}

RELATED TOOLS:
{tool_info.get('related_tools', [])}"""


def _build_resources_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the external resources section of tool documentation.

    Covers documentation URLs, source code, tutorials, and forums. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted resources section string
    """
    return f"""EXTERNAL RESOURCES:
- Official Documentation: {tool_info.get('documentation_url', 'N/A')}
- Source Code: {tool_info.get('source_url', 'N/A')}
- Tutorial Links: {tool_info.get('tutorials', [])}
- Community Forums: {tool_info.get('forums', [])}"""


def _build_metadata_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the metadata section of tool documentation.

    Covers timestamps, verification status, and usage stats. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted metadata section string
    """
    return f"""METADATA:
- Added: {datetime.now(tz=timezone.utc).isoformat()}
- Last Updated: {datetime.now(tz=timezone.utc).isoformat()}
- Verification Status: {tool_info.get('verified', 'unverified')}
- Usage Count: 0
- Success Rate: N/A
"""


def _build_tool_document_content(tool_info: Dict[str, Any], tool_name: str) -> str:
    """
    Build document content string for tool storage.

    Issue #665: Extracted from store_tool_knowledge to reduce function length.
    Issue #620: Further refactored using Extract Method pattern.

    Args:
        tool_info: Tool information dictionary
        tool_name: Name of the tool

    Returns:
        Formatted document content string
    """
    sections = [
        _build_basic_info_section(tool_info, tool_name),
        _build_installation_section(tool_info),
        _build_usage_section(tool_info),
        _build_troubleshooting_section(tool_info),
        _build_resources_section(tool_info),
        _build_metadata_section(tool_info),
    ]
    return "\n\n".join(sections)
