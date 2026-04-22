# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Re-export shim — canonical implementation lives in specialized_agent_service.py.

Kept for backward-compatibility; import from specialized_agent_service directly.
See: #5429
"""

from services.specialized_agent_service import (  # noqa: F401
    SpecializedAgentService,
    _categorize_agent,
    _parse_frontmatter,
    _extract_system_prompt_excerpt,
)
