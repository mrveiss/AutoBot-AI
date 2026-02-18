# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Issue #656 - StreamingMessage LogItem Pattern.

Tests verify:
1. StreamingMessage class with stream() and update() methods
2. Stable UUID across updates
3. Version increments on each operation
4. Correct operation tracking (create, stream, update)
5. Metadata management
6. WorkflowMessage conversion
"""

import pytest
from backend.chat_workflow.models import StreamingMessage, StreamingOperation


class TestStreamingMessageBasics:
    """Test StreamingMessage basic functionality."""

    def test_default_creation(self):
        """Test default message creation."""
        msg = StreamingMessage()
        assert msg.type == "response"
        assert msg.content == ""
        assert msg.version == 0
        assert msg.operation == StreamingOperation.CREATE
        assert len(msg.id) == 36  # UUID format

    def test_custom_creation(self):
        """Test message with custom type."""
        msg = StreamingMessage(type="thought")
        assert msg.type == "thought"
        assert msg.version == 0

    def test_id_is_stable(self):
        """ID should not change across updates."""
        msg = StreamingMessage()
        original_id = msg.id
        msg.stream("chunk1")
        msg.stream("chunk2")
        msg.update("replaced")
        assert msg.id == original_id


class TestStreamOperation:
    """Test stream() method for content accumulation."""

    def test_stream_accumulates(self):
        """stream() should append content."""
        msg = StreamingMessage()
        msg.stream("Hello ")
        msg.stream("World")
        assert msg.content == "Hello World"
        assert msg.version == 2

    def test_stream_increments_version(self):
        """Each stream() call increments version."""
        msg = StreamingMessage()
        assert msg.version == 0
        msg.stream("a")
        assert msg.version == 1
        msg.stream("b")
        assert msg.version == 2
        msg.stream("c")
        assert msg.version == 3

    def test_stream_sets_operation(self):
        """stream() should set operation to STREAM."""
        msg = StreamingMessage()
        assert msg.operation == StreamingOperation.CREATE
        msg.stream("chunk")
        assert msg.operation == StreamingOperation.STREAM

    def test_stream_returns_self(self):
        """stream() should return self for chaining."""
        msg = StreamingMessage()
        result = msg.stream("chunk")
        assert result is msg

    def test_stream_chaining(self):
        """Multiple stream() calls can be chained."""
        msg = StreamingMessage()
        msg.stream("a").stream("b").stream("c")
        assert msg.content == "abc"
        assert msg.version == 3


class TestUpdateOperation:
    """Test update() method for content replacement."""

    def test_update_replaces(self):
        """update() should replace content."""
        msg = StreamingMessage()
        msg.update("Step 1")
        msg.update("Step 2")
        assert msg.content == "Step 2"
        assert msg.version == 2

    def test_update_increments_version(self):
        """Each update() call increments version."""
        msg = StreamingMessage()
        msg.update("v1")
        assert msg.version == 1
        msg.update("v2")
        assert msg.version == 2

    def test_update_sets_operation(self):
        """update() should set operation to UPDATE."""
        msg = StreamingMessage()
        msg.update("content")
        assert msg.operation == StreamingOperation.UPDATE

    def test_update_returns_self(self):
        """update() should return self for chaining."""
        msg = StreamingMessage()
        result = msg.update("content")
        assert result is msg

    def test_update_after_stream(self):
        """update() after stream() should replace accumulated content."""
        msg = StreamingMessage()
        msg.stream("a").stream("b").stream("c")
        assert msg.content == "abc"
        msg.update("replaced")
        assert msg.content == "replaced"
        assert msg.operation == StreamingOperation.UPDATE


class TestSetType:
    """Test set_type() method for type transitions."""

    def test_set_type_changes_type(self):
        """set_type() should change message type."""
        msg = StreamingMessage(type="response")
        msg.set_type("thought")
        assert msg.type == "thought"

    def test_set_type_increments_version(self):
        """set_type() should increment version."""
        msg = StreamingMessage()
        msg.set_type("planning")
        assert msg.version == 1

    def test_set_type_returns_self(self):
        """set_type() should return self for chaining."""
        msg = StreamingMessage()
        result = msg.set_type("thought")
        assert result is msg


class TestMetadataOperations:
    """Test metadata management methods."""

    def test_set_metadata(self):
        """set_metadata() should set key-value pair."""
        msg = StreamingMessage()
        msg.set_metadata("model", "llama3")
        assert msg.metadata["model"] == "llama3"

    def test_set_metadata_increments_version(self):
        """set_metadata() should increment version."""
        msg = StreamingMessage()
        msg.set_metadata("key", "value")
        assert msg.version == 1

    def test_set_metadata_returns_self(self):
        """set_metadata() should return self for chaining."""
        msg = StreamingMessage()
        result = msg.set_metadata("key", "value")
        assert result is msg

    def test_merge_metadata(self):
        """merge_metadata() should merge multiple key-value pairs."""
        msg = StreamingMessage()
        msg.set_metadata("existing", "value1")
        msg.merge_metadata({"new1": "value2", "new2": "value3"})
        assert msg.metadata["existing"] == "value1"
        assert msg.metadata["new1"] == "value2"
        assert msg.metadata["new2"] == "value3"

    def test_merge_metadata_increments_version(self):
        """merge_metadata() should increment version."""
        msg = StreamingMessage()
        msg.merge_metadata({"a": 1, "b": 2})
        assert msg.version == 1

    def test_merge_metadata_returns_self(self):
        """merge_metadata() should return self for chaining."""
        msg = StreamingMessage()
        result = msg.merge_metadata({"key": "value"})
        assert result is msg


class TestToWorkflowMessage:
    """Test conversion to WorkflowMessage."""

    def test_to_workflow_message_basic(self):
        """to_workflow_message() should create WorkflowMessage."""
        msg = StreamingMessage(type="response")
        msg.stream("Hello")

        wm = msg.to_workflow_message()

        assert wm.type == "response"
        assert wm.content == "Hello"
        assert wm.id == msg.id

    def test_to_workflow_message_metadata(self):
        """to_workflow_message() should include streaming metadata."""
        msg = StreamingMessage()
        msg.set_metadata("model", "llama3")
        msg.stream("chunk")

        wm = msg.to_workflow_message()

        assert wm.metadata["message_id"] == msg.id
        assert wm.metadata["version"] == msg.version
        assert wm.metadata["operation"] == "stream"
        assert wm.metadata["streaming"] is True
        assert wm.metadata["model"] == "llama3"

    def test_to_workflow_message_preserves_id(self):
        """to_workflow_message() should use same ID for stable identity."""
        msg = StreamingMessage()
        msg.stream("a")
        wm1 = msg.to_workflow_message()
        msg.stream("b")
        wm2 = msg.to_workflow_message()

        assert wm1.id == wm2.id == msg.id

    def test_to_workflow_message_tracks_version(self):
        """to_workflow_message() should include incrementing version."""
        msg = StreamingMessage()
        msg.stream("a")
        wm1 = msg.to_workflow_message()
        msg.stream("b")
        wm2 = msg.to_workflow_message()

        assert wm1.metadata["version"] == 1
        assert wm2.metadata["version"] == 2


class TestToDict:
    """Test dictionary serialization."""

    def test_to_dict(self):
        """to_dict() should serialize all fields."""
        msg = StreamingMessage(type="progress")
        msg.set_metadata("step", 1)
        msg.update("Step 1 complete")

        d = msg.to_dict()

        assert d["id"] == msg.id
        assert d["type"] == "progress"
        assert d["content"] == "Step 1 complete"
        assert d["metadata"]["step"] == 1
        assert d["version"] == 2  # set_metadata + update
        assert d["operation"] == "update"


class TestStreamingOperation:
    """Test StreamingOperation enum."""

    def test_operation_values(self):
        """Verify operation enum values."""
        assert StreamingOperation.CREATE.value == "create"
        assert StreamingOperation.STREAM.value == "stream"
        assert StreamingOperation.UPDATE.value == "update"


class TestMethodChaining:
    """Test full method chaining scenarios."""

    def test_full_chaining(self):
        """All methods can be chained together."""
        msg = (
            StreamingMessage()
            .set_type("thought")
            .set_metadata("model", "llama3")
            .stream("Analyzing ")
            .stream("the problem...")
            .merge_metadata({"tokens": 5})
        )

        assert msg.type == "thought"
        assert msg.content == "Analyzing the problem..."
        assert msg.metadata["model"] == "llama3"
        assert msg.metadata["tokens"] == 5
        assert msg.version == 5  # set_type + set_metadata + 2 streams + merge

    def test_llm_streaming_pattern(self):
        """Test typical LLM streaming usage pattern."""
        msg = StreamingMessage(type="response")
        msg.merge_metadata({"model": "llama3", "terminal_session_id": "test123"})

        # Simulate streaming tokens
        chunks = ["Hello", " ", "World", "!"]
        for chunk in chunks:
            msg.stream(chunk)

        assert msg.content == "Hello World!"
        assert msg.version == len(chunks) + 1  # merge_metadata + chunks
        assert msg.operation == StreamingOperation.STREAM

    def test_progress_update_pattern(self):
        """Test typical progress update usage pattern."""
        msg = StreamingMessage(type="progress")

        for step in range(1, 4):
            msg.update(f"Step {step}/3 complete")

        assert msg.content == "Step 3/3 complete"
        assert msg.version == 3
        assert msg.operation == StreamingOperation.UPDATE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
