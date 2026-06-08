# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
    _extract_system_prompt_excerpt,
    _parse_frontmatter,
)
