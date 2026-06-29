# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unified multi-platform message gateway."""

from .adapters import (
    BaseAdapter,
    DiscordAdapter,
    GatewayMessage,
    IMessageAdapter,
    MatrixAdapter,
    NormalizedResponse,
    SignalAdapter,
    SlackAdapter,
    TeamsAdapter,
    TelegramAdapter,
    WebAdapter,
    WhatsAppAdapter,
)
from .gateway_manager import GatewayManager
from .message_queue import MessageQueue, RateLimiter

__all__ = [
    "GatewayManager",
    "MessageQueue",
    "RateLimiter",
    "BaseAdapter",
    "GatewayMessage",
    "NormalizedResponse",
    "SlackAdapter",
    "DiscordAdapter",
    "WhatsAppAdapter",
    "TeamsAdapter",
    "WebAdapter",
    "TelegramAdapter",
    "SignalAdapter",
    "MatrixAdapter",
    "IMessageAdapter",
]
