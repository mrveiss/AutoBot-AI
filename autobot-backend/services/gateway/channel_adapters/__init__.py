# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Channel Adapters

Issue #732: Unified Gateway for multi-channel communication.
Exports all available channel adapters.
"""

from .base import BaseChannelAdapter
from .websocket_adapter import WebSocketAdapter

__all__ = [
    "BaseChannelAdapter",
    "WebSocketAdapter",
]
