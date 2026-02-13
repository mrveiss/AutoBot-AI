# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Gateway Configuration

Issue #732: Unified Gateway for multi-channel communication.
Contains configuration settings for the Gateway service.
"""

import os
from dataclasses import dataclass


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
        return cls(
            rate_limit_per_user=int(os.getenv("GATEWAY_RATE_LIMIT_USER", "60")),
            rate_limit_per_channel=int(os.getenv("GATEWAY_RATE_LIMIT_CHANNEL", "100")),
            session_timeout_seconds=int(os.getenv("GATEWAY_SESSION_TIMEOUT", "1800")),
            max_message_size_bytes=int(
                os.getenv("GATEWAY_MAX_MESSAGE_SIZE", str(1024 * 1024))
            ),
            max_sessions_per_user=int(os.getenv("GATEWAY_MAX_SESSIONS_USER", "5")),
            enable_sandbox_mode=os.getenv("GATEWAY_ENABLE_SANDBOX", "false").lower()
            == "true",
            heartbeat_interval_seconds=int(
                os.getenv("GATEWAY_HEARTBEAT_INTERVAL", "30")
            ),
            message_retention_hours=int(
                os.getenv("GATEWAY_MESSAGE_RETENTION_HOURS", "24")
            ),
        )


# Default configuration instance
DEFAULT_CONFIG = GatewayConfig.from_env()
