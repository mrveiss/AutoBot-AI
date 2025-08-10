"""AutoBot Agents Package - Multi-Agent Architecture."""

# Legacy agents
from .kb_librarian_agent import KBLibrarianAgent, get_kb_librarian
from .containerized_librarian_assistant import (
    ContainerizedLibrarianAssistant,
    get_containerized_librarian_assistant,
)

# New specialized agents (Multi-Agent Architecture)
from .chat_agent import ChatAgent, get_chat_agent
from .enhanced_system_commands_agent import (
    EnhancedSystemCommandsAgent,
    get_enhanced_system_commands_agent,
)
from .rag_agent import RAGAgent, get_rag_agent
from .knowledge_retrieval_agent import (
    KnowledgeRetrievalAgent,
    get_knowledge_retrieval_agent,
)
from .research_agent import ResearchAgent, get_research_agent
from .agent_orchestrator import AgentOrchestrator, get_agent_orchestrator, AgentType

# Alias for backward compatibility - use containerized version by default
get_librarian_assistant = get_containerized_librarian_assistant
LibrarianAssistantAgent = ContainerizedLibrarianAssistant

__all__ = [
    # Legacy agents
    "KBLibrarianAgent",
    "get_kb_librarian",
    "LibrarianAssistantAgent",
    "get_librarian_assistant",
    "ContainerizedLibrarianAssistant",
    "get_containerized_librarian_assistant",
    # Multi-Agent Architecture
    "ChatAgent",
    "get_chat_agent",
    "EnhancedSystemCommandsAgent",
    "get_enhanced_system_commands_agent",
    "RAGAgent",
    "get_rag_agent",
    "KnowledgeRetrievalAgent",
    "get_knowledge_retrieval_agent",
    "ResearchAgent",
    "get_research_agent",
    "AgentOrchestrator",
    "get_agent_orchestrator",
    "AgentType",
]
