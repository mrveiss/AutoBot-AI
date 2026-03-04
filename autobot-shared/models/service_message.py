# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unified envelope for cross-service communication (#1377).

All inter-service messages across AutoBot's distributed fleet use this
schema. The ``correlation_id`` field traces a chain of related messages
across VMs, enabling end-to-end observability.

Usage::

    from autobot_shared.models.service_message import ServiceMessage

    msg = ServiceMessage(
        sender="main-backend",
        receiver="slm-backend",
        msg_type="task",
        content='{"action": "deploy", "role": "browser"}',
    )
    payload = msg.model_dump_json()
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

ServiceName = Literal[
    "main-backend",
    "slm-backend",
    "ai-stack",
    "browser-worker",
    "npu-worker",
    "llm-cpu",
    "frontend",
    "system",
    "user",
]

MessageType = Literal[
    "task",
    "result",
    "error",
    "health",
    "deploy",
    "workflow_step",
    "notification",
]


class ServiceMessage(BaseModel):
    """Unified envelope for cross-service communication."""

    msg_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique message identifier (UUID4).",
    )
    ts: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO 8601 timestamp of message creation.",
    )
    sender: str = Field(
        description="Originating service name.",
    )
    receiver: str = Field(
        description="Target service name.",
    )
    msg_type: str = Field(
        description="Message category (task, result, error, etc.).",
    )
    content: str = Field(
        description="JSON payload or plain text body.",
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Correlation ID for tracing related messages.",
    )
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata (retry count, headers, tags).",
    )
