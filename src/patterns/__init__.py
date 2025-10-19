"""
Pattern Management Module

Centralized pattern management for AutoBot including conversation patterns,
command patterns, security patterns, and more.
"""

from src.constants.network_constants import NetworkConstants

from .conversation_patterns import (
    ConversationPatterns,
    ConversationType,
    conversation_patterns,
)

__all__ = ["ConversationPatterns", "ConversationType", "conversation_patterns"]
