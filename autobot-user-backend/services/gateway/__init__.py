# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Gateway Service

Issue #732: Unified Gateway for multi-channel communication.
Main exports for the Gateway service.
"""

from .channel_adapters import BaseChannelAdapter, WebSocketAdapter
from .config import DEFAULT_CONFIG, GatewayConfig
from .gateway import Gateway, get_gateway
from .message_router import MessageRouter
from .session_manager import SessionManager
from .types import (
    ChannelType,
    GatewaySession,
    MessageType,
    RoutingDecision,
    SessionStatus,
    UnifiedMessage,
)

__all__ = [
    # Core Gateway
    "Gateway",
    "get_gateway",
    # Components
    "SessionManager",
    "MessageRouter",
    # Channel Adapters
    "BaseChannelAdapter",
    "WebSocketAdapter",
    # Configuration
    "GatewayConfig",
    "DEFAULT_CONFIG",
    # Types
    "ChannelType",
    "MessageType",
    "SessionStatus",
    "UnifiedMessage",
    "GatewaySession",
    "RoutingDecision",
]
