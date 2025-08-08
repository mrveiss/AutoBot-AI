"""AutoBot Agents Package."""

from .kb_librarian_agent import KBLibrarianAgent, get_kb_librarian
from .containerized_librarian_assistant import (
    ContainerizedLibrarianAssistant,
    get_containerized_librarian_assistant,
)

# Alias for backward compatibility - use containerized version by default
get_librarian_assistant = get_containerized_librarian_assistant
LibrarianAssistantAgent = ContainerizedLibrarianAssistant

__all__ = [
    "KBLibrarianAgent",
    "get_kb_librarian",
    "LibrarianAssistantAgent",
    "get_librarian_assistant",
    "ContainerizedLibrarianAssistant",
    "get_containerized_librarian_assistant",
]
