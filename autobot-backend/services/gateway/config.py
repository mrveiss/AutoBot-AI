# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Gateway Configuration

Issue #732: Unified Gateway for multi-channel communication.
Contains configuration settings for the Gateway service.
"""

from dataclasses import dataclass

from autobot_shared.env_utils import blank_to_none
from autobot_shared.ssot_config import config


def _int_or_default(raw: object, default: int) -> int:
    """int(raw), falling back to *default* when raw is blank/unset (#14028).

    ``ssot_config`` declares several of these knobs as ``str = Field(default="")``
    (GATEWAY_MAX_SESSIONS_USER, GATEWAY_HEARTBEAT_INTERVAL,
    GATEWAY_MESSAGE_RETENTION_HOURS) — an unset var arrives as ``""``, and
    ``int("")`` raises ValueError before ``from_env()`` ever returns.
    Same defect class as chat_history/cache.py's ``_resolve_chat_session_cache_ttl``
    (#12782), newly surfaced here because nothing previously imported
    ``services.gateway.gateway`` (and therefore this module) in tests.
    """
    resolved = blank_to_none(raw)
    if resolved is None:
        return default
    return int(resolved)


@dataclass
class GatewayConfig:
    """
    Gateway configuration settings.

    Attributes:
        rate_limit_per_user: Max messages per minute per user
        rate_limit_per_channel: Max messages per minute per channel
        session_timeout_seconds: Idle session timeout
        max_message_size_bytes: Maximum message size
        max_sessions_per_user: Maximum concurrent sessions per user
        enable_sandbox_mode: Enable sandbox mode for untrusted sessions
        heartbeat_interval_seconds: WebSocket heartbeat interval
        message_retention_hours: How long to retain message history
    """

    rate_limit_per_user: int = 60
    rate_limit_per_channel: int = 100
    session_timeout_seconds: int = 1800  # 30 minutes
    max_message_size_bytes: int = 1024 * 1024  # 1MB
    max_sessions_per_user: int = 5
    enable_sandbox_mode: bool = False
    heartbeat_interval_seconds: int = 30
    message_retention_hours: int = 24

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        """Load configuration from environment variables."""
        defaults = cls()
        return cls(
            rate_limit_per_user=int(config.gateway_rate_limit_user),
            rate_limit_per_channel=int(config.gateway_rate_limit_channel),
            session_timeout_seconds=int(config.gateway_session_timeout),
            max_message_size_bytes=int(config.gateway_max_message_size),
            max_sessions_per_user=_int_or_default(config.gateway_max_sessions_user, defaults.max_sessions_per_user),
            enable_sandbox_mode=config.gateway_enable_sandbox.lower() == "true",
            heartbeat_interval_seconds=_int_or_default(
                config.gateway_heartbeat_interval, defaults.heartbeat_interval_seconds
            ),
            message_retention_hours=_int_or_default(
                config.gateway_message_retention_hours, defaults.message_retention_hours
            ),
        )


# Default configuration instance
DEFAULT_CONFIG = GatewayConfig.from_env()
