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

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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


# ------------------------------------------------------------------
# Serialization / deserialization helpers
# ------------------------------------------------------------------


def serialize_message(msg: ServiceMessage) -> str:
    """Serialize a *ServiceMessage* to a JSON string."""
    return msg.model_dump_json()


def deserialize_message(raw: str | bytes) -> Optional[ServiceMessage]:
    """Deserialize JSON *raw* into a *ServiceMessage*.

    Returns ``None`` (and logs a warning) if parsing fails instead
    of raising, so callers can treat bad payloads as non-fatal.
    """
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        return ServiceMessage.model_validate_json(text)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Failed to deserialize ServiceMessage: %s", exc)
        return None


def create_reply(
    original: ServiceMessage,
    *,
    msg_type: str = "result",
    content: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> ServiceMessage:
    """Create a reply that swaps sender/receiver and shares *correlation_id*.

    This is the standard way to respond to a cross-service request::

        reply = create_reply(
            incoming,
            msg_type="result",
            content='{"status": "ok"}',
        )
    """
    return ServiceMessage(
        sender=original.receiver,
        receiver=original.sender,
        msg_type=msg_type,
        content=content,
        correlation_id=original.correlation_id,
        meta=meta or {},
    )
