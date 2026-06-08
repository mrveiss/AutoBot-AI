# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WebSocket package for AutoBot real-time features.

Provides presence tracking and collaborative session management.
Issue #3282: collaborative multi-user support.
"""

from websocket.presence import PresenceManager, presence_manager, presence_websocket_handler

__all__ = ["PresenceManager", "presence_manager", "presence_websocket_handler"]
