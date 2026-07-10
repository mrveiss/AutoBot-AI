# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
llm_shared.json_utils — Shared JSON parsing helpers for LLM responses.

Issue #11520: Extracted from judges/__init__.py `_extract_json_object` so
every LLM call site in the codebase shares a single fence-tolerant parser.
judges/__init__.py now imports from here instead of defining its own copy.
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Parse a JSON object from an LLM response, tolerating markdown code fences (#10672).

    structured_output=True makes supporting providers emit valid JSON; providers
    that ignore it may still wrap the object in a ```json fence, so strip that
    before parsing. Raises json.JSONDecodeError on genuinely unparseable text.

    Args:
        raw_text: Raw LLM response content, possibly wrapped in markdown fences.

    Returns:
        Parsed JSON as a Python dict.

    Raises:
        json.JSONDecodeError: If the text cannot be parsed as JSON.
    """
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        if "```" in raw_text:
            block = raw_text.split("```", 2)[1]
            if block.lstrip().lower().startswith("json"):
                block = block.lstrip()[4:]
            return json.loads(block.strip())
        raise
