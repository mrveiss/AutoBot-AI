# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unified multi-platform message gateway."""

from .adapters import (
    BaseAdapter,
    DiscordAdapter,
    IMessageAdapter,
    MatrixAdapter,
    NormalizedResponse,
    SignalAdapter,
    SlackAdapter,
    TeamsAdapter,
    TelegramAdapter,
    UnifiedMessage,
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
    "UnifiedMessage",
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
