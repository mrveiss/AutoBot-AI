# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one adapter package for the unified message gateway (#15024).

Two roles, one package:

* ``BaseAdapter`` (``base_adapter.py``) -- payload normalizers used by ``GatewayManager``.
* ``BaseChannelAdapter`` (``transport_base.py``) -- session transports used by ``Gateway``.
"""

from .base_adapter import BaseAdapter, GatewayMessage, NormalizedResponse
from .discord_adapter import DiscordAdapter
from .imessage_adapter import IMessageAdapter
from .matrix_adapter import MatrixAdapter
from .signal_adapter import SignalAdapter
from .slack_adapter import SlackAdapter
from .teams_adapter import TeamsAdapter
from .telegram_adapter import TelegramAdapter
from .transport_base import BaseChannelAdapter
from .web_adapter import WebAdapter
from .websocket_adapter import WebSocketAdapter
from .whatsapp_adapter import WhatsAppAdapter

__all__ = [
    "BaseAdapter",
    "BaseChannelAdapter",
    "WebSocketAdapter",
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
