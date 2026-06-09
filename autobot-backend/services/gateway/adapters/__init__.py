# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Platform adapters for unified message gateway."""

from .base_adapter import BaseAdapter, NormalizedResponse, UnifiedMessage
from .discord_adapter import DiscordAdapter
from .imessage_adapter import IMessageAdapter
from .matrix_adapter import MatrixAdapter
from .signal_adapter import SignalAdapter
from .slack_adapter import SlackAdapter
from .teams_adapter import TeamsAdapter
from .telegram_adapter import TelegramAdapter
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
    "TelegramAdapter",
    "SignalAdapter",
    "MatrixAdapter",
    "IMessageAdapter",
]
