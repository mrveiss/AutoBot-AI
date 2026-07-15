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
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

#: Short JSON escapes for the most common raw control characters (#11587).
_CONTROL_ESCAPES = {"\n": "\\n", "\t": "\\t", "\r": "\\r"}

#: Trailing comma immediately before a closing brace/bracket (#11688).
_TRAILING_COMMA_RE = re.compile(r",\s*(?=[}\]])")

#: Bare (unquoted) object key following '{' or ',' (#11688).
_BARE_KEY_RE = re.compile(r"([{,]\s*)([A-Za-z_]\w*)(\s*:)")


def _escape_controls_in_strings(text: str) -> str:
    """Escape raw C0 control chars inside JSON string literals (#11587).

    Single-pass state machine tracking in-string and backslash-escape state.
    Inside double-quoted string literals, raw control characters (< 0x20) are
    replaced with their JSON escape sequences; structural whitespace outside
    strings is left untouched. Already-escaped sequences are never
    double-escaped because the escape state consumes the following character.
    """
    out = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string and not escaped and ch < "\x20":
            out.append(_CONTROL_ESCAPES.get(ch, f"\\u{ord(ch):04x}"))
            continue
        out.append(ch)
        if escaped:
            escaped = False
        elif in_string and ch == "\\":
            escaped = True
        elif ch == '"':
            in_string = not in_string
    return "".join(out)


def repair_json_syntax(text: str) -> str:
    """Repair common LLM JSON syntax errors (#11688).

    Promoted from agents/json_formatter_agent.py so every extract_json_object()
    caller (structured_ops, judges, the formatter agent) shares one repair
    cascade: strips trailing commas before a closing brace/bracket and
    double-quotes bare object keys. Purely textual — the caller still gates the
    result through json.loads(), so a repair that is wrong for a given input
    fails the parse exactly as the unrepaired text would have.
    """
    repaired = _TRAILING_COMMA_RE.sub("", text)
    return _BARE_KEY_RE.sub(r'\1"\2"\3', repaired)


def extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Parse a JSON object from an LLM response, tolerating markdown code fences (#10672).

    structured_output=True makes supporting providers emit valid JSON; providers
    that ignore it may still wrap the object in a ```json fence, so strip that
    before parsing. Repair tiers, each gated by a real parse attempt:

    1. Direct ``json.loads``.
    2. Markdown fence strip (#10672).
    3. Raw control characters inside string literals escaped (#11587).
    4. Common syntax repair — trailing commas, bare keys, then a last-resort
       single→double quote swap for python-repr style objects (#11688).

    Raises json.JSONDecodeError on genuinely unparseable text.

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
        candidate = raw_text
        if "```" in candidate:
            block = candidate.split("```", 2)[1]
            if block.lstrip().lower().startswith("json"):
                block = block.lstrip()[4:]
            candidate = block.strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        candidate = _escape_controls_in_strings(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # Progressive repairs, safest first: the bare-key regex can touch
        # colon-bearing string values, so only apply it when the
        # trailing-comma fix alone was not enough.
        repaired = _TRAILING_COMMA_RE.sub("", candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_BARE_KEY_RE.sub(r'\1"\2"\3', repaired))
        except json.JSONDecodeError:
            return json.loads(repair_json_syntax(candidate.replace("'", '"')))
