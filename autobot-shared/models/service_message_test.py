# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for ServiceMessage schema (#1377)."""

import uuid

from autobot_shared.models.service_message import ServiceMessage


def test_service_message_defaults():
    """msg_id, ts, and correlation_id auto-generate when not provided."""
    msg = ServiceMessage(
        sender="main-backend",
        receiver="slm-backend",
        msg_type="task",
        content='{"action": "ping"}',
    )
    # msg_id is a valid UUID
    uuid.UUID(msg.msg_id)
    # ts is a non-empty ISO 8601 string
    assert msg.ts and "T" in msg.ts
    # correlation_id is a valid UUID
    uuid.UUID(msg.correlation_id)
    # meta defaults to empty dict
    assert msg.meta == {}


def test_service_message_explicit_correlation():
    """Explicit correlation_id is preserved, not overwritten."""
    cid = "trace-abc-123"
    msg = ServiceMessage(
        sender="slm-backend",
        receiver="browser-worker",
        msg_type="result",
        content="ok",
        correlation_id=cid,
    )
    assert msg.correlation_id == cid


def test_service_message_json_roundtrip():
    """model_dump_json / model_validate_json produces identical object."""
    original = ServiceMessage(
        sender="ai-stack",
        receiver="main-backend",
        msg_type="result",
        content='{"score": 0.95}',
        meta={"attempt": 1},
    )
    json_str = original.model_dump_json()
    restored = ServiceMessage.model_validate_json(json_str)
    assert restored.msg_id == original.msg_id
    assert restored.ts == original.ts
    assert restored.sender == original.sender
    assert restored.receiver == original.receiver
    assert restored.msg_type == original.msg_type
    assert restored.content == original.content
    assert restored.correlation_id == original.correlation_id
    assert restored.meta == original.meta


def test_service_message_meta_field():
    """Nested dict in meta is preserved through construction."""
    meta = {
        "retry_count": 3,
        "headers": {"X-Request-ID": "req-001"},
        "tags": ["urgent", "deploy"],
    }
    msg = ServiceMessage(
        sender="system",
        receiver="main-backend",
        msg_type="deploy",
        content="{}",
        meta=meta,
    )
    assert msg.meta["retry_count"] == 3
    assert msg.meta["headers"]["X-Request-ID"] == "req-001"
    assert "urgent" in msg.meta["tags"]
