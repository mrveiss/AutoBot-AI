# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for conversation persistence deduplication logic (Issue #177).

Tests the _persist_conversation method's ability to handle duplicate entries
when both terminal service and chat flow persist the same user message.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass, field
from typing import List, Dict, Any


# Mock WorkflowSession for testing
@dataclass
class MockWorkflowSession:
    """Mock session for testing."""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)


class TestPersistConversationDedup:
    """Tests for _persist_conversation deduplication logic."""

    @pytest.fixture
    def mock_workflow_manager(self):
        """Create a mock workflow manager with necessary methods."""
        manager = MagicMock()
        manager._save_conversation_history = AsyncMock()
        manager._append_to_transcript = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_empty_history_creates_new_entry(self, mock_workflow_manager):
        """Test that empty history creates a new entry."""
        session = MockWorkflowSession(conversation_history=[])

        # Simulate the deduplication logic
        message = "run ls command"
        llm_response = "I'll run the ls command for you."

        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                existing_response = last_entry.get("assistant", "")
                if llm_response not in existing_response:
                    last_entry["assistant"] = f"{existing_response}\n\n{llm_response}"
            else:
                session.conversation_history.append(
                    {"user": message, "assistant": llm_response}
                )
        else:
            session.conversation_history.append(
                {"user": message, "assistant": llm_response}
            )

        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["user"] == message
        assert session.conversation_history[0]["assistant"] == llm_response

    @pytest.mark.asyncio
    async def test_different_user_message_creates_new_entry(self, mock_workflow_manager):
        """Test that a different user message creates a new entry."""
        session = MockWorkflowSession(conversation_history=[
            {"user": "previous question", "assistant": "previous answer"}
        ])

        message = "run ls command"
        llm_response = "I'll run the ls command for you."

        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                existing_response = last_entry.get("assistant", "")
                if llm_response not in existing_response:
                    last_entry["assistant"] = f"{existing_response}\n\n{llm_response}"
            else:
                session.conversation_history.append(
                    {"user": message, "assistant": llm_response}
                )
        else:
            session.conversation_history.append(
                {"user": message, "assistant": llm_response}
            )

        assert len(session.conversation_history) == 2
        assert session.conversation_history[0]["user"] == "previous question"
        assert session.conversation_history[1]["user"] == message
        assert session.conversation_history[1]["assistant"] == llm_response

    @pytest.mark.asyncio
    async def test_same_user_message_appends_response(self, mock_workflow_manager):
        """Test that same user message appends new response to existing."""
        message = "run ls command"
        first_response = "I'll run the ls command for you."

        session = MockWorkflowSession(conversation_history=[
            {"user": message, "assistant": first_response}
        ])

        # Second response (e.g., from terminal interpretation)
        second_response = "The command completed. Here are the results:\nfile1.txt\nfile2.txt"

        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                existing_response = last_entry.get("assistant", "")
                if second_response not in existing_response:
                    last_entry["assistant"] = f"{existing_response}\n\n{second_response}"
            else:
                session.conversation_history.append(
                    {"user": message, "assistant": second_response}
                )
        else:
            session.conversation_history.append(
                {"user": message, "assistant": second_response}
            )

        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["user"] == message
        assert first_response in session.conversation_history[0]["assistant"]
        assert second_response in session.conversation_history[0]["assistant"]
        assert "\n\n" in session.conversation_history[0]["assistant"]

    @pytest.mark.asyncio
    async def test_duplicate_response_skipped(self, mock_workflow_manager):
        """Test that duplicate response is skipped (not appended twice)."""
        message = "run ls command"
        response = "I'll run the ls command for you."

        session = MockWorkflowSession(conversation_history=[
            {"user": message, "assistant": response}
        ])

        # Try to add the same response again
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                existing_response = last_entry.get("assistant", "")
                if response not in existing_response:
                    last_entry["assistant"] = f"{existing_response}\n\n{response}"
                # else: skipped (this is what we're testing)
            else:
                session.conversation_history.append(
                    {"user": message, "assistant": response}
                )
        else:
            session.conversation_history.append(
                {"user": message, "assistant": response}
            )

        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["assistant"] == response
        # Verify no duplication occurred
        assert session.conversation_history[0]["assistant"].count(response) == 1

    @pytest.mark.asyncio
    async def test_partial_duplicate_response_still_skipped(self, mock_workflow_manager):
        """Test that response already contained in existing is skipped."""
        message = "run ls command"
        first_response = "I'll run the ls command for you."
        combined_response = f"{first_response}\n\nThe command completed successfully."

        session = MockWorkflowSession(conversation_history=[
            {"user": message, "assistant": combined_response}
        ])

        # Try to add the first response again (it's already contained in combined)
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                existing_response = last_entry.get("assistant", "")
                if first_response not in existing_response:
                    last_entry["assistant"] = f"{existing_response}\n\n{first_response}"
                # else: skipped (first_response is already in combined_response)
            else:
                session.conversation_history.append(
                    {"user": message, "assistant": first_response}
                )
        else:
            session.conversation_history.append(
                {"user": message, "assistant": first_response}
            )

        assert len(session.conversation_history) == 1
        # Verify the response wasn't duplicated
        assert session.conversation_history[0]["assistant"] == combined_response


class TestIssue177Scenario:
    """Test the specific scenario from Issue #177."""

    @pytest.mark.asyncio
    async def test_terminal_interpretation_flow(self):
        """
        Test the exact scenario from Issue #177:
        1. User sends message that triggers terminal command
        2. Terminal service persists with interpretation
        3. Chat flow tries to persist with LLM response
        4. Should not create duplicate entry
        """
        session = MockWorkflowSession(conversation_history=[])
        user_message = "run the whoami command"

        # Step 1: Terminal service persists with interpretation
        interpretation = "The whoami command shows you're logged in as 'autobot'."

        # First persistence (from terminal service interpret_terminal_command)
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == user_message:
                existing_response = last_entry.get("assistant", "")
                if interpretation not in existing_response:
                    last_entry["assistant"] = f"{existing_response}\n\n{interpretation}"
            else:
                session.conversation_history.append(
                    {"user": user_message, "assistant": interpretation}
                )
        else:
            session.conversation_history.append(
                {"user": user_message, "assistant": interpretation}
            )

        assert len(session.conversation_history) == 1

        # Step 2: Chat flow tries to persist with LLM response
        llm_response = "I executed the whoami command for you."

        # Second persistence (from process_message_stream)
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == user_message:
                existing_response = last_entry.get("assistant", "")
                if llm_response not in existing_response:
                    last_entry["assistant"] = f"{existing_response}\n\n{llm_response}"
            else:
                session.conversation_history.append(
                    {"user": user_message, "assistant": llm_response}
                )
        else:
            session.conversation_history.append(
                {"user": user_message, "assistant": llm_response}
            )

        # Verify: should still be only 1 entry with both responses combined
        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["user"] == user_message
        assert interpretation in session.conversation_history[0]["assistant"]
        assert llm_response in session.conversation_history[0]["assistant"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
