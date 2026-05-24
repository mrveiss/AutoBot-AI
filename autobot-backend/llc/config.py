# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC module configuration (GH#8236, GH#8232).

Centralized configuration for LLC APIs, including agent API base URL
and authentication endpoints.
"""

import os

# Agent API base URL (used for context assembly and heartbeat payloads)
AGENT_API_BASE_URL = os.environ.get("LLC_AGENT_API_BASE_URL", "http://localhost:8001/api")

__all__ = ["AGENT_API_BASE_URL"]
