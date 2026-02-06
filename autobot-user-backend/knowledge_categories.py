# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Category Constants

Defines the 3 main categories for AutoBot's knowledge base:
1. AutoBot Documentation - AutoBot's own documentation and guides
2. System Knowledge - System information, man pages, OS-specific knowledge
3. User Knowledge - User-provided documents and reference materials
"""

from enum import Enum
from typing import Dict, List

# Issue #380: Module-level tuples for source category detection
_AUTOBOT_DOC_KEYWORDS = ("autobot", "docs/", "documentation")
_SYSTEM_KNOWLEDGE_KEYWORDS = ("man_page", "manpage", "system", "command", "os_", "machine")


class KnowledgeCategory(str, Enum):
    """Main knowledge base categories"""

    AUTOBOT_DOCUMENTATION = "autobot-documentation"
    SYSTEM_KNOWLEDGE = "system-knowledge"
    USER_KNOWLEDGE = "user-knowledge"


# Category metadata for display and organization
CATEGORY_METADATA: Dict[str, Dict[str, str]] = {
    KnowledgeCategory.AUTOBOT_DOCUMENTATION: {
        "name": "AutoBot Documentation",
        "description": "AutoBot's initial knowledge - documentation and guides",
        "icon": "fas fa-book",
        "color": "#3b82f6",  # Blue
        "examples": "API docs, architecture guides, setup instructions",
    },
    KnowledgeCategory.SYSTEM_KNOWLEDGE: {
        "name": "System Knowledge",
        "description": (
            "AutoBot's initial knowledge - system info, man pages, OS knowledge"
        ),
        "icon": "fas fa-server",
        "color": "#10b981",  # Green
        "examples": "Man pages, system commands, configuration files, hardware info",
    },
    KnowledgeCategory.USER_KNOWLEDGE: {
        "name": "User Knowledge",
        "description": "What AutoBot is used for - user-provided domain knowledge",
        "icon": "fas fa-user-circle",
        "color": "#f59e0b",  # Amber
        "examples": "Programming books, law references, domain-specific guides",
    },
}


def get_category_display_name(category: str) -> str:
    """Get human-readable category name"""
    return CATEGORY_METADATA.get(category, {}).get("name", category)


def get_category_icon(category: str) -> str:
    """Get FontAwesome icon class for category"""
    return CATEGORY_METADATA.get(category, {}).get("icon", "fas fa-folder")


def get_category_color(category: str) -> str:
    """Get color for category"""
    return CATEGORY_METADATA.get(category, {}).get("color", "#6b7280")


def get_all_categories() -> List[str]:
    """Get list of all valid category IDs"""
    return [cat.value for cat in KnowledgeCategory]


def is_valid_category(category: str) -> bool:
    """Check if category is valid"""
    return category in get_all_categories()


def get_category_for_source(source: str) -> str:
    """Map source to appropriate category"""
    source_lower = source.lower()

    # AutoBot documentation sources
    if any(keyword in source_lower for keyword in _AUTOBOT_DOC_KEYWORDS):
        return KnowledgeCategory.AUTOBOT_DOCUMENTATION

    # System knowledge sources
    if any(keyword in source_lower for keyword in _SYSTEM_KNOWLEDGE_KEYWORDS):
        return KnowledgeCategory.SYSTEM_KNOWLEDGE

    # Default to user knowledge
    return KnowledgeCategory.USER_KNOWLEDGE
