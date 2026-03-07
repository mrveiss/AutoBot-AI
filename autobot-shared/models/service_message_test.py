# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for ServiceMessage schema (#1377)."""

import uuid

from autobot_shared.models.service_message import (
    ServiceMessage,
    create_reply,
    deserialize_message,
    serialize_message,
)


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


# ------------------------------------------------------------------
# Helper function tests
# ------------------------------------------------------------------


def test_serialize_message():
    """serialize_message returns a valid JSON string."""
    msg = ServiceMessage(
        sender="main-backend",
        receiver="slm-backend",
        msg_type="task",
        content='{"action": "deploy"}',
    )
    json_str = serialize_message(msg)
    assert isinstance(json_str, str)
    assert '"sender":"main-backend"' in json_str


def test_deserialize_message_str():
    """deserialize_message parses a JSON string."""
    msg = ServiceMessage(
        sender="ai-stack",
        receiver="main-backend",
        msg_type="result",
        content="done",
    )
    json_str = serialize_message(msg)
    restored = deserialize_message(json_str)
    assert restored is not None
    assert restored.msg_id == msg.msg_id
    assert restored.sender == "ai-stack"


def test_deserialize_message_bytes():
    """deserialize_message handles bytes input (from Redis)."""
    msg = ServiceMessage(
        sender="browser-worker",
        receiver="main-backend",
        msg_type="result",
        content="ok",
    )
    raw = serialize_message(msg).encode("utf-8")
    restored = deserialize_message(raw)
    assert restored is not None
    assert restored.sender == "browser-worker"


def test_deserialize_message_invalid():
    """deserialize_message returns None on invalid input."""
    result = deserialize_message("not valid json {{{")
    assert result is None


def test_create_reply_swaps_sender_receiver():
    """create_reply swaps sender/receiver and preserves correlation_id."""
    original = ServiceMessage(
        sender="slm-backend",
        receiver="main-backend",
        msg_type="task",
        content='{"action": "status"}',
        correlation_id="corr-123",
    )
    reply = create_reply(original, content='{"status": "ok"}')
    assert reply.sender == "main-backend"
    assert reply.receiver == "slm-backend"
    assert reply.correlation_id == "corr-123"
    assert reply.msg_type == "result"
    assert reply.content == '{"status": "ok"}'
    # New msg_id (not same as original)
    assert reply.msg_id != original.msg_id


def test_create_reply_custom_type_and_meta():
    """create_reply accepts custom msg_type and meta."""
    original = ServiceMessage(
        sender="ai-stack",
        receiver="npu-worker",
        msg_type="task",
        content="process",
    )
    reply = create_reply(
        original,
        msg_type="error",
        content="GPU OOM",
        meta={"error_code": 137},
    )
    assert reply.msg_type == "error"
    assert reply.meta == {"error_code": 137}
