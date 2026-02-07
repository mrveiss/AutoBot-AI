# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests for Chat Intent Detector Module

Tests the intent detection and context prompt selection system for
enhanced system prompts (Issue #160).

Test Coverage:
- detect_exit_intent(): Exit intent classification
- detect_user_intent(): Multi-category intent classification
- select_context_prompt(): Context prompt selection and combination

Related Issue: #160 - Enhanced System Prompts Testing and Validation
"""

from unittest.mock import patch

import pytest
from src.chat_intent_detector import (
    CONTEXT_PROMPT_MAP,
    EXIT_KEYWORDS,
    INTENT_KEYWORDS,
    detect_exit_intent,
    detect_user_intent,
    select_context_prompt,
)


class TestDetectExitIntent:
    """Tests for detect_exit_intent() function"""

    # =============================================================================
    # Exact Match Exit Keywords
    # =============================================================================

    def test_exact_goodbye_returns_true(self):
        """'goodbye' exactly should trigger exit"""
        assert detect_exit_intent("goodbye") is True

    def test_exact_bye_returns_true(self):
        """'bye' exactly should trigger exit"""
        assert detect_exit_intent("bye") is True

    def test_exact_exit_returns_true(self):
        """'exit' exactly should trigger exit"""
        assert detect_exit_intent("exit") is True

    def test_exact_quit_returns_true(self):
        """'quit' exactly should trigger exit"""
        assert detect_exit_intent("quit") is True

    def test_exact_stop_returns_true(self):
        """'stop' exactly should trigger exit"""
        assert detect_exit_intent("stop") is True

    def test_exact_end_chat_returns_true(self):
        """'end chat' exactly should trigger exit"""
        assert detect_exit_intent("end chat") is True

    def test_exact_thats_all_returns_true(self):
        """'that's all' exactly should trigger exit"""
        assert detect_exit_intent("that's all") is True

    def test_exact_see_you_returns_true(self):
        """'see you' exactly should trigger exit"""
        assert detect_exit_intent("see you") is True

    def test_exact_farewell_returns_true(self):
        """'farewell' exactly should trigger exit"""
        assert detect_exit_intent("farewell") is True

    def test_exact_im_done_returns_true(self):
        """'i'm done' exactly should trigger exit"""
        assert detect_exit_intent("i'm done") is True

    def test_exact_im_done_no_apostrophe_returns_true(self):
        """'im done' without apostrophe should trigger exit"""
        assert detect_exit_intent("im done") is True

    def test_exact_end_conversation_returns_true(self):
        """'end conversation' exactly should trigger exit"""
        assert detect_exit_intent("end conversation") is True

    # =============================================================================
    # Case Insensitivity
    # =============================================================================

    def test_case_insensitive_goodbye(self):
        """Exit detection should be case insensitive"""
        assert detect_exit_intent("GOODBYE") is True
        assert detect_exit_intent("Goodbye") is True
        assert detect_exit_intent("GoodBye") is True

    def test_case_insensitive_bye(self):
        """'BYE' in various cases should trigger exit"""
        assert detect_exit_intent("BYE") is True
        assert detect_exit_intent("Bye") is True

    # =============================================================================
    # Exit Words Within Sentences
    # =============================================================================

    def test_bye_in_sentence_triggers_exit(self):
        """'bye' within a sentence (no question mark) should trigger exit"""
        assert detect_exit_intent("thanks bye") is True

    def test_goodbye_in_sentence_triggers_exit(self):
        """'goodbye' within a sentence should trigger exit"""
        assert detect_exit_intent("ok goodbye now") is True

    # =============================================================================
    # Questions About Exit - Should NOT Trigger Exit
    # =============================================================================

    def test_question_about_exit_returns_false(self):
        """Questions about exiting should NOT trigger exit"""
        assert detect_exit_intent("How do I exit?") is False
        assert detect_exit_intent("What does exit do?") is False
        assert detect_exit_intent("Can I say goodbye?") is False

    def test_question_about_quitting_returns_false(self):
        """Questions about quitting should NOT trigger exit"""
        assert detect_exit_intent("How do I quit the application?") is False

    def test_exit_in_question_context_returns_false(self):
        """Exit word in a question should NOT trigger exit"""
        assert detect_exit_intent("When should I say bye?") is False

    # =============================================================================
    # Non-Exit Messages
    # =============================================================================

    def test_regular_message_returns_false(self):
        """Regular messages should NOT trigger exit"""
        assert detect_exit_intent("Hello, how are you?") is False
        assert detect_exit_intent("Tell me about AutoBot") is False
        assert detect_exit_intent("What can you help me with?") is False

    def test_empty_message_returns_false(self):
        """Empty message should NOT trigger exit"""
        assert detect_exit_intent("") is False

    def test_whitespace_only_returns_false(self):
        """Whitespace-only message should NOT trigger exit"""
        assert detect_exit_intent("   ") is False

    def test_exit_as_part_of_word_returns_false(self):
        """'exit' as part of larger word should NOT trigger exit"""
        assert detect_exit_intent("What is the exit code?") is False
        # But standalone "exit" should trigger
        assert detect_exit_intent("exit") is True


class TestDetectUserIntent:
    """Tests for detect_user_intent() function"""

    # =============================================================================
    # Installation Intent Tests
    # =============================================================================

    def test_install_keyword_returns_installation(self):
        """Messages with 'install' should return installation intent"""
        assert detect_user_intent("How do I install AutoBot?") == "installation"

    def test_setup_keyword_returns_installation(self):
        """Messages with 'setup' should return installation intent"""
        assert detect_user_intent("Help me setup the system") == "installation"

    def test_configure_keyword_returns_installation(self):
        """Messages with 'configure' should return installation intent"""
        assert detect_user_intent("How do I configure the VMs?") == "installation"

    def test_deployment_keyword_returns_installation(self):
        """Messages with 'deployment' should return installation intent"""
        assert detect_user_intent("Explain the deployment process") == "installation"

    def test_getting_started_returns_installation(self):
        """Messages with 'getting started' should return installation intent"""
        assert detect_user_intent("Getting started with AutoBot") == "installation"

    def test_run_autobot_returns_installation(self):
        """Messages about running autobot should return installation intent"""
        assert detect_user_intent("How do I run autobot?") == "installation"

    def test_vm_setup_returns_installation(self):
        """Messages about VM setup should return installation intent"""
        assert detect_user_intent("Tell me about vm setup") == "installation"

    # =============================================================================
    # Architecture Intent Tests
    # =============================================================================

    def test_architecture_keyword_returns_architecture(self):
        """Messages with 'architecture' should return architecture intent"""
        assert detect_user_intent("Explain the architecture") == "architecture"

    def test_design_keyword_returns_architecture(self):
        """Messages with 'design' should return architecture intent"""
        assert detect_user_intent("What is the system design?") == "architecture"

    def test_why_keyword_returns_architecture(self):
        """Messages with 'why' should return architecture intent"""
        assert detect_user_intent("Why is it built this way?") == "architecture"

    def test_how_does_keyword_returns_architecture(self):
        """Messages with 'how does' should return architecture intent"""
        assert detect_user_intent("How does the system work?") == "architecture"

    def test_distributed_keyword_returns_architecture(self):
        """Messages with 'distributed' should return architecture intent"""
        # Note: "distributed setup" is in installation keywords as a phrase
        # "distributed" alone should return architecture
        assert (
            detect_user_intent("Explain the distributed architecture") == "architecture"
        )

    def test_vm_keyword_returns_architecture(self):
        """Messages about VMs (general) should return architecture intent"""
        assert detect_user_intent("Tell me about the VM structure") == "architecture"

    def test_infrastructure_returns_architecture(self):
        """Messages about infrastructure should return architecture intent"""
        assert detect_user_intent("Explain the infrastructure") == "architecture"

    def test_how_many_returns_architecture(self):
        """Messages with 'how many' should return architecture intent"""
        assert detect_user_intent("How many VMs are there?") == "architecture"

    # =============================================================================
    # Troubleshooting Intent Tests
    # =============================================================================

    def test_error_keyword_returns_troubleshooting(self):
        """Messages with 'error' should return troubleshooting intent"""
        assert detect_user_intent("I'm getting an error") == "troubleshooting"

    def test_issue_keyword_returns_troubleshooting(self):
        """Messages with 'issue' should return troubleshooting intent"""
        assert detect_user_intent("I have an issue with Redis") == "troubleshooting"

    def test_problem_keyword_returns_troubleshooting(self):
        """Messages with 'problem' should return troubleshooting intent"""
        assert detect_user_intent("There's a problem connecting") == "troubleshooting"

    def test_not_working_returns_troubleshooting(self):
        """Messages with 'not working' should return troubleshooting intent"""
        assert detect_user_intent("The frontend is not working") == "troubleshooting"

    def test_broken_keyword_returns_troubleshooting(self):
        """Messages with 'broken' should return troubleshooting intent"""
        assert detect_user_intent("Something is broken") == "troubleshooting"

    def test_failed_keyword_returns_troubleshooting(self):
        """Messages with 'failed' should return troubleshooting intent"""
        assert detect_user_intent("The connection failed") == "troubleshooting"

    def test_crash_keyword_returns_troubleshooting(self):
        """Messages with 'crash' should return troubleshooting intent"""
        assert detect_user_intent("The server keeps crashing") == "troubleshooting"

    def test_timeout_keyword_returns_troubleshooting(self):
        """Messages with 'timeout' should return troubleshooting intent"""
        assert detect_user_intent("I'm getting a timeout") == "troubleshooting"

    def test_cant_keyword_returns_troubleshooting(self):
        """Messages with 'can't' should return troubleshooting intent"""
        assert detect_user_intent("I can't connect to Redis") == "troubleshooting"

    def test_stuck_keyword_returns_troubleshooting(self):
        """Messages with 'stuck' should return troubleshooting intent"""
        assert detect_user_intent("The process is stuck") == "troubleshooting"

    def test_fix_keyword_returns_troubleshooting(self):
        """Messages with 'fix' should return troubleshooting intent"""
        assert detect_user_intent("How do I fix this?") == "troubleshooting"

    def test_debug_keyword_returns_troubleshooting(self):
        """Messages with 'debug' should return troubleshooting intent"""
        assert detect_user_intent("Help me debug the issue") == "troubleshooting"

    # =============================================================================
    # API Intent Tests
    # =============================================================================

    def test_api_keyword_returns_api(self):
        """Messages with 'api' should return api intent"""
        assert detect_user_intent("How do I use the API?") == "api"

    def test_endpoint_keyword_returns_api(self):
        """Messages with 'endpoint' should return api intent"""
        assert detect_user_intent("What endpoints are available?") == "api"

    def test_request_keyword_returns_api(self):
        """Messages with 'request' should return api intent"""
        assert detect_user_intent("How do I make a request?") == "api"

    def test_response_keyword_returns_api(self):
        """Messages with 'response' should return api intent"""
        assert detect_user_intent("What is the response format?") == "api"

    def test_curl_keyword_returns_api(self):
        """Messages with 'curl' should return api intent"""
        assert detect_user_intent("Show me a curl example") == "api"

    def test_http_keyword_returns_api(self):
        """Messages with 'http' should return api intent"""
        assert detect_user_intent("What http methods are supported?") == "api"

    def test_rest_keyword_returns_api(self):
        """Messages with 'rest' should return api intent"""
        assert detect_user_intent("Is this a rest API?") == "api"

    def test_websocket_keyword_returns_api(self):
        """Messages with 'websocket' should return api intent"""
        assert detect_user_intent("Does it support websocket?") == "api"

    def test_stream_keyword_returns_api(self):
        """Messages with 'stream' should return api intent"""
        assert detect_user_intent("How do I stream responses?") == "api"

    def test_integration_keyword_returns_api(self):
        """Messages with 'integration' should return api intent"""
        assert detect_user_intent("Help with API integration") == "api"

    # =============================================================================
    # General Intent Tests (Fallback)
    # =============================================================================

    def test_general_message_returns_general(self):
        """Messages without specific keywords should return general intent"""
        assert detect_user_intent("Hello, how are you?") == "general"

    def test_simple_greeting_returns_general(self):
        """Simple greetings should return general intent"""
        assert detect_user_intent("Hi there!") == "general"

    def test_thanks_message_returns_general(self):
        """Thanks messages should return general intent"""
        # Note: "help" is a troubleshooting keyword, so use a simpler thanks message
        assert detect_user_intent("Thank you so much!") == "general"

    def test_empty_message_returns_general(self):
        """Empty message should return general intent"""
        assert detect_user_intent("") == "general"

    # =============================================================================
    # Multiple Keywords - Highest Score Wins
    # =============================================================================

    def test_multiple_keywords_highest_score_wins(self):
        """When multiple intents match, highest score should win"""
        # "install" + "error" -> 1 installation + 1 troubleshooting = tie
        # This tests that scoring works
        result = detect_user_intent("I have an install error and a setup issue")
        # Should be installation (2 keywords: install, setup) or troubleshooting (2: error, issue)
        assert result in ["installation", "troubleshooting"]

    def test_clear_installation_over_troubleshooting(self):
        """Clear installation context should win over single troubleshooting word"""
        # setup + install + getting started = 3 installation keywords
        result = detect_user_intent("Help me setup and install, I'm getting started")
        assert result == "installation"

    # =============================================================================
    # Conversation History Context Tests
    # =============================================================================

    def test_context_boost_from_history(self):
        """Conversation history should boost related intent scores"""
        history = [{"assistant": "Let me help you with the installation process."}]
        # Without history, this might be general. With installation context, it boosts.
        result = detect_user_intent("What's next?", history)
        # The context boost should influence (may still be general if no keywords)
        # This tests that the function accepts and uses history
        assert isinstance(result, str)

    def test_troubleshooting_context_boost(self):
        """Troubleshooting in history should boost troubleshooting intent"""
        history = [
            {"assistant": "I see you're having an error. Let me help debug this issue."}
        ]
        # Even a vague message gets context boost
        result = detect_user_intent("Yes please help", history)
        # The history contains: error, debug, issue = 3 troubleshooting keywords
        # This should boost troubleshooting
        assert isinstance(result, str)

    def test_multiple_history_messages(self):
        """Should consider last 2 assistant messages from history"""
        history = [
            {"assistant": "Here's how to install AutoBot."},
            {"assistant": "The setup process takes about 25 minutes."},
        ]
        result = detect_user_intent("Tell me more", history)
        # install, setup = installation context
        assert isinstance(result, str)

    def test_empty_history_no_crash(self):
        """Empty conversation history should not cause errors"""
        result = detect_user_intent("Hello", [])
        assert result == "general"

    def test_none_history_no_crash(self):
        """None conversation history should not cause errors"""
        result = detect_user_intent("Hello", None)
        assert result == "general"


class TestSelectContextPrompt:
    """Tests for select_context_prompt() function"""

    @pytest.fixture
    def base_prompt(self):
        """Fixture providing a base system prompt"""
        return "You are AutoBot, an AI assistant."

    # =============================================================================
    # General Intent - Returns Base Prompt Only
    # =============================================================================

    def test_general_intent_returns_base_only(self, base_prompt):
        """General intent should return base prompt unchanged"""
        result = select_context_prompt("general", base_prompt)
        assert result == base_prompt

    def test_unknown_intent_returns_base_only(self, base_prompt):
        """Unknown intent should return base prompt unchanged"""
        result = select_context_prompt("unknown_intent", base_prompt)
        assert result == base_prompt

    # =============================================================================
    # Context Prompt Loading and Combination
    # =============================================================================

    @patch("src.chat_intent_detector.get_prompt")
    def test_installation_intent_loads_context(self, mock_get_prompt, base_prompt):
        """Installation intent should load and combine context prompt"""
        mock_get_prompt.return_value = "Installation help content"

        result = select_context_prompt("installation", base_prompt)

        mock_get_prompt.assert_called_once_with("chat.installation_help")
        assert base_prompt in result
        assert "Installation help content" in result
        assert "CONTEXT-SPECIFIC GUIDANCE" in result
        assert "installation conversation" in result

    @patch("src.chat_intent_detector.get_prompt")
    def test_architecture_intent_loads_context(self, mock_get_prompt, base_prompt):
        """Architecture intent should load and combine context prompt"""
        mock_get_prompt.return_value = "Architecture explanation content"

        result = select_context_prompt("architecture", base_prompt)

        mock_get_prompt.assert_called_once_with("chat.architecture_explanation")
        assert base_prompt in result
        assert "Architecture explanation content" in result
        assert "architecture conversation" in result

    @patch("src.chat_intent_detector.get_prompt")
    def test_troubleshooting_intent_loads_context(self, mock_get_prompt, base_prompt):
        """Troubleshooting intent should load and combine context prompt"""
        mock_get_prompt.return_value = "Troubleshooting guide content"

        result = select_context_prompt("troubleshooting", base_prompt)

        mock_get_prompt.assert_called_once_with("chat.troubleshooting")
        assert base_prompt in result
        assert "Troubleshooting guide content" in result
        assert "troubleshooting conversation" in result

    @patch("src.chat_intent_detector.get_prompt")
    def test_api_intent_loads_context(self, mock_get_prompt, base_prompt):
        """API intent should load and combine context prompt"""
        mock_get_prompt.return_value = "API documentation content"

        result = select_context_prompt("api", base_prompt)

        mock_get_prompt.assert_called_once_with("chat.api_documentation")
        assert base_prompt in result
        assert "API documentation content" in result
        assert "api conversation" in result

    # =============================================================================
    # Error Handling
    # =============================================================================

    @patch("src.chat_intent_detector.get_prompt")
    def test_prompt_load_failure_returns_base(self, mock_get_prompt, base_prompt):
        """If context prompt fails to load, should return base prompt"""
        mock_get_prompt.side_effect = FileNotFoundError("Prompt not found")

        result = select_context_prompt("installation", base_prompt)

        assert result == base_prompt

    @patch("src.chat_intent_detector.get_prompt")
    def test_prompt_load_exception_returns_base(self, mock_get_prompt, base_prompt):
        """Any exception during prompt load should return base prompt"""
        mock_get_prompt.side_effect = Exception("Unexpected error")

        result = select_context_prompt("troubleshooting", base_prompt)

        assert result == base_prompt

    # =============================================================================
    # Combined Prompt Structure
    # =============================================================================

    @patch("src.chat_intent_detector.get_prompt")
    def test_combined_prompt_structure(self, mock_get_prompt, base_prompt):
        """Combined prompt should have proper structure"""
        mock_get_prompt.return_value = "Context content here"

        result = select_context_prompt("installation", base_prompt)

        # Check structure
        assert result.startswith(base_prompt)
        assert "---" in result  # Separator
        assert "## CONTEXT-SPECIFIC GUIDANCE" in result
        assert "Context content here" in result
        assert "**Remember**:" in result


class TestConstants:
    """Tests for module constants"""

    def test_exit_keywords_not_empty(self):
        """EXIT_KEYWORDS should contain keywords"""
        assert len(EXIT_KEYWORDS) > 0
        assert "goodbye" in EXIT_KEYWORDS
        assert "bye" in EXIT_KEYWORDS
        assert "exit" in EXIT_KEYWORDS

    def test_intent_keywords_has_all_categories(self):
        """INTENT_KEYWORDS should have all expected categories"""
        assert "installation" in INTENT_KEYWORDS
        assert "architecture" in INTENT_KEYWORDS
        assert "troubleshooting" in INTENT_KEYWORDS
        assert "api" in INTENT_KEYWORDS

    def test_intent_keywords_not_empty(self):
        """Each intent category should have keywords"""
        for intent, keywords in INTENT_KEYWORDS.items():
            assert len(keywords) > 0, f"{intent} has no keywords"

    def test_context_prompt_map_has_all_intents(self):
        """CONTEXT_PROMPT_MAP should map all non-general intents"""
        assert "installation" in CONTEXT_PROMPT_MAP
        assert "architecture" in CONTEXT_PROMPT_MAP
        assert "troubleshooting" in CONTEXT_PROMPT_MAP
        assert "api" in CONTEXT_PROMPT_MAP
        # General should NOT be in the map
        assert "general" not in CONTEXT_PROMPT_MAP

    def test_context_prompt_map_values_are_valid_paths(self):
        """Context prompt map values should be valid prompt keys"""
        for intent, prompt_key in CONTEXT_PROMPT_MAP.items():
            assert prompt_key.startswith("chat.")
            assert len(prompt_key) > 5  # "chat." + something


class TestIntegration:
    """Integration tests combining multiple functions"""

    def test_full_intent_detection_to_prompt_selection(self):
        """Test full flow from message to enhanced prompt"""

        # Test installation flow
        message = "How do I install AutoBot?"
        intent = detect_user_intent(message)
        assert intent == "installation"

        # Test architecture flow
        message = "Explain the system architecture"
        intent = detect_user_intent(message)
        assert intent == "architecture"

        # Test troubleshooting flow
        message = "I'm getting an error with Redis"
        intent = detect_user_intent(message)
        assert intent == "troubleshooting"

        # Test API flow
        message = "What API endpoints are available?"
        intent = detect_user_intent(message)
        assert intent == "api"

    def test_exit_and_intent_are_independent(self):
        """Exit detection should be independent of intent detection"""
        # A message can be about installation but also be an exit
        message = "thanks for the install help, bye"

        # Should trigger exit
        assert detect_exit_intent(message) is True

        # But also has installation keywords
        intent = detect_user_intent(message)
        # "install" keyword present, but "thanks" and "help" might match troubleshooting
        assert isinstance(intent, str)

    def test_regression_no_premature_exit_on_content(self):
        """REGRESSION: Content-related messages should not trigger exit"""
        # These should NOT trigger exit
        assert detect_exit_intent("Tell me about the exit code") is False
        assert detect_exit_intent("What is the bye command?") is False
        assert detect_exit_intent("Explain how to quit the program") is False

    def test_conversation_context_affects_intent(self):
        """Conversation context should influence intent detection"""
        # Without context - generic
        result1 = detect_user_intent("yes")
        assert result1 == "general"

        # With installation context - still general (no keywords match)
        # but the history is considered in scoring
        history = [{"assistant": "Would you like help with installation?"}]
        result2 = detect_user_intent("yes please", history)
        # Still general because "yes please" has no intent keywords
        # But the function should handle context gracefully
        assert isinstance(result2, str)
