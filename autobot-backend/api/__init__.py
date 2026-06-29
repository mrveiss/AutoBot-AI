# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot REST API package — all router modules exported here.

Central registry of API modules mounted by app_factory; importing from
this package guarantees consistent router registration order.
"""

__all__ = [
    "chat",
    "system",
    "files",
    "knowledge",
    "llm",
    "sandbox",
    # Issue #567: base_terminal archived — endpoints migrated to terminal.py
    # Issue #3332: base_terminal removed from public API surface
    "websockets",
    "search",  # NPU-accelerated search API (#10666 B7)
    "analytics",  # Backend analytics API
    "live_events",  # Issue #1408: scoped real-time event channels
]
