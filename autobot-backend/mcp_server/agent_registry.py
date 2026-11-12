# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Static agent registry served by the ``agents.list`` MCP tool.

Split out of ``autobot_server`` to keep that file under its size ceiling (#21327).
"""

from typing import Dict, List

# Static agent registry — enumerate agents/ directory names + descriptions.
AGENT_REGISTRY: List[Dict[str, str]] = [
    {"id": "chat_agent", "description": "General-purpose conversational agent"},
    {"id": "research_agent", "description": "Multi-source research and summarisation"},
    {"id": "code_generation_agent", "description": "Source-code generation and review"},
    {"id": "data_analysis_agent", "description": "Structured data analysis and charting"},
    {"id": "classification_agent", "description": "Text classification via LLM"},
    {"id": "audio_processing_agent", "description": "Transcription and audio analysis"},
    {"id": "kb_librarian_agent", "description": "Knowledge base curation librarian"},
    {"id": "librarian_assistant", "description": "Librarian assistant for KB indexing"},
    {
        "id": "enhanced_system_commands_agent",
        "description": "System-command execution with safety guards",
    },
    {
        "id": "graph_entity_extractor",
        "description": "Extracts entities and relations for the memory graph",
    },
    {
        "id": "development_speedup_agent",
        "description": "Dev workflow acceleration and code scaffolding",
    },
]
