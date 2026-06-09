# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from autobot_shared.models.task_result import (
    TaskResult,
    task_error,
    task_pending,
    task_pending_approval,
    task_success,
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
    "TaskResult",
    "task_success",
    "task_error",
    "task_pending",
    "task_pending_approval",
]
