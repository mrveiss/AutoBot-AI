# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent Client Protocol (ACP) server surface for AutoBot (#14825)."""

from acp.protocol import ACP_PROTOCOL_VERSION, AcpError, AcpMethod
from acp.server import AcpServer

__all__ = ["AcpServer", "AcpError", "AcpMethod", "ACP_PROTOCOL_VERSION"]
