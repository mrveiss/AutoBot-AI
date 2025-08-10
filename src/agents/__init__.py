# AutoBot Agents Package

from .kb_librarian_agent import get_kb_librarian
from .research_agent import research_agent


# Create a stub for get_librarian_assistant for backward compatibility
def get_librarian_assistant():
    """Stub function for backward compatibility."""
    return get_kb_librarian()


__all__ = ["get_kb_librarian", "get_librarian_assistant", "research_agent"]
