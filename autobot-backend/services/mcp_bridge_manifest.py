# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared MCPBridgeManifest dataclass — imported by mcp_registry and each bridge."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MCPBridgeManifest:
    """Metadata describing an MCP bridge plugin."""

    name: str
    version: str
    description: str
    features: List[str] = field(default_factory=list)
    endpoint: Optional[str] = None
    resource_limits: Optional[Dict[str, int]] = None
