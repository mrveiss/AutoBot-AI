# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared models for cross-service communication."""

from autobot_shared.models.service_message import (
    MessageType,
    ServiceMessage,
    ServiceName,
    create_reply,
    deserialize_message,
    serialize_message,
)
from autobot_shared.models.task_result import (
    TaskResult,
    task_error,
    task_pending,
    task_pending_approval,
    task_success,
)

__all__ = [
    "ServiceMessage",
    "ServiceName",
    "MessageType",
    "serialize_message",
    "deserialize_message",
    "create_reply",
    "TaskResult",
    "task_success",
    "task_error",
    "task_pending",
    "task_pending_approval",
]
