# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC configuration package (GH#8487).

Re-exports legacy llc/config.py symbols so existing callers continue to work
now that llc/config/ directory (GH#8487) shadows the old flat module.
"""

import os

# Agent API base URL — re-exported from the legacy flat module so that
# ``from llc.config import AGENT_API_BASE_URL`` keeps working (GH#8487).
AGENT_API_BASE_URL = os.environ.get("LLC_AGENT_API_BASE_URL", "http://localhost:8001/api")

# Placeholder written into heartbeat context by HeartbeatContextBuilder before a
# real run-scoped key is issued at dispatch time. Subprocess adapters skip this
# value when injecting AUTOBOT_LLC_API_KEY and redact it from LLC_INVOKE_CONTEXT
# (GH#9623, GH#9789). Shared here so the producer (kb) and consumers (adapters)
# can never drift (GH#9777).
AGENT_API_KEY_PLACEHOLDER = "<injected-at-runtime>"

__all__ = ["AGENT_API_BASE_URL", "AGENT_API_KEY_PLACEHOLDER"]
