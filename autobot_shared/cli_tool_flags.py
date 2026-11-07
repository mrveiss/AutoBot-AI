# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared sanitizer for claude_code tool-permission CLI flags (GH#11186).

``--allowedTools`` / ``--disallowedTools`` take a comma-joined list of tool names.
Both the execution backend and the LLC agent adapter build these, so the guard
lives here once: drop empty names, flag-looking values (option injection), and any
name carrying the ``,`` / newline join delimiters (which would split into extra
entries). Values are passed as distinct argv elements (no shell), so this is
defense-in-depth on top of that.
"""

import re
from typing import Any, Iterable, List, Optional


def sanitize_tool_names(values: Optional[Iterable[Any]]) -> List[str]:
    """Return the safe subset of *values* usable in a comma-joined tool flag."""
    return [s for v in (values or []) if (s := str(v)) and not s.startswith("-") and "," not in s and "\n" not in s]


# A model alias or id: ``opus``, ``claude-opus-5[1m]``, ``us.anthropic.claude-x-v1:0``.
# Starts alphanumeric so a value can never read as an option; no whitespace.
_SAFE_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,127}")


def safe_model_arg(value: Any) -> Optional[str]:
    """Return *value* as a ``--model`` argument, or ``None`` when it is not a safe model name."""
    if value is None:
        return None
    s = str(value)
    return s if _SAFE_MODEL_RE.fullmatch(s) else None
