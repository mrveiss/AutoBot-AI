# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Flow Analyzer - Backward Compatibility Facade

Issue #381: God class refactoring - Original 1,258 lines reduced to ~70 line facade.

This module is a thin wrapper that re-exports from the new
src/code_intelligence/conversation_analysis/ package for backward compatibility.
All functionality has been extracted to:
- src/code_intelligence/conversation_analysis/types.py: Enums and data classes
- src/code_intelligence/conversation_analysis/classifiers.py: Intent/Response classifiers
- src/code_intelligence/conversation_analysis/analyzer.py: ConversationFlowAnalyzer

Features:
- Flow extraction from conversation histories
- Intent classification using pattern matching
- Response pattern analysis
- Error recovery pattern detection
- Bottleneck identification
- Optimization suggestions

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #227).

DEPRECATED: Import directly from code_intelligence.conversation_analysis instead.
"""

# Re-export everything from the new package for backward compatibility
from backend.code_intelligence.conversation_analysis import (
    # Types
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
    # Classifiers
    IntentClassifier,
    ResponseClassifier,
    # Analyzer
    ConversationFlowAnalyzer,
    # Convenience functions
    analyze_conversations,
    classify_intent,
    classify_response,
    get_bottleneck_types,
    get_intent_categories,
    get_optimization_types,
    get_response_types,
)

# Backward compatibility alias
_SATISFACTION_SIGNALS = SATISFACTION_SIGNALS

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
    "_SATISFACTION_SIGNALS",  # Backward compatibility
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
