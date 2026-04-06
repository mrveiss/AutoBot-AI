# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared models for cross-service communication."""

from autobot_shared.models.pagination import PaginationParams, apply_pagination
from autobot_shared.models.service_message import (
    MessageType,
    ServiceMessage,
    ServiceName,
    create_reply,
    deserialize_message,
    serialize_message,
)

__all__ = [
    "PaginationParams",
    "apply_pagination",
    "ServiceMessage",
    "ServiceName",
    "MessageType",
    "serialize_message",
    "deserialize_message",
    "create_reply",
]
