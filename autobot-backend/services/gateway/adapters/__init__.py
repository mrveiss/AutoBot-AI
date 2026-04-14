# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Platform adapters for unified message gateway."""

from .base_adapter import BaseAdapter, NormalizedResponse, UnifiedMessage
from .discord_adapter import DiscordAdapter
from .slack_adapter import SlackAdapter
from .teams_adapter import TeamsAdapter
from .web_adapter import WebAdapter
from .whatsapp_adapter import WhatsAppAdapter

__all__ = [
    "BaseAdapter",
    "UnifiedMessage",
    "NormalizedResponse",
    "SlackAdapter",
    "DiscordAdapter",
    "WhatsAppAdapter",
    "TeamsAdapter",
    "WebAdapter",
]
