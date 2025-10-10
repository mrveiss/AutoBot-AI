# AutoBot Agents Package

# Import available agent classes
from .kb_librarian_agent import KBLibrarianAgent, get_kb_librarian
from src.constants.network_constants import NetworkConstants

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
]
