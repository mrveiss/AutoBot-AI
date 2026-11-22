# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``web_search`` tool's parameter schema: one definition, read by the handler and by the chat prompts (#21877).

The chat system prompts used to name only ``query``, so the model never learned ``fetch_full`` existed.
``browser_tool_prompt.render_parameter_lines`` renders the prompt's parameter list from this schema, so the
two cannot drift.
"""

WEB_SEARCH_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query string."},
        "fetch_full": {
            "type": "boolean",
            "description": (
                "When true, fetches the full markdown of each result page "
                "in addition to returning search snippets. Default false."
            ),
        },
        "max_pages": {
            "type": "integer",
            "description": (
                "Maximum number of search results to return. Applies to both "
                "snippet mode (fetch_full=false) and full-fetch mode "
                "(fetch_full=true). Default 5."
            ),
            "minimum": 1,
            "maximum": 10,
        },
    },
    "required": ["query"],
}
