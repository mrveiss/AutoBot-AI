# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Storage category definitions and their on-disk directories (Issue #665, #18293).

Extracted from ``api/data_storage.py``. Every category lives under the data
directory except the legacy conversation transcripts, which live where their
retired writer put them (``legacy_conversation_transcripts_dir``). That category
is PROTECTED: bulk cleanup cannot remove sessions whose turns exist only there.
"""

from pathlib import Path

from autobot_shared.store_authority import legacy_conversation_transcripts_dir

#: The category id of the legacy transcripts -- the store_authority concept name, not
#: a directory: the directory comes from SSOT config (#18293).
LEGACY_TRANSCRIPTS_CATEGORY = "legacy_conversation_transcripts"


def category_dir(data_dir: Path, category_path: str) -> Path:
    """The directory holding *category_path*'s files."""
    if category_path == LEGACY_TRANSCRIPTS_CATEGORY:
        return legacy_conversation_transcripts_dir()
    return data_dir / category_path


# =============================================================================
# Storage Category Definitions (Issue #665)
# =============================================================================


def get_protected_categories() -> list[dict]:
    """
    Get protected storage categories (cannot be cleaned up).

    Issue #665: Extracted from get_storage_categories to reduce function length.
    These are critical system data stores that should not be modified.
    """
    return [
        {
            "name": "ChromaDB Vectors",
            "path": "chromadb",
            "description": "Vector embeddings database for semantic search",
        },
        {
            "name": "Knowledge Base ChromaDB",
            "path": "chromadb_kb",
            "description": "Knowledge base vector embeddings",
        },
        {
            "name": "Knowledge Files",
            "path": "knowledge",
            "description": "Knowledge base configuration files",
        },
        {
            "name": "Knowledge Base Data",
            "path": "knowledge_base",
            "description": "Knowledge base documents and embeddings",
        },
        {
            "name": "System Knowledge",
            "path": "system_knowledge",
            "description": "System procedures, workflows, and tools",
        },
        {
            "name": "Memory Storage",
            "path": "memory",
            "description": "Agent memory and context storage",
        },
        {
            "name": "MCP Tools",
            "path": "mcp_tools",
            "description": "MCP tool configurations",
        },
        {
            # #18293: read-only legacy store; disposal goes through the #17038 review queue.
            "name": "Conversation Transcripts (legacy)",
            "path": LEGACY_TRANSCRIPTS_CATEGORY,
            "description": "Legacy chat transcripts, read-only; chat sessions are the system of record",
        },
    ]


def get_cleanable_categories() -> list[dict]:
    """
    Get cleanable storage categories (can be manually cleaned up).

    Issue #665: Extracted from get_storage_categories to reduce function length.
    These are user data and reports that can be safely removed.
    """
    return [
        {
            "name": "Chat Sessions",
            "path": "chats",
            "description": "Chat sessions and terminal transcripts",
        },
        {
            "name": "Conversation Files",
            "path": "conversation_files",
            "description": "Files attached to conversations",
        },
        {
            "name": "Anti-Pattern Reports",
            "path": "anti_pattern_reports",
            "description": "Code anti-pattern detection reports",
        },
        {
            "name": "Reports",
            "path": "reports",
            "description": "Generated analysis reports",
        },
        {
            "name": "File Manager Root",
            "path": "file_manager_root",
            "description": "File manager sandbox root directory",
        },
        {
            "name": "Security Data",
            "path": "security",
            "description": "Security scan results and configurations",
        },
    ]
