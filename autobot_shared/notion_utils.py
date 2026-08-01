# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Notion API response parsing helpers.

Issue #12659: ``extract_title()`` was a byte-identical ``_extract_title()``
copy in both ``integrations/notion_integration.py`` and
``knowledge/connectors/notion.py``. Neither module depends on the other
(one implements the agent-callable integrations framework, the other the
knowledge-connector sync pipeline), so the shared helper lives here rather
than in either module.
"""

from typing import Any, Dict


def extract_title(obj: Dict[str, Any]) -> str:
    """Extract the plain-text title from a Notion page or database object."""
    # Database title field
    title_array = obj.get("title", [])
    if title_array and isinstance(title_array, list):
        return "".join(t.get("plain_text", "") for t in title_array)

    # Page title via Name property
    props = obj.get("properties", {})
    for prop_name in ("Name", "Title", "title"):
        prop = props.get(prop_name, {})
        title_values = prop.get("title", [])
        if title_values:
            return "".join(t.get("plain_text", "") for t in title_values)

    return ""
