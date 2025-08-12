# AutoBot Agents Package

from .kb_librarian_agent import get_kb_librarian
from .research_agent import research_agent
from .chat_agent import get_chat_agent
from .rag_agent import get_rag_agent
from .agent_orchestrator import get_agent_orchestrator, AgentType
from .classification_agent import ClassificationAgent
from .enhanced_system_commands_agent import get_enhanced_system_commands_agent
from .containerized_librarian_assistant import get_containerized_librarian_assistant
from .security_scanner_agent import security_scanner_agent


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
    "security_scanner_agent"
]
