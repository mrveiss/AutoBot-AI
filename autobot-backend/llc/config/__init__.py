# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC configuration (GH#8487, GH#9776).

Single source of truth for LLC config constants. The legacy flat module
``llc/config.py`` was shadowed by this package and therefore dead — its unique
``DEFAULT_STREAMING_WATCHDOG_TIMEOUT`` was unreachable. It is folded in here and
the flat module deleted (GH#9776).
"""

import logging
import os
from decimal import Decimal, InvalidOperation

from autobot_shared.ssot_config import config as _ssot_config

_cfg_logger = logging.getLogger(__name__)


def _env_decimal(name: str, default: str) -> Decimal:
    """Read an env var as Decimal; log a warning and return the default on malformed input."""
    raw = os.environ.get(name, default)
    try:
        return Decimal(raw)
    except InvalidOperation:
        _cfg_logger.warning("LLC config: %s=%r is not a valid decimal — using default %s", name, raw, default)
        return Decimal(default)


def _default_agent_api_base_url() -> str:
    """Derive the LLC agent API base URL from SSOT config (vm.main / port.backend)."""
    return f"{_ssot_config.backend_url}/api"


# Agent API base URL (used for context assembly and heartbeat payloads).
# Env var LLC_AGENT_API_BASE_URL takes precedence; default derives from SSOT.
AGENT_API_BASE_URL = os.environ.get("LLC_AGENT_API_BASE_URL", _default_agent_api_base_url())

# Default dollar budget limit for newly provisioned agent budget rows.
# Override via LLC_DEFAULT_BUDGET_LIMIT env var (GH#9901).
DEFAULT_BUDGET_LIMIT: Decimal = _env_decimal("LLC_DEFAULT_BUDGET_LIMIT", "10.00")

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
    "DEFAULT_BUDGET_LIMIT",
    "DEFAULT_STREAMING_WATCHDOG_TIMEOUT",
]
