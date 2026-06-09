# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC configuration (GH#8487, GH#9776).

Single source of truth for LLC config constants. The legacy flat module
``llc/config.py`` was shadowed by this package and therefore dead — its unique
``DEFAULT_STREAMING_WATCHDOG_TIMEOUT`` was unreachable. It is folded in here and
the flat module deleted (GH#9776).
"""

import os

# Agent API base URL (used for context assembly and heartbeat payloads).
AGENT_API_BASE_URL = os.environ.get("LLC_AGENT_API_BASE_URL", "http://localhost:8001/api")

# Default streaming watchdog timeout (seconds of silence before kill).
# Per-agent override via adapter_config["streaming_watchdog_timeout_seconds"].
DEFAULT_STREAMING_WATCHDOG_TIMEOUT = int(os.environ.get("LLC_STREAMING_WATCHDOG_TIMEOUT", "120"))

# Placeholder written into heartbeat context by HeartbeatContextBuilder before a
# real run-scoped key is issued at dispatch time. Subprocess adapters skip this
# value when injecting AUTOBOT_LLC_API_KEY and redact it from LLC_INVOKE_CONTEXT
# (GH#9623, GH#9789). Shared here so the producer (kb) and consumers (adapters)
# can never drift (GH#9777).
AGENT_API_KEY_PLACEHOLDER = "<injected-at-runtime>"

__all__ = [
    "AGENT_API_BASE_URL",
    "AGENT_API_KEY_PLACEHOLDER",
    "DEFAULT_STREAMING_WATCHDOG_TIMEOUT",
]
