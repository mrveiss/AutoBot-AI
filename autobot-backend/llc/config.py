# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC module configuration (GH#8236, GH#8232, GH#9030).

Centralized configuration for LLC APIs, including agent API base URL
and authentication endpoints.
"""

import os

# Agent API base URL (used for context assembly and heartbeat payloads)
AGENT_API_BASE_URL = os.environ.get("LLC_AGENT_API_BASE_URL", "http://localhost:8001/api")

# Default streaming watchdog timeout (seconds of silence before kill)
# Per-agent override via adapter_config["streaming_watchdog_timeout_seconds"]
DEFAULT_STREAMING_WATCHDOG_TIMEOUT = int(os.environ.get("LLC_STREAMING_WATCHDOG_TIMEOUT", "120"))

__all__ = ["AGENT_API_BASE_URL", "DEFAULT_STREAMING_WATCHDOG_TIMEOUT"]
