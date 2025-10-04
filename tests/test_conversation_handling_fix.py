"""
Test suite for conversation handling bug fix

This test validates the fix for conversation premature termination bug where
the system incorrectly ended conversations when users provided short clarifying
responses like "of autobot".

Bug Report: Conversation c09d53ab-6119-408a-8d26-d948d271ec65
Issue: System said "AutoBot out!" when user asked "help me navigate the install process of autobot"
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.chat_workflow_manager import ChatWorkflowManager, detect_exit_intent


class TestExitIntentDetection:
    """Test exit intent detection logic"""

    def test_explicit_exit_phrases(self):
        """Test that explicit exit phrases are correctly detected"""
        exit_phrases = [
            "goodbye",
            "bye",
            "exit",
            "quit",
            "end chat",
            "bye bye",
            "that's all",
            "thanks goodbye"
        ]

        for phrase in exit_phrases:
            assert detect_exit_intent(phrase) == True, f"Should detect exit intent for: {phrase}"

    def test_clarifying_responses_not_exit(self):
        """Test that clarifying responses are NOT treated as exit intent"""
        clarifying_responses = [
            "of autobot",
            "yes",
            "no",
            "ok",
            "sure",
            "please",
            "the first one",
            "option 2",
            "can you help?",
            "what about this?",
            "autobot installation"
        ]

        for response in clarifying_responses:
            assert detect_exit_intent(response) == False, f"Should NOT detect exit intent for: {response}"

    def test_questions_with_exit_words_not_exit(self):
        """Test that questions containing exit words are NOT treated as exit"""
        questions_with_exit_words = [
            "how do I exit vim?",
            "what's the quit command?",
            "can I stop this process?",
            "should I say goodbye to the service?"
        ]

        for question in questions_with_exit_words:
            assert detect_exit_intent(question) == False, f"Should NOT detect exit intent for question: {question}"

    def test_case_insensitive_detection(self):
        """Test that exit detection is case-insensitive"""
        assert detect_exit_intent("GOODBYE") == True
        assert detect_exit_intent("Bye") == True
        assert detect_exit_intent("EXIT") == True
        assert detect_exit_intent("QuIt") == True


class TestConversationContinuation:
    """Test that conversations continue appropriately"""

    @pytest.mark.asyncio
    async def test_short_response_continues_conversation(self):
        """Test that short responses like 'of autobot' continue the conversation"""
        manager = ChatWorkflowManager()
        await manager.initialize()

        session_id = "test-short-response-session"

        # Simulate the problematic conversation flow
        messages = []

        # First message: User asks for help
        async for msg in manager.process_message_stream(session_id, "help me navigate the install process"):
            messages.append(msg)

        # Check that we got a response (not an exit)
        assert len(messages) > 0, "Should receive response to initial question"
        assert not any("AutoBot out!" in msg.content for msg in messages if hasattr(msg, 'content')), \
            "Should not end conversation on initial question"

        messages.clear()

        # Second message: User clarifies with short response "of autobot"
        async for msg in manager.process_message_stream(session_id, "of autobot"):
            messages.append(msg)

        # CRITICAL: Verify conversation continues
        assert len(messages) > 0, "Should receive response to clarification"

        # Check that response is helpful, not an exit message
        all_content = " ".join([msg.content for msg in messages if hasattr(msg, 'content')])
        assert "AutoBot out!" not in all_content, "Should NOT end conversation on clarification 'of autobot'"
        assert "goodbye" not in all_content.lower() or "installation" in all_content.lower(), \
            "Should provide helpful response about AutoBot installation, not goodbye"

    @pytest.mark.asyncio
    async def test_explicit_goodbye_ends_conversation(self):
        """Test that explicit goodbye properly ends conversation"""
        manager = ChatWorkflowManager()
        await manager.initialize()

        session_id = "test-explicit-goodbye-session"

        messages = []
        async for msg in manager.process_message_stream(session_id, "goodbye"):
            messages.append(msg)

        # Verify that explicit goodbye gets exit acknowledgment
        all_content = " ".join([msg.content for msg in messages if hasattr(msg, 'content')])
        assert any(word in all_content.lower() for word in ["goodbye", "bye", "take care"]), \
            "Should acknowledge user's goodbye"

    @pytest.mark.asyncio
    async def test_ambiguous_responses_get_clarification(self):
        """Test that ambiguous responses prompt for clarification, not exit"""
        manager = ChatWorkflowManager()
        await manager.initialize()

        session_id = "test-ambiguous-response-session"

        # Send ambiguous response
        messages = []
        async for msg in manager.process_message_stream(session_id, "yes"):
            messages.append(msg)

        # Should continue conversation, possibly asking what user means
        assert len(messages) > 0, "Should receive response to ambiguous input"
        all_content = " ".join([msg.content for msg in messages if hasattr(msg, 'content')])
        assert "AutoBot out!" not in all_content, "Should not exit on ambiguous response"


class TestRegressionPrevention:
    """Regression tests to prevent the specific bug from recurring"""

    @pytest.mark.asyncio
    async def test_exact_bug_scenario(self):
        """
        Test the exact scenario that caused the bug:
        User: "help me navigate the install process"
        Bot: <asks which software>
        User: "of autobot"
        Bot: Should help with AutoBot installation, NOT exit
        """
        manager = ChatWorkflowManager()
        await manager.initialize()

        session_id = "test-exact-bug-scenario"

        # Step 1: User asks for help
        messages_1 = []
        async for msg in manager.process_message_stream(session_id, "help me navigate the install process"):
            messages_1.append(msg)

        assert len(messages_1) > 0, "Should respond to initial question"

        # Step 2: User clarifies "of autobot"
        messages_2 = []
        async for msg in manager.process_message_stream(session_id, "of autobot"):
            messages_2.append(msg)

        # CRITICAL ASSERTION: Verify bug is fixed
        all_content = " ".join([msg.content for msg in messages_2 if hasattr(msg, 'content')])

        # The bug was: Bot said "AutoBot out!" - this should NEVER happen
        assert "AutoBot out!" not in all_content, \
            "BUG REGRESSION: Bot should NEVER say 'AutoBot out!' for clarification 'of autobot'"

        assert "reached the end of our conversation" not in all_content.lower(), \
            "BUG REGRESSION: Bot should not think conversation ended on clarification"

        # Bot should provide helpful information about AutoBot installation
        assert len(all_content) > 20, "Should provide substantive response"


class TestSystemPromptLoading:
    """Test system prompt loading and fallback"""

    @pytest.mark.asyncio
    async def test_prompt_file_loads_successfully(self):
        """Test that the system prompt loads from prompts/chat/system_prompt.md"""
        from src.prompt_manager import get_prompt

        try:
            prompt = get_prompt("chat.system_prompt")
            assert len(prompt) > 0, "System prompt should not be empty"
            assert "AutoBot" in prompt, "System prompt should mention AutoBot"
            assert "NEVER end" in prompt or "never end" in prompt.lower(), \
                "System prompt should include conversation continuation instructions"
        except Exception as e:
            pytest.fail(f"Failed to load system prompt from file: {e}")

    @pytest.mark.asyncio
    async def test_conversation_continuation_rules_in_prompt(self):
        """Test that system prompt contains conversation continuation rules"""
        from src.prompt_manager import get_prompt

        prompt = get_prompt("chat.system_prompt")

        # Check for key conversation continuation instructions
        assert any(keyword in prompt.lower() for keyword in ["never end", "continuation", "don't end", "do not end"]), \
            "System prompt must include conversation continuation rules"

        assert any(keyword in prompt for keyword in ["goodbye", "exit", "quit"]), \
            "System prompt must define explicit exit criteria"


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "-s"])


if __name__ == "__main__":
    run_tests()
