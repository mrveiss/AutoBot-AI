# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pattern Management Module

Centralized pattern management for AutoBot including conversation patterns,
command patterns, security patterns, and more.
"""

from .conversation_patterns import (
    ConversationPatterns,
    ConversationType,
    conversation_patterns,
)

__all__ = ["ConversationPatterns", "ConversationType", "conversation_patterns"]
