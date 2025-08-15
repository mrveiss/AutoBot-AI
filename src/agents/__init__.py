# AutoBot Agents Package

from .kb_librarian_agent import get_kb_librarian


# Create a stub for get_librarian_assistant for backward compatibility
def get_librarian_assistant():
    """Stub function for backward compatibility."""
    return get_kb_librarian()


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
]
