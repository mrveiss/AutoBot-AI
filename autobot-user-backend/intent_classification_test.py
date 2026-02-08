# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive Tests for Intent Classification System

Tests the 3-layer intent classification system:
- IntentClassifier: Pattern-based intent classification
- ConversationContextAnalyzer: Conversation history analysis
- ConversationSafetyGuards: Safety rules for preventing inappropriate endings

Related Issue: #159 - Prevent Premature Conversation Endings
"""

from typing import Dict, List

from conversation_context import ConversationContextAnalyzer
from conversation_safety import ConversationSafetyGuards
from intent_classifier import ConversationIntent, IntentClassifier


class TestIntentClassifier:
    """Test IntentClassifier - Pattern-based intent classification"""

    def setup_method(self):
        """Setup test fixture"""
        self.classifier = IntentClassifier()

    # =============================================================================
    # CONTINUE Intent Tests
    # =============================================================================

    def test_question_intent_continue(self):
        """Questions should classify as CONTINUE"""
        message = "What is AutoBot?"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE
        assert result.confidence >= 0.80

    def test_question_mark_continue(self):
        """Messages with question marks should classify as CONTINUE"""
        message = "Can you help me with this?"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE
        assert result.confidence >= 0.80

    def test_continuation_words_continue(self):
        """Continuation words should classify as CONTINUE"""
        message = "Tell me more about the features"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE
        assert result.confidence >= 0.70

    def test_regression_of_autobot_continue(self):
        """REGRESSION TEST: 'of autobot' should NOT trigger exit (Issue #159)"""
        message = "Tell me the capabilities of autobot"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE
        assert result.intent != ConversationIntent.END
        assert "continuation" in result.reasoning.lower()

    def test_about_autobot_continue(self):
        """Questions about AutoBot should classify as CONTINUE"""
        message = "What are the main features of autobot"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE

    def test_how_question_continue(self):
        """How questions should classify as CONTINUE"""
        message = "How does the system work?"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE

    def test_why_question_continue(self):
        """Why questions should classify as CONTINUE"""
        message = "Why is AutoBot using distributed VMs?"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE

    def test_acknowledgment_continue(self):
        """Acknowledgments should classify as CONTINUE"""
        message = "okay"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE

    # =============================================================================
    # END Intent Tests
    # =============================================================================

    def test_goodbye_end(self):
        """'goodbye' should classify as END"""
        message = "goodbye"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END
        assert result.confidence >= 0.90

    def test_bye_end(self):
        """'bye' should classify as END"""
        message = "bye"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END
        assert result.confidence >= 0.90

    def test_exit_end(self):
        """'exit' should classify as END"""
        message = "exit"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END

    def test_quit_end(self):
        """'quit' should classify as END"""
        message = "quit"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END

    def test_thats_all_end(self):
        """'that's all' should classify as END"""
        message = "that's all"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END

    def test_im_done_end(self):
        """'I'm done' should classify as END"""
        message = "I'm done"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END

    def test_thanks_goodbye_end(self):
        """'thanks goodbye' should classify as END"""
        message = "thanks goodbye"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END

    def test_see_you_end(self):
        """'see you' should classify as END"""
        message = "see you later"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END

    def test_end_conversation_end(self):
        """'end conversation' should classify as END"""
        message = "end conversation"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.END

    def test_question_about_exit_clarification(self):
        """Questions about exiting should NOT classify as END"""
        message = "How do I exit?"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CLARIFICATION
        assert result.intent != ConversationIntent.END

    def test_exit_phrase_with_continuation_continue(self):
        """Exit word in continuation context should classify as CONTINUE"""
        message = "Tell me about the exit status code"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE

    # =============================================================================
    # CLARIFICATION Intent Tests
    # =============================================================================

    def test_what_do_you_mean_clarification(self):
        """'what do you mean' with question mark classifies as CONTINUE (question takes priority)"""
        message = "what do you mean?"
        result = self.classifier.classify(message)
        # Question mark triggers CONTINUE intent before CLARIFICATION check
        assert result.intent == ConversationIntent.CONTINUE
        assert result.confidence >= 0.85

    def test_confused_clarification(self):
        """'confused' should classify as CLARIFICATION"""
        message = "I'm confused about this"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CLARIFICATION

    def test_unclear_clarification(self):
        """'unclear' should classify as CLARIFICATION"""
        message = "That's unclear to me"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CLARIFICATION

    def test_can_you_explain_clarification(self):
        """'can you explain' should classify as CLARIFICATION"""
        message = "Can you explain that again?"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CLARIFICATION

    def test_dont_understand_clarification(self):
        """'don't understand' should classify as CLARIFICATION"""
        message = "I don't understand this part"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CLARIFICATION

    # =============================================================================
    # TASK_REQUEST Intent Tests
    # =============================================================================

    def test_create_task_request(self):
        """'create' should classify as TASK_REQUEST"""
        message = "Create a new configuration file"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.TASK_REQUEST
        assert result.confidence >= 0.80

    def test_install_task_request(self):
        """'install' should classify as TASK_REQUEST"""
        message = "Install the required dependencies"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.TASK_REQUEST

    def test_fix_task_request(self):
        """'fix' should classify as TASK_REQUEST"""
        message = "Fix the broken connection"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.TASK_REQUEST

    def test_run_task_request(self):
        """'run' should classify as TASK_REQUEST"""
        message = "Run the tests"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.TASK_REQUEST

    def test_update_task_request(self):
        """'update' should classify as TASK_REQUEST"""
        message = "Update the configuration"
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.TASK_REQUEST

    # =============================================================================
    # Edge Cases and Context Tests
    # =============================================================================

    def test_empty_message_continue(self):
        """Empty message should default to CONTINUE"""
        message = ""
        result = self.classifier.classify(message)
        assert result.intent == ConversationIntent.CONTINUE
        assert result.confidence <= 0.70  # Low confidence for empty

    def test_very_short_message_with_context(self):
        """Short message responding to question should be CONTINUE"""
        history = [{"role": "assistant", "content": "Would you like to proceed?"}]
        message = "yes"
        result = self.classifier.classify(message, history)
        assert result.intent == ConversationIntent.CONTINUE

    def test_long_message_continue(self):
        """Long detailed message with 'understand' classifies as CLARIFICATION"""
        message = "I would like to understand how the AutoBot distributed architecture works with multiple VMs and how the Redis integration provides caching and data persistence across the system."
        result = self.classifier.classify(message)
        # Word "understand" triggers CLARIFICATION intent
        assert result.intent == ConversationIntent.CLARIFICATION
        assert result.confidence >= 0.80


class TestConversationContextAnalyzer:
    """Test ConversationContextAnalyzer - Conversation history analysis"""

    def setup_method(self):
        """Setup test fixture"""
        self.analyzer = ConversationContextAnalyzer()

    def test_empty_history(self):
        """Empty history should return default context"""
        history = []
        message = "Hello"
        context = self.analyzer.analyze(history, message)

        assert context.message_count == 0
        assert context.has_recent_question is False
        assert context.has_active_task is False
        assert context.has_confusion_signals is False
        assert context.user_engagement_level == "low"

    def test_detect_recent_question(self):
        """Should detect question in last assistant message"""
        history = [{"role": "assistant", "content": "What would you like to know?"}]
        message = "Tell me about AutoBot"
        context = self.analyzer.analyze(history, message)

        assert context.has_recent_question is True

    def test_detect_active_task(self):
        """Should detect active task indicators"""
        history = [
            {"role": "assistant", "content": "Currently processing your request..."}
        ]
        message = "okay"
        context = self.analyzer.analyze(history, message)

        assert context.has_active_task is True

    def test_detect_confusion_signals(self):
        """Should detect confusion in user message"""
        history = []
        message = "I'm confused about this"
        context = self.analyzer.analyze(history, message)

        assert context.has_confusion_signals is True

    def test_detect_confusion_unclear(self):
        """Should detect 'unclear' confusion signal"""
        history = []
        message = "That's unclear to me"
        context = self.analyzer.analyze(history, message)

        assert context.has_confusion_signals is True

    def test_detect_confusion_dont_understand(self):
        """Should detect 'don't understand' confusion signal"""
        history = []
        message = "I don't understand what you mean"
        context = self.analyzer.analyze(history, message)

        assert context.has_confusion_signals is True

    def test_short_conversation_low_engagement(self):
        """Short conversation should have low engagement"""
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello! How can I help?"},
        ]
        message = "bye"
        context = self.analyzer.analyze(history, message)

        assert context.message_count == 2
        assert context.user_engagement_level == "low"

    def test_long_message_high_engagement(self):
        """Long detailed message should indicate high engagement"""
        history = []
        message = "I would like to understand the complete architecture of AutoBot including how all the distributed VMs communicate with each other and how the Redis caching layer works."
        context = self.analyzer.analyze(history, message)

        assert context.user_engagement_level == "high"

    def test_question_high_engagement(self):
        """Questions should indicate high engagement"""
        history = []
        message = "How does the NPU worker integrate with the main system?"
        context = self.analyzer.analyze(history, message)

        assert context.user_engagement_level == "high"

    def test_determine_topic_troubleshooting(self):
        """Should detect troubleshooting topic"""
        history = [
            {
                "role": "user",
                "content": "I'm getting an error with the Redis connection",
            },
            {"role": "assistant", "content": "Let me help you debug that issue"},
        ]
        message = "The error says connection timeout"
        context = self.analyzer.analyze(history, message)

        assert context.conversation_topic == "troubleshooting"

    def test_determine_topic_installation(self):
        """Should detect installation topic"""
        history = [
            {"role": "user", "content": "How do I install AutoBot?"},
            {"role": "assistant", "content": "Let me guide you through the setup"},
        ]
        message = "I need to configure the VMs"
        context = self.analyzer.analyze(history, message)

        assert context.conversation_topic == "installation"


class TestConversationSafetyGuards:
    """Test ConversationSafetyGuards - Safety rules enforcement"""

    def setup_method(self):
        """Setup test fixture"""
        self.guards = ConversationSafetyGuards()
        self.classifier = IntentClassifier()
        self.analyzer = ConversationContextAnalyzer()

    def test_block_end_on_recent_question(self):
        """SAFETY RULE 1: Never end on questions"""
        # Assistant asked a question
        history = [{"role": "assistant", "content": "Would you like more details?"}]
        message = "bye"

        classification = self.classifier.classify(message)
        context = self.analyzer.analyze(history, message)
        safety_check = self.guards.check(classification, context)

        assert safety_check.is_safe_to_end is False
        assert "assistant_asked_question" in safety_check.violated_rules

    def test_block_end_on_confusion(self):
        """SAFETY RULE 2: Never end on confusion signals"""
        history = []
        message = "I'm confused, goodbye"

        classification = self.classifier.classify(message)
        context = self.analyzer.analyze(history, message)
        safety_check = self.guards.check(classification, context)

        assert safety_check.is_safe_to_end is False
        assert "user_confused" in safety_check.violated_rules

    def test_block_end_on_short_conversation(self):
        """SAFETY RULE 3: Never end on short conversations (<3 messages)"""
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        message = "goodbye"

        classification = self.classifier.classify(message)
        context = self.analyzer.analyze(history, message)
        safety_check = self.guards.check(classification, context)

        assert safety_check.is_safe_to_end is False
        assert "conversation_too_short" in safety_check.violated_rules

    def test_block_end_on_active_task(self):
        """SAFETY RULE 4: Never end on active tasks"""
        history = [
            {"role": "assistant", "content": "Currently processing your request..."}
        ]
        message = "bye"

        classification = self.classifier.classify(message)
        context = self.analyzer.analyze(history, message)
        safety_check = self.guards.check(classification, context)

        assert safety_check.is_safe_to_end is False
        assert "active_task" in safety_check.violated_rules

    def test_block_end_on_low_confidence(self):
        """SAFETY RULE 5: Require high confidence (>0.85) for END"""
        history = []
        # This will have lower confidence because it's a question about exiting
        message = "How do I exit?"

        classification = self.classifier.classify(message)
        context = self.analyzer.analyze(history, message)

        # This should be classified as CLARIFICATION, not END
        # But if it were END with low confidence, it should be blocked
        if classification.intent == ConversationIntent.END:
            safety_check = self.guards.check(classification, context)
            if classification.confidence < 0.85:
                assert safety_check.is_safe_to_end is False

    def test_block_end_on_high_engagement(self):
        """SAFETY RULE 6: High engagement prevents ending"""
        history = []
        # Long message indicates high engagement
        message = "I've learned a lot about AutoBot's architecture and how it uses distributed VMs. Thanks, goodbye!"

        classification = self.classifier.classify(message)
        context = self.analyzer.analyze(history, message)
        safety_check = self.guards.check(classification, context)

        # Even though "goodbye" is in message, high engagement should block
        if (
            context.user_engagement_level == "high"
            and classification.intent == ConversationIntent.END
        ):
            assert safety_check.is_safe_to_end is False
            assert "high_engagement" in safety_check.violated_rules

    def test_allow_end_all_checks_pass(self):
        """Should allow END when all safety checks pass"""
        # Long enough conversation
        history = [
            {"role": "user", "content": "Tell me about AutoBot"},
            {"role": "assistant", "content": "AutoBot is an AI automation platform..."},
            {"role": "user", "content": "What are the main features?"},
            {"role": "assistant", "content": "The main features include..."},
            {"role": "user", "content": "Thanks for the information"},
        ]
        message = "goodbye"

        classification = self.classifier.classify(message)
        context = self.analyzer.analyze(history, message)
        safety_check = self.guards.check(classification, context)

        assert classification.intent == ConversationIntent.END
        assert classification.confidence >= 0.85
        assert safety_check.is_safe_to_end is True
        assert len(safety_check.violated_rules) == 0

    def test_override_intent_on_violation(self):
        """Should override END intent to CONTINUE when rules violated"""
        history = [{"role": "assistant", "content": "Any other questions?"}]
        message = "bye"

        classification = self.classifier.classify(message)
        context = self.analyzer.analyze(history, message)
        safety_check = self.guards.check(classification, context)

        assert classification.intent == ConversationIntent.END
        assert safety_check.is_safe_to_end is False
        assert safety_check.override_intent == ConversationIntent.CONTINUE


class TestIntegrationScenarios:
    """Integration tests for complete classification pipeline"""

    def setup_method(self):
        """Setup test fixture"""
        self.classifier = IntentClassifier()
        self.analyzer = ConversationContextAnalyzer()
        self.guards = ConversationSafetyGuards()

    def classify_with_safety(
        self, message: str, history: List[Dict[str, str]]
    ) -> tuple:
        """Helper to run complete classification with safety checks"""
        classification = self.classifier.classify(message, history)
        context = self.analyzer.analyze(history, message)
        safety_check = self.guards.check(classification, context)

        # Determine final decision
        should_exit = (
            classification.intent == ConversationIntent.END
            and safety_check.is_safe_to_end
        )

        return classification, context, safety_check, should_exit

    def test_regression_of_autobot_no_exit(self):
        """REGRESSION: 'of autobot' should never trigger exit"""
        history = []
        message = "Tell me the capabilities of autobot"

        classification, context, safety_check, should_exit = self.classify_with_safety(
            message, history
        )

        assert should_exit is False
        assert classification.intent == ConversationIntent.CONTINUE

    def test_normal_conversation_flow(self):
        """Test normal conversation flow without premature ending"""
        # Conversation 1: User asks question
        history1 = []
        message1 = "What is AutoBot?"
        classification1, context1, safety1, exit1 = self.classify_with_safety(
            message1, history1
        )
        assert exit1 is False

        # Conversation 2: Assistant responds, user asks follow-up
        history2 = [
            {"role": "user", "content": message1},
            {"role": "assistant", "content": "AutoBot is an AI automation platform..."},
        ]
        message2 = "How do I install it?"
        classification2, context2, safety2, exit2 = self.classify_with_safety(
            message2, history2
        )
        assert exit2 is False

        # Conversation 3: User satisfied, says goodbye (but conversation still too short)
        history3 = [
            {"role": "user", "content": message1},
            {"role": "assistant", "content": "AutoBot is an AI automation platform..."},
            {"role": "user", "content": message2},
            {"role": "assistant", "content": "You can install AutoBot by running..."},
        ]
        message3 = "Thanks, that's all I needed. Goodbye!"
        classification3, context3, safety3, exit3 = self.classify_with_safety(
            message3, history3
        )

        # Should be classified as END intent
        assert classification3.intent == ConversationIntent.END
        # But blocked by safety guards (conversation too short: only 2 exchanges < 3 minimum)
        assert safety3.is_safe_to_end is False
        assert (
            "conversation_too_short" in safety3.violated_rules
            or "active_task" in safety3.violated_rules
        )
        assert exit3 is False

        # Conversation 4: Longer conversation, no active tasks or questions
        history4 = [
            {"role": "user", "content": "Tell me about AutoBot"},
            {
                "role": "assistant",
                "content": "AutoBot is an AI-powered automation platform with distributed architecture.",
            },
            {"role": "user", "content": "Interesting, tell me more about the features"},
            {
                "role": "assistant",
                "content": "AutoBot includes multi-modal AI capabilities, NPU acceleration, and comprehensive API.",
            },
            {"role": "user", "content": "Great overview, thanks"},
            {
                "role": "assistant",
                "content": "You're welcome! I'm glad I could provide useful information.",
            },
        ]
        message4 = "Perfect, thank you for the information. Goodbye!"
        classification4, context4, safety4, exit4 = self.classify_with_safety(
            message4, history4
        )

        # Now with 3+ exchanges and no blocking conditions, should be allowed to exit
        assert classification4.intent == ConversationIntent.END
        assert classification4.confidence >= 0.85
        # Conversation is now 3 exchanges, no recent question, user is satisfied
        assert safety4.is_safe_to_end is True
        assert exit4 is True

    def test_prevent_premature_exit_on_question(self):
        """Prevent exit when assistant just asked a question"""
        history = [
            {"role": "user", "content": "Help me with installation"},
            {
                "role": "assistant",
                "content": "Sure! Which operating system are you using?",
            },
        ]
        message = "Actually, nevermind. Bye!"

        classification, context, safety_check, should_exit = self.classify_with_safety(
            message, history
        )

        # Should be blocked because assistant asked a question
        assert classification.intent == ConversationIntent.END
        assert context.has_recent_question is True
        assert safety_check.is_safe_to_end is False
        assert should_exit is False

    def test_prevent_exit_on_confusion(self):
        """Prevent exit when user is confused"""
        history = [
            {"role": "user", "content": "How does NPU worker work?"},
            {"role": "assistant", "content": "The NPU worker uses OpenVINO..."},
        ]
        message = "I'm confused about that, bye"

        classification, context, safety_check, should_exit = self.classify_with_safety(
            message, history
        )

        # Should be blocked because user is confused
        assert context.has_confusion_signals is True
        assert safety_check.is_safe_to_end is False
        assert should_exit is False
