# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Gateway Configuration

Issue #732: Unified Gateway for multi-channel communication.
Contains configuration settings for the Gateway service.
"""

from dataclasses import dataclass

from autobot_shared.ssot_config import config


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
            rate_limit_per_user=int(config.gateway_rate_limit_user),
            rate_limit_per_channel=int(config.gateway_rate_limit_channel),
            session_timeout_seconds=int(config.gateway_session_timeout),
            max_message_size_bytes=int(config.gateway_max_message_size),
            max_sessions_per_user=int(config.gateway_max_sessions_user),
            enable_sandbox_mode=config.gateway_enable_sandbox.lower() == "true",
            heartbeat_interval_seconds=int(config.gateway_heartbeat_interval),
            message_retention_hours=int(config.gateway_message_retention_hours),
        )


# Default configuration instance
DEFAULT_CONFIG = GatewayConfig.from_env()
