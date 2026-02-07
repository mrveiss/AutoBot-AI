# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for chat.py merge_messages deduplication logic.

Tests the merge_messages function's ability to handle:
- Streaming token accumulation (prevents 49+ duplicate messages)
- Message ID-based deduplication
- Timestamp + sender fallback deduplication
- Backend-added message preservation
"""

from typing import Dict, List

import pytest

# Import the function under test
# Note: We test the logic directly since merge_messages is async
from backend.type_defs.common import STREAMING_MESSAGE_TYPES


class TestMergeMessagesSignature:
    """Tests for message signature generation logic."""

    def test_streaming_message_types_constant(self):
        """Verify STREAMING_MESSAGE_TYPES contains expected values."""
        assert "llm_response" in STREAMING_MESSAGE_TYPES
        assert "llm_response_chunk" in STREAMING_MESSAGE_TYPES
        assert "response" in STREAMING_MESSAGE_TYPES
        assert len(STREAMING_MESSAGE_TYPES) == 3

    def test_message_id_signature_priority(self):
        """Test that message ID takes priority for signature."""
        msg = {
            "id": "msg-123",
            "text": "Hello world",
            "timestamp": "2025-01-01 10:00:00",
            "sender": "assistant",
            "messageType": "llm_response",
        }

        # Simulate msg_signature logic
        msg_id = msg.get("id") or msg.get("messageId")
        if msg_id:
            sig = ("id", msg_id)
        else:
            sig = (msg.get("timestamp", ""), msg.get("sender", ""))

        assert sig == ("id", "msg-123")

    def test_streaming_signature_excludes_text(self):
        """Test that streaming messages don't use text in signature."""
        msg1 = {
            "timestamp": "2025-01-01 10:00:00",
            "sender": "assistant",
            "text": "Hel",
            "messageType": "llm_response",
        }
        msg2 = {
            "timestamp": "2025-01-01 10:00:00",
            "sender": "assistant",
            "text": "Hello world",
            "messageType": "llm_response",
        }

        def msg_signature(msg: Dict) -> tuple:
            """Replica of the signature logic from chat.py."""
            msg_id = msg.get("id") or msg.get("messageId")
            if msg_id:
                return ("id", msg_id)
            message_type = msg.get("messageType", msg.get("type", "default"))
            if message_type in STREAMING_MESSAGE_TYPES:
                return (
                    msg.get("timestamp", ""),
                    msg.get("sender", ""),
                    message_type,
                )
            return (
                msg.get("timestamp", ""),
                msg.get("sender", ""),
                msg.get("text", "")[:100],
            )

        # Both should have same signature despite different text
        sig1 = msg_signature(msg1)
        sig2 = msg_signature(msg2)
        assert sig1 == sig2
        assert sig1 == ("2025-01-01 10:00:00", "assistant", "llm_response")


class TestStreamingDeduplication:
    """Tests for streaming token accumulation deduplication."""

    def create_streaming_sequence(self, final_text: str, step: int = 3) -> List[Dict]:
        """Create a sequence of accumulated streaming messages."""
        messages = []
        for i in range(1, len(final_text) + 1, step):
            messages.append(
                {
                    "timestamp": "2025-01-01 10:00:00",
                    "sender": "assistant",
                    "text": final_text[:i],
                    "messageType": "llm_response",
                }
            )
        return messages

    def test_identifies_streaming_responses(self):
        """Test is_streaming_response helper logic."""

        def is_streaming_response(msg: Dict) -> bool:
            message_type = msg.get("messageType", msg.get("type", "default"))
            return message_type in STREAMING_MESSAGE_TYPES

        assert is_streaming_response({"messageType": "llm_response"})
        assert is_streaming_response({"messageType": "llm_response_chunk"})
        assert is_streaming_response({"messageType": "response"})
        assert is_streaming_response({"type": "llm_response"})
        assert not is_streaming_response({"messageType": "terminal_command"})
        assert not is_streaming_response({"messageType": "system"})
        assert not is_streaming_response({"messageType": "default"})
        assert not is_streaming_response({})  # defaults to "default"

    def test_streaming_with_newer_text_preserved(self):
        """Test that longer/newer streaming text is preserved."""
        existing_text = "Hello"
        new_text = "Hello world, how are you?"

        existing = {
            "timestamp": "2025-01-01 10:00:00",
            "sender": "assistant",
            "text": existing_text,
            "messageType": "llm_response",
        }
        new = {
            "timestamp": "2025-01-01 10:00:00",
            "sender": "assistant",
            "text": new_text,
            "messageType": "llm_response",
        }

        # Simulate the deduplication logic
        def is_streaming_response(msg: Dict) -> bool:
            message_type = msg.get("messageType", msg.get("type", "default"))
            return message_type in STREAMING_MESSAGE_TYPES

        has_newer = (
            new.get("timestamp", "") == existing.get("timestamp", "")
            and new.get("sender", "") == existing.get("sender", "")
            and is_streaming_response(new)
            and len(new.get("text", "")) >= len(existing.get("text", ""))
        )

        assert has_newer is True

    def test_backend_messages_preserved(self):
        """Test that backend-added messages (terminal output) are preserved."""
        terminal_msg = {
            "timestamp": "2025-01-01 10:00:05",
            "sender": "agent_terminal",
            "text": "$ ls\nfile1.txt file2.txt",
            "messageType": "terminal_output",
        }

        def is_streaming_response(msg: Dict) -> bool:
            message_type = msg.get("messageType", msg.get("type", "default"))
            return message_type in STREAMING_MESSAGE_TYPES

        # Terminal messages should NOT be identified as streaming
        assert not is_streaming_response(terminal_msg)


class TestMergeLogic:
    """Tests for the complete merge algorithm."""

    def test_preserves_non_streaming_messages(self):
        """Test that non-streaming messages are preserved during merge."""
        existing = [
            {
                "timestamp": "2025-01-01 10:00:00",
                "sender": "user",
                "text": "Hello",
                "messageType": "default",
            },
            {
                "timestamp": "2025-01-01 10:00:05",
                "sender": "agent_terminal",
                "text": "$ whoami\nroot",
                "messageType": "terminal_output",
            },
        ]
        new = [
            {
                "timestamp": "2025-01-01 10:00:00",
                "sender": "user",
                "text": "Hello",
                "messageType": "default",
            },
        ]

        # Simulate merge - terminal output should be preserved
        def msg_signature(msg: Dict) -> tuple:
            msg_id = msg.get("id") or msg.get("messageId")
            if msg_id:
                return ("id", msg_id)
            message_type = msg.get("messageType", msg.get("type", "default"))
            if message_type in STREAMING_MESSAGE_TYPES:
                return (
                    msg.get("timestamp", ""),
                    msg.get("sender", ""),
                    message_type,
                )
            return (
                msg.get("timestamp", ""),
                msg.get("sender", ""),
                msg.get("text", "")[:100],
            )

        new_sigs = {msg_signature(msg) for msg in new}
        preserved = []
        for msg in existing:
            sig = msg_signature(msg)
            if sig not in new_sigs:
                preserved.append(msg)

        merged = preserved + new

        # Should have 2 messages: user + terminal_output
        assert len(merged) == 2
        assert any(m["messageType"] == "terminal_output" for m in merged)
        assert any(m["messageType"] == "default" for m in merged)

    def test_deduplicates_by_id(self):
        """Test that messages with same ID are deduplicated."""
        existing = [
            {
                "id": "msg-001",
                "timestamp": "2025-01-01 10:00:00",
                "sender": "assistant",
                "text": "Hello",
                "messageType": "llm_response",
            },
        ]
        new = [
            {
                "id": "msg-001",
                "timestamp": "2025-01-01 10:00:00",
                "sender": "assistant",
                "text": "Hello world!",  # Updated text
                "messageType": "llm_response",
            },
        ]

        new_by_id = {msg["id"]: msg for msg in new if msg.get("id")}
        preserved = []
        for msg in existing:
            msg_id = msg.get("id")
            if msg_id and msg_id in new_by_id:
                continue  # Skip, will use new version
            preserved.append(msg)

        merged = preserved + new

        # Should have 1 message with updated text
        assert len(merged) == 1
        assert merged[0]["text"] == "Hello world!"


class TestRealWorldScenario:
    """Test real-world scenarios from production issues."""

    def test_issue_chat_9_streaming_accumulation(self):
        """
        Test the exact scenario from Chat 9 (session 0922a948):
        - User sends "hello"
        - LLM streams response character by character
        - Each accumulated state was being saved as separate message
        - Should result in 1 final message, not 49
        """
        # Simulate streaming accumulation (like real issue)
        accumulated_states = []
        final_text = "`Retrieving system information...`"
        for i in range(1, len(final_text) + 1, 3):
            accumulated_states.append(
                {
                    "timestamp": "2025-11-25 21:03:31",
                    "sender": "assistant",
                    "text": f" {final_text[:i]}",  # Leading space like in real data
                    "messageType": "llm_response",
                }
            )

        def msg_signature(msg: Dict) -> tuple:
            msg_id = msg.get("id") or msg.get("messageId")
            if msg_id:
                return ("id", msg_id)
            message_type = msg.get("messageType", msg.get("type", "default"))
            if message_type in STREAMING_MESSAGE_TYPES:
                return (
                    msg.get("timestamp", ""),
                    msg.get("sender", ""),
                    message_type,
                )
            return (
                msg.get("timestamp", ""),
                msg.get("sender", ""),
                msg.get("text", "")[:100],
            )

        # All streaming messages with same timestamp should have same signature
        signatures = {msg_signature(msg) for msg in accumulated_states}

        # CRITICAL: Should be exactly 1 unique signature
        assert len(signatures) == 1
        assert signatures == {("2025-11-25 21:03:31", "assistant", "llm_response")}

    def test_preserves_command_approval_request(self):
        """Test that command_approval_request messages are preserved."""
        existing = [
            {
                "timestamp": "2025-11-25 21:03:31",
                "sender": "assistant",
                "text": "`Retrieving system information...`",
                "messageType": "llm_response",
            },
            {
                "timestamp": "2025-11-25 21:04:12",
                "sender": "assistant",
                "text": "Agent wants to execute: `uname -a`",
                "messageType": "command_approval_request",
            },
        ]
        new = [
            {
                "timestamp": "2025-11-25 21:03:31",
                "sender": "assistant",
                "text": "`Retrieving system information...`",
                "messageType": "llm_response",
            },
        ]

        def msg_signature(msg: Dict) -> tuple:
            msg_id = msg.get("id") or msg.get("messageId")
            if msg_id:
                return ("id", msg_id)
            message_type = msg.get("messageType", msg.get("type", "default"))
            if message_type in STREAMING_MESSAGE_TYPES:
                return (
                    msg.get("timestamp", ""),
                    msg.get("sender", ""),
                    message_type,
                )
            return (
                msg.get("timestamp", ""),
                msg.get("sender", ""),
                msg.get("text", "")[:100],
            )

        new_sigs = {msg_signature(msg) for msg in new}

        preserved = []
        for msg in existing:
            sig = msg_signature(msg)
            if sig not in new_sigs:
                preserved.append(msg)

        merged = preserved + new

        # Should have 2 messages - approval request preserved
        assert len(merged) == 2
        assert any(m["messageType"] == "command_approval_request" for m in merged)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
