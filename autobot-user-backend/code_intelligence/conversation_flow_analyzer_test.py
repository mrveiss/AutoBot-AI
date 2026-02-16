# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Conversation Flow Analyzer

Tests the conversation flow analysis functionality including:
- Intent classification
- Response type classification
- Flow parsing and analysis
- Pattern extraction
- Bottleneck detection
- Optimization suggestions

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #227)
"""

from datetime import datetime

import pytest

from backend.code_intelligence.conversation_flow_analyzer import (
    AnalysisResult,
    Bottleneck,
    BottleneckType,
    ConversationFlow,
    ConversationFlowAnalyzer,
    ConversationMessage,
    FlowPattern,
    FlowState,
    IntentCategory,
    IntentClassifier,
    Optimization,
    OptimizationType,
    ResponseClassifier,
    ResponseType,
    analyze_conversations,
    classify_intent,
    classify_response,
    get_bottleneck_types,
    get_intent_categories,
    get_optimization_types,
    get_response_types,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_conversation():
    """Sample conversation for testing."""
    return [
        {"role": "user", "content": "Hello, how are you?"},
        {
            "role": "assistant",
            "content": "Hello! I'm doing well. How can I help you today?",
        },
        {"role": "user", "content": "I need help installing AutoBot"},
        {
            "role": "assistant",
            "content": "I'd be happy to help you install AutoBot. "
            "Which operating system are you using?",
        },
        {"role": "user", "content": "I'm using Ubuntu 22.04"},
        {
            "role": "assistant",
            "content": "Great! For Ubuntu, you can run: bash setup.sh --full",
        },
        {"role": "user", "content": "Thanks, that worked! Goodbye"},
        {"role": "assistant", "content": "You're welcome! Goodbye, take care!"},
    ]


@pytest.fixture
def error_conversation():
    """Conversation with errors for testing."""
    return [
        {"role": "user", "content": "Help me fix this error"},
        {
            "role": "assistant",
            "content": "I see you're having an issue. What error are you seeing?",
        },
        {"role": "user", "content": "I get a timeout error when connecting"},
        {
            "role": "assistant",
            "content": "I apologize, I'm unable to connect to the service. "
            "The error indicates a timeout.",
        },
        {"role": "user", "content": "What do you mean? I don't understand"},
        {
            "role": "assistant",
            "content": "Sorry, I couldn't find a solution. "
            "Let me try a different approach.",
        },
        {"role": "user", "content": "This is still not working"},
        {
            "role": "assistant",
            "content": "I apologize for the continued issues. "
            "Would you like to escalate this?",
        },
    ]


@pytest.fixture
def multiple_conversations():
    """Multiple conversations for pattern analysis."""
    conversations = []

    # Add 5 similar installation conversations
    for i in range(5):
        conversations.append(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hello! How can I help?"},
                {"role": "user", "content": "I need to install AutoBot"},
                {"role": "assistant", "content": "I can help with installation."},
                {"role": "user", "content": f"Thanks! Session {i}"},
            ]
        )

    # Add 3 troubleshooting conversations
    for i in range(3):
        conversations.append(
            [
                {"role": "user", "content": "I have an error"},
                {"role": "assistant", "content": "What error are you seeing?"},
                {"role": "user", "content": "Connection timeout"},
                {"role": "assistant", "content": "Let me help you fix that."},
            ]
        )

    return conversations


@pytest.fixture
def analyzer():
    """Create a ConversationFlowAnalyzer instance."""
    return ConversationFlowAnalyzer(
        min_pattern_occurrences=2,
        slow_response_threshold_ms=1000.0,
        max_turns_threshold=10,
        clarification_threshold=2,
    )


# =============================================================================
# Intent Classification Tests
# =============================================================================


class TestIntentCategory:
    """Tests for IntentCategory enum."""

    def test_all_categories_defined(self):
        """Test that all expected categories are defined."""
        expected = [
            "installation",
            "architecture",
            "troubleshooting",
            "api_usage",
            "security",
            "performance",
            "knowledge_base",
            "code_analysis",
            "research",
            "general",
            "greeting",
            "farewell",
            "clarification",
            "confirmation",
            "unknown",
        ]
        actual = [c.value for c in IntentCategory]
        for exp in expected:
            assert exp in actual, f"Missing category: {exp}"

    def test_category_values_are_strings(self):
        """Test that all category values are strings."""
        for category in IntentCategory:
            assert isinstance(category.value, str)


class TestIntentClassifier:
    """Tests for IntentClassifier."""

    def test_classify_greeting(self):
        """Test greeting intent classification."""
        intent, confidence = IntentClassifier.classify("Hello")
        assert intent == IntentCategory.GREETING
        assert confidence > 0

    def test_classify_farewell(self):
        """Test farewell intent classification."""
        intent, confidence = IntentClassifier.classify("Goodbye")
        assert intent == IntentCategory.FAREWELL
        assert confidence > 0

    def test_classify_installation(self):
        """Test installation intent classification."""
        intent, confidence = IntentClassifier.classify("How do I install AutoBot?")
        assert intent == IntentCategory.INSTALLATION
        assert confidence > 0

    def test_classify_troubleshooting(self):
        """Test troubleshooting intent classification."""
        intent, confidence = IntentClassifier.classify("I have an error with the API")
        assert intent == IntentCategory.TROUBLESHOOTING
        assert confidence > 0

    def test_classify_architecture(self):
        """Test architecture intent classification."""
        intent, confidence = IntentClassifier.classify(
            "How is the system architecture designed?"
        )
        assert intent == IntentCategory.ARCHITECTURE
        assert confidence > 0

    def test_classify_security(self):
        """Test security intent classification."""
        intent, confidence = IntentClassifier.classify(
            "How do I set up authentication?"
        )
        assert intent == IntentCategory.SECURITY
        assert confidence > 0

    def test_classify_performance(self):
        """Test performance intent classification."""
        intent, confidence = IntentClassifier.classify(
            "The system is slow and needs optimization"
        )
        assert intent == IntentCategory.PERFORMANCE
        assert confidence > 0

    def test_classify_clarification(self):
        """Test clarification intent classification."""
        intent, confidence = IntentClassifier.classify(
            "I don't understand, can you explain?"
        )
        assert intent == IntentCategory.CLARIFICATION
        assert confidence > 0

    def test_classify_confirmation(self):
        """Test confirmation intent classification."""
        intent, confidence = IntentClassifier.classify("Yes, that's correct")
        assert intent == IntentCategory.CONFIRMATION
        assert confidence > 0

    def test_classify_empty_message(self):
        """Test empty message classification."""
        intent, confidence = IntentClassifier.classify("")
        assert intent == IntentCategory.UNKNOWN
        assert confidence == 0.0

    def test_classify_general_message(self):
        """Test general message classification."""
        intent, confidence = IntentClassifier.classify("Tell me about something random")
        # Should return GENERAL or a low confidence match
        assert intent is not None

    def test_classify_sequence(self):
        """Test classifying a sequence of messages."""
        messages = ["Hello", "I need to install AutoBot", "Thanks, goodbye"]
        results = IntentClassifier.classify_sequence(messages)
        assert len(results) == 3
        assert results[0][0] == IntentCategory.GREETING
        assert results[1][0] == IntentCategory.INSTALLATION
        assert results[2][0] == IntentCategory.FAREWELL

    def test_case_insensitivity(self):
        """Test that classification is case insensitive."""
        intent1, _ = IntentClassifier.classify("HELLO")
        intent2, _ = IntentClassifier.classify("hello")
        intent3, _ = IntentClassifier.classify("Hello")
        assert intent1 == intent2 == intent3 == IntentCategory.GREETING


# =============================================================================
# Response Classification Tests
# =============================================================================


class TestResponseType:
    """Tests for ResponseType enum."""

    def test_all_types_defined(self):
        """Test that all expected response types are defined."""
        expected = [
            "greeting",
            "information",
            "question",
            "clarification",
            "action_result",
            "error_message",
            "suggestion",
            "confirmation_request",
            "farewell",
            "tool_call",
            "streaming",
        ]
        actual = [rt.value for rt in ResponseType]
        for exp in expected:
            assert exp in actual, f"Missing response type: {exp}"


class TestResponseClassifier:
    """Tests for ResponseClassifier."""

    def test_classify_greeting(self):
        """Test greeting response classification."""
        resp_type = ResponseClassifier.classify("Hello! How can I help you today?")
        assert resp_type == ResponseType.GREETING

    def test_classify_question(self):
        """Test question response classification."""
        resp_type = ResponseClassifier.classify("What operating system are you using?")
        assert resp_type == ResponseType.QUESTION

    def test_classify_error(self):
        """Test error response classification."""
        resp_type = ResponseClassifier.classify(
            "I apologize, I'm unable to complete that request."
        )
        assert resp_type == ResponseType.ERROR_MESSAGE

    def test_classify_suggestion(self):
        """Test suggestion response classification."""
        resp_type = ResponseClassifier.classify("I suggest trying a different approach")
        assert resp_type == ResponseType.SUGGESTION

    def test_classify_farewell(self):
        """Test farewell response classification."""
        resp_type = ResponseClassifier.classify("Goodbye! Have a great day!")
        assert resp_type == ResponseType.FAREWELL

    def test_classify_confirmation_request(self):
        """Test confirmation request classification."""
        # Note: patterns are checked in order, so we test a phrase that matches
        # confirmation_request patterns without triggering QUESTION's "?" pattern first
        resp_type = ResponseClassifier.classify("Shall I proceed with the changes")
        assert resp_type == ResponseType.CONFIRMATION_REQUEST

    def test_classify_tool_call(self):
        """Test tool call response classification."""
        resp_type = ResponseClassifier.classify("Let me search for that information.")
        assert resp_type == ResponseType.TOOL_CALL

    def test_classify_information(self):
        """Test information response classification (default)."""
        resp_type = ResponseClassifier.classify("The system has 5 VMs configured.")
        assert resp_type == ResponseType.INFORMATION

    def test_classify_empty_response(self):
        """Test empty response classification."""
        resp_type = ResponseClassifier.classify("")
        assert resp_type == ResponseType.INFORMATION


# =============================================================================
# Flow State Tests
# =============================================================================


class TestFlowState:
    """Tests for FlowState enum."""

    def test_all_states_defined(self):
        """Test that all expected states are defined."""
        expected = [
            "initiated",
            "context_gathering",
            "processing",
            "awaiting_confirmation",
            "completed",
            "error_recovery",
            "escalated",
            "abandoned",
        ]
        actual = [fs.value for fs in FlowState]
        for exp in expected:
            assert exp in actual, f"Missing state: {exp}"


# =============================================================================
# Data Class Tests
# =============================================================================


class TestConversationMessage:
    """Tests for ConversationMessage dataclass."""

    def test_create_message(self):
        """Test creating a conversation message."""
        msg = ConversationMessage(
            role="user",
            content="Hello",
            timestamp=datetime.now(),
            intent=IntentCategory.GREETING,
        )
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.intent == IntentCategory.GREETING

    def test_default_values(self):
        """Test default values for optional fields."""
        msg = ConversationMessage(role="user", content="Hello")
        assert msg.timestamp is None
        assert msg.message_id is None
        assert msg.latency_ms is None
        assert msg.has_tool_call is False
        assert msg.metadata == {}


class TestConversationFlow:
    """Tests for ConversationFlow dataclass."""

    def test_create_flow(self):
        """Test creating a conversation flow."""
        flow = ConversationFlow(
            session_id="test_session",
            messages=[],
            final_state=FlowState.COMPLETED,
            successful=True,
        )
        assert flow.session_id == "test_session"
        assert flow.final_state == FlowState.COMPLETED
        assert flow.successful is True

    def test_default_values(self):
        """Test default values for optional fields."""
        flow = ConversationFlow(session_id="test", messages=[])
        assert flow.final_state == FlowState.INITIATED
        assert flow.turn_count == 0
        assert flow.error_count == 0
        assert flow.intent_sequence == []


class TestFlowPattern:
    """Tests for FlowPattern dataclass."""

    def test_create_pattern(self):
        """Test creating a flow pattern."""
        pattern = FlowPattern(
            pattern_id="pattern_1",
            name="installation_flow",
            description="Installation conversation pattern",
            intent_sequence=[IntentCategory.GREETING, IntentCategory.INSTALLATION],
            state_sequence=[FlowState.COMPLETED],
            occurrence_count=5,
            avg_turn_count=4.0,
            avg_latency_ms=500.0,
            success_rate=0.8,
        )
        assert pattern.pattern_id == "pattern_1"
        assert pattern.occurrence_count == 5
        assert pattern.success_rate == 0.8


class TestBottleneck:
    """Tests for Bottleneck dataclass."""

    def test_create_bottleneck(self):
        """Test creating a bottleneck."""
        bottleneck = Bottleneck(
            bottleneck_type=BottleneckType.SLOW_RESPONSE,
            description="High latency detected",
            severity="high",
            occurrence_count=10,
            affected_sessions=["session_1", "session_2"],
            recommendations=["Optimize LLM calls"],
        )
        assert bottleneck.bottleneck_type == BottleneckType.SLOW_RESPONSE
        assert bottleneck.severity == "high"
        assert len(bottleneck.recommendations) == 1


class TestOptimization:
    """Tests for Optimization dataclass."""

    def test_create_optimization(self):
        """Test creating an optimization suggestion."""
        opt = Optimization(
            optimization_type=OptimizationType.CACHING,
            description="Cache common responses",
            impact="high",
            effort="medium",
            affected_patterns=["pattern_1"],
            estimated_improvement="20% latency reduction",
        )
        assert opt.optimization_type == OptimizationType.CACHING
        assert opt.impact == "high"


# =============================================================================
# Conversation Flow Analyzer Tests
# =============================================================================


class TestConversationFlowAnalyzer:
    """Tests for ConversationFlowAnalyzer."""

    def test_init(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.min_pattern_occurrences == 2
        assert analyzer.slow_response_threshold_ms == 1000.0
        assert analyzer.max_turns_threshold == 10

    def test_parse_conversation(self, analyzer, sample_conversation):
        """Test parsing a raw conversation."""
        flow = analyzer.parse_conversation(sample_conversation, session_id="test_1")

        assert flow.session_id == "test_1"
        assert len(flow.messages) == 8
        assert flow.turn_count == 4  # 4 user messages
        # Check that intent sequence contains expected intents
        assert IntentCategory.GREETING in flow.intent_sequence
        assert IntentCategory.FAREWELL in flow.intent_sequence

    def test_parse_empty_conversation(self, analyzer):
        """Test parsing an empty conversation."""
        flow = analyzer.parse_conversation([], session_id="empty")
        assert flow.session_id == "empty"
        assert len(flow.messages) == 0
        assert flow.turn_count == 0

    def test_parse_conversation_with_errors(self, analyzer, error_conversation):
        """Test parsing a conversation with errors."""
        flow = analyzer.parse_conversation(error_conversation, session_id="error_1")

        assert flow.session_id == "error_1"
        assert flow.error_count > 0
        assert flow.clarification_count > 0
        assert not flow.successful

    def test_analyze_single_conversation(self, analyzer, sample_conversation):
        """Test analyzing a single conversation."""
        result = analyzer.analyze(conversations=[sample_conversation])

        assert result.total_conversations == 1
        assert result.total_messages == 8
        assert result.avg_turn_count == 4.0

    def test_analyze_multiple_conversations(self, analyzer, multiple_conversations):
        """Test analyzing multiple conversations."""
        result = analyzer.analyze(conversations=multiple_conversations)

        assert result.total_conversations == 8
        assert result.total_messages > 0
        assert len(result.intent_distribution) > 0

    def test_extract_flow_patterns(self, analyzer, multiple_conversations):
        """Test flow pattern extraction."""
        result = analyzer.analyze(conversations=multiple_conversations)

        # Should find at least one pattern (installation)
        assert len(result.flow_patterns) > 0

        # Check pattern structure
        pattern = result.flow_patterns[0]
        assert pattern.occurrence_count >= 2
        assert pattern.avg_turn_count > 0

    def test_detect_bottlenecks(self, analyzer):
        """Test bottleneck detection."""
        # Create conversations with high clarification count
        clarification_conversations = []
        for i in range(5):
            clarification_conversations.append(
                [
                    {"role": "user", "content": "What do you mean?"},
                    {"role": "assistant", "content": "Let me clarify."},
                    {"role": "user", "content": "I don't understand"},
                    {"role": "assistant", "content": "To clarify..."},
                    {"role": "user", "content": "Can you explain more?"},
                    {"role": "assistant", "content": "Let me explain again."},
                ]
            )

        result = analyzer.analyze(conversations=clarification_conversations)

        # Should detect clarification bottleneck
        bottleneck_types = [b.bottleneck_type for b in result.bottlenecks]
        assert BottleneckType.REPEATED_CLARIFICATION in bottleneck_types

    def test_generate_optimizations(self, analyzer, multiple_conversations):
        """Test optimization generation."""
        result = analyzer.analyze(conversations=multiple_conversations)

        # With frequent patterns, should suggest caching
        if result.flow_patterns:
            opt_types = [o.optimization_type for o in result.optimizations]
            assert OptimizationType.CACHING in opt_types

    def test_health_score_calculation(self, analyzer, sample_conversation):
        """Test health score calculation."""
        result = analyzer.analyze(conversations=[sample_conversation])

        assert 0 <= result.health_score <= 100

    def test_common_paths(self, analyzer, multiple_conversations):
        """Test common path detection."""
        result = analyzer.analyze(conversations=multiple_conversations)

        assert len(result.common_paths) > 0

    def test_cache_opportunities(self, analyzer, multiple_conversations):
        """Test cache opportunity detection."""
        result = analyzer.analyze(conversations=multiple_conversations)

        # Should find cache opportunities for repeated first messages
        assert len(result.cache_opportunities) > 0

    def test_empty_analysis(self, analyzer):
        """Test analysis with no data."""
        result = analyzer.analyze(conversations=[])

        assert result.total_conversations == 0
        assert result.health_score == 100.0


class TestDetermineFinalState:
    """Tests for final state determination."""

    def test_completed_state(self, analyzer):
        """Test completed state detection."""
        messages = [
            ConversationMessage(
                role="user",
                content="Goodbye",
                intent=IntentCategory.FAREWELL,
            )
        ]
        state = analyzer._determine_final_state(
            messages, error_count=0, clarification_count=0
        )
        assert state == FlowState.COMPLETED

    def test_error_recovery_state(self, analyzer):
        """Test error recovery state detection."""
        messages = [ConversationMessage(role="user", content="Help")]
        state = analyzer._determine_final_state(
            messages, error_count=2, clarification_count=0
        )
        assert state == FlowState.ERROR_RECOVERY

    def test_escalated_state(self, analyzer):
        """Test escalated state detection."""
        messages = [ConversationMessage(role="user", content="I'm confused")]
        state = analyzer._determine_final_state(
            messages, error_count=0, clarification_count=5
        )
        assert state == FlowState.ESCALATED

    def test_abandoned_state(self, analyzer):
        """Test abandoned state for empty messages."""
        state = analyzer._determine_final_state(
            [], error_count=0, clarification_count=0
        )
        assert state == FlowState.ABANDONED


class TestDeterminePrimaryIntent:
    """Tests for primary intent determination."""

    def test_single_intent(self, analyzer):
        """Test with single intent."""
        sequence = [IntentCategory.INSTALLATION]
        primary = analyzer._determine_primary_intent(sequence)
        assert primary == IntentCategory.INSTALLATION

    def test_multiple_intents(self, analyzer):
        """Test with multiple intents, returns most common."""
        sequence = [
            IntentCategory.GREETING,
            IntentCategory.INSTALLATION,
            IntentCategory.INSTALLATION,
            IntentCategory.FAREWELL,
        ]
        primary = analyzer._determine_primary_intent(sequence)
        assert primary == IntentCategory.INSTALLATION

    def test_empty_sequence(self, analyzer):
        """Test with empty sequence."""
        primary = analyzer._determine_primary_intent([])
        assert primary is None

    def test_only_meta_intents(self, analyzer):
        """Test with only meta intents (greeting, farewell, etc.)."""
        sequence = [IntentCategory.GREETING, IntentCategory.FAREWELL]
        primary = analyzer._determine_primary_intent(sequence)
        assert primary == IntentCategory.GREETING


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_analyze_conversations_function(self, multiple_conversations):
        """Test analyze_conversations convenience function."""
        result = analyze_conversations(
            multiple_conversations,
            min_pattern_occurrences=2,
        )

        assert isinstance(result, AnalysisResult)
        assert result.total_conversations == len(multiple_conversations)

    def test_classify_intent_function(self):
        """Test classify_intent convenience function."""
        intent, confidence = classify_intent("Hello")
        assert intent == IntentCategory.GREETING
        assert confidence > 0

    def test_classify_response_function(self):
        """Test classify_response convenience function."""
        resp_type = classify_response("What issue are you experiencing?")
        assert resp_type == ResponseType.QUESTION

    def test_get_intent_categories(self):
        """Test get_intent_categories function."""
        categories = get_intent_categories()
        assert isinstance(categories, list)
        assert "installation" in categories
        assert "greeting" in categories

    def test_get_response_types(self):
        """Test get_response_types function."""
        types = get_response_types()
        assert isinstance(types, list)
        assert "greeting" in types
        assert "question" in types

    def test_get_bottleneck_types(self):
        """Test get_bottleneck_types function."""
        types = get_bottleneck_types()
        assert isinstance(types, list)
        assert "slow_response" in types
        assert "error_loop" in types

    def test_get_optimization_types(self):
        """Test get_optimization_types function."""
        types = get_optimization_types()
        assert isinstance(types, list)
        assert "caching" in types
        assert "prompt_improvement" in types


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_unicode_content(self, analyzer):
        """Test handling of Unicode content."""
        conversation = [
            {"role": "user", "content": "Hello 🤖 こんにちは"},
            {"role": "assistant", "content": "Hi there! 👋"},
        ]
        flow = analyzer.parse_conversation(conversation, session_id="unicode")
        assert len(flow.messages) == 2

    def test_very_long_message(self, analyzer):
        """Test handling of very long messages."""
        long_content = "a" * 10000
        conversation = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": "Received your long message."},
        ]
        flow = analyzer.parse_conversation(conversation, session_id="long")
        assert len(flow.messages) == 2

    def test_special_characters(self, analyzer):
        """Test handling of special characters."""
        conversation = [
            {"role": "user", "content": "Test @#$%^&*()[]{}|\\"},
            {"role": "assistant", "content": "Response with <html> tags"},
        ]
        flow = analyzer.parse_conversation(conversation, session_id="special")
        assert len(flow.messages) == 2

    def test_missing_role(self, analyzer):
        """Test handling of message with missing role."""
        conversation = [
            {"content": "No role specified"},
            {"role": "assistant", "content": "Response"},
        ]
        flow = analyzer.parse_conversation(conversation, session_id="missing_role")
        assert flow.messages[0].role == "unknown"

    def test_missing_content(self, analyzer):
        """Test handling of message with missing content."""
        conversation = [
            {"role": "user"},
            {"role": "assistant", "content": "Response"},
        ]
        flow = analyzer.parse_conversation(conversation, session_id="missing_content")
        assert flow.messages[0].content == ""

    def test_malformed_timestamp(self, analyzer):
        """Test handling of malformed timestamp."""
        conversation = [
            {"role": "user", "content": "Hello", "timestamp": "invalid-date"},
            {"role": "assistant", "content": "Hi"},
        ]
        flow = analyzer.parse_conversation(conversation, session_id="bad_time")
        assert flow.messages[0].timestamp is None

    def test_valid_timestamp(self, analyzer):
        """Test handling of valid ISO timestamp."""
        conversation = [
            {"role": "user", "content": "Hello", "timestamp": "2025-01-15T10:30:00"},
            {"role": "assistant", "content": "Hi"},
        ]
        flow = analyzer.parse_conversation(conversation, session_id="good_time")
        assert flow.messages[0].timestamp is not None


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the complete flow."""

    def test_full_analysis_workflow(self, multiple_conversations):
        """Test complete analysis workflow."""
        # Create analyzer
        analyzer = ConversationFlowAnalyzer(min_pattern_occurrences=2)

        # Parse and analyze
        result = analyzer.analyze(conversations=multiple_conversations)

        # Verify all components
        assert result.total_conversations > 0
        assert result.total_messages > 0
        assert result.avg_turn_count > 0
        assert 0 <= result.success_rate <= 1.0
        assert len(result.intent_distribution) > 0
        assert result.health_score >= 0
        assert result.analysis_timestamp is not None

    def test_analysis_with_prebuilt_flows(self, analyzer):
        """Test analysis with pre-built ConversationFlow objects."""
        flows = [
            ConversationFlow(
                session_id="flow_1",
                messages=[
                    ConversationMessage(role="user", content="Hello"),
                    ConversationMessage(role="assistant", content="Hi there!"),
                ],
                turn_count=1,
                successful=True,
                intent_sequence=[IntentCategory.GREETING],
            ),
            ConversationFlow(
                session_id="flow_2",
                messages=[
                    ConversationMessage(role="user", content="Hello"),
                    ConversationMessage(role="assistant", content="Hi!"),
                ],
                turn_count=1,
                successful=True,
                intent_sequence=[IntentCategory.GREETING],
            ),
        ]

        result = analyzer.analyze(flows=flows)

        assert result.total_conversations == 2
        assert result.success_rate == 1.0

    def test_analysis_with_latency_data(self, analyzer):
        """Test analysis with latency data."""
        conversations = []
        for i in range(5):
            conversations.append(
                [
                    {"role": "user", "content": "Hello", "latency_ms": 100},
                    {"role": "assistant", "content": "Hi", "latency_ms": 500},
                ]
            )

        result = analyzer.analyze(conversations=conversations)

        assert result.avg_latency_ms > 0


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    def test_analysis_result_fields(self):
        """Test AnalysisResult has all required fields."""
        result = AnalysisResult(
            total_conversations=10,
            total_messages=50,
            avg_turn_count=5.0,
            avg_latency_ms=100.0,
            success_rate=0.8,
            intent_distribution={IntentCategory.INSTALLATION: 5},
            response_type_distribution={ResponseType.INFORMATION: 10},
            flow_patterns=[],
            bottlenecks=[],
            optimizations=[],
            common_paths=[],
            error_recovery_patterns=[],
            cache_opportunities=[],
            health_score=85.0,
        )

        assert result.total_conversations == 10
        assert result.success_rate == 0.8
        assert result.health_score == 85.0
