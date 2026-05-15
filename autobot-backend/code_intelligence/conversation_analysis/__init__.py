# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Analysis Package

Issue #381: Extracted from conversation_flow_analyzer.py god class refactoring.
Provides conversation flow analysis capabilities for AutoBot's chat system.

Package Structure:
- types.py: Enums and data classes (IntentCategory, FlowState, ConversationFlow, etc.)
- classifiers.py: IntentClassifier, ResponseClassifier
- analyzer.py: ConversationFlowAnalyzer main class and convenience functions
"""

# Re-export analyzer and convenience functions
from .analyzer import (
    ConversationFlowAnalyzer,
    analyze_conversations,
    classify_intent,
    classify_response,
    get_bottleneck_types,
    get_intent_categories,
    get_optimization_types,
    get_response_types,
)

# Re-export classifiers
from .classifiers import IntentClassifier, ResponseClassifier

# Re-export all public types
from .types import (
    SATISFACTION_SIGNALS,
    AnalysisResult,
    Bottleneck,
    BottleneckType,
    ConversationFlow,
    ConversationMessage,
    FlowPattern,
    FlowState,
    IntentCategory,
    Optimization,
    OptimizationType,
    ResponseType,
)

__all__ = [
    # Types
    "IntentCategory",
    "FlowState",
    "ResponseType",
    "BottleneckType",
    "OptimizationType",
    "ConversationMessage",
    "ConversationFlow",
    "FlowPattern",
    "Bottleneck",
    "Optimization",
    "AnalysisResult",
    "SATISFACTION_SIGNALS",
    # Classifiers
    "IntentClassifier",
    "ResponseClassifier",
    # Analyzer
    "ConversationFlowAnalyzer",
    # Convenience functions
    "analyze_conversations",
    "classify_intent",
    "classify_response",
    "get_intent_categories",
    "get_response_types",
    "get_bottleneck_types",
    "get_optimization_types",
]
