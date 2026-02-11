# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# AutoBot Agents Package

# Import available agent classes
from .kb_librarian_agent import get_kb_librarian


# Create a stub for get_librarian_assistant for backward compatibility
def get_librarian_assistant():
    """Stub function for backward compatibility."""
    return None  # Will need knowledge_base parameter


__all__ = [
    "get_kb_librarian",
    "get_librarian_assistant",
    "research_agent",
    "get_chat_agent",
    "get_rag_agent",
    "get_agent_orchestrator",
    "AgentType",
    "ClassificationAgent",
    "get_enhanced_system_commands_agent",
    "get_containerized_librarian_assistant",
    "security_scanner_agent",
    # Issue #60: Specialized agents
    "get_data_analysis_agent",
    "get_code_generation_agent",
    "get_translation_agent",
    "get_summarization_agent",
    "get_sentiment_analysis_agent",
    "get_image_analysis_agent",
    "get_audio_processing_agent",
]
