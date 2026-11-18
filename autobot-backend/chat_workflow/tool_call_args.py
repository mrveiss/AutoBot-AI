# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tool-call argument parsing and parse-failure feedback (#4483, #21843).

``parse_tool_args`` is the single parser for the ``params='…'`` blob of a
``<TOOL_CALL>``. When a call's args cannot be parsed the tool never runs;
``tool_call_parse_error`` produces the message that is fed back to the model so
the turn continues instead of ending, and ``clean_reply_text`` guarantees that
raw tool-call markup is never persisted as the final answer.
"""

from __future__ import annotations

import ast
import json
import re

from autobot_shared.logging_manager import get_logger
from chat_workflow.tool_call_grammar import TOOL_CALL_OPENING_RE, TOOL_CALL_PATTERN, strip_unparsed_tool_tags

logger = get_logger(__name__)

_PARSE_ERROR_SNIPPET_CHARS = 200
# `'key': '` at the start of a dict, or `', 'key': '` between entries.
_QUOTED_KEY_START_RE = re.compile(r"(?:^\{\s*|'\s*,\s*)'(\w+)'\s*:\s*'")
_QUOTED_DICT_END_RE = re.compile(r"'\s*\}\s*$")


def _split_quoted_entries(raw: str) -> dict | None:
    """Parse ``{'k': 'v', ...}`` whose string values hold unescaped apostrophes.

    ``ast.literal_eval`` rejects ``{'expression': 'a.querySelector('x')'}``. Every
    value must be a quoted string, delimited by the ``', 'key': '`` boundaries and
    the closing ``'}``; anything else returns None so the caller still errors.
    """
    text = raw.strip()
    end = _QUOTED_DICT_END_RE.search(text)
    starts = list(_QUOTED_KEY_START_RE.finditer(text))
    if not end or not starts or starts[0].start() != 0:
        return None
    out: dict = {}
    for i, m in enumerate(starts):
        stop = starts[i + 1].start() if i + 1 < len(starts) else end.start()
        out[m.group(1)] = text[m.end() : stop]
    return out


def parse_tool_args(raw: str) -> dict:
    """Parse tool call args: JSON, then literals, then apostrophe-tolerant dicts. (#4483, #21843)

    ``ast.literal_eval`` only accepts Python literal structures, so it is safe.
    Raises ``json.JSONDecodeError`` when nothing parses.
    """
    try:
        return json.loads(raw, strict=False)  # strict=False: raw newlines/tabs inside strings
    except json.JSONDecodeError as err:
        first_error = err
    try:
        result = ast.literal_eval(raw)  # noqa: S307 - literals only, safe
        if isinstance(result, dict):
            logger.warning("Tool args parsed via ast.literal_eval fallback — LLM produced near-valid JSON")
            return result
    except (ValueError, SyntaxError):
        pass
    if (recovered := _split_quoted_entries(raw)) is not None:
        logger.warning("Tool args recovered from unescaped apostrophes in single-quoted values (#21843)")
        return recovered
    raise first_error


def tool_call_parse_error(text: str) -> str | None:
    """Describe why *text*'s TOOL_CALL did not parse, or None if it has no failed call. (#21843)

    Covers a well-formed tag whose args are invalid, and an opening tag that never
    matched the full grammar. A tag that parses cleanly returns None.
    """
    if not text or not TOOL_CALL_OPENING_RE.search(text):
        return None
    failures = []
    for match in TOOL_CALL_PATTERN.finditer(text):
        try:
            parse_tool_args(match.group(3))
        except json.JSONDecodeError as err:
            snippet = match.group(3)[:_PARSE_ERROR_SNIPPET_CHARS]
            failures.append(f"tool '{match.group(1)}': params are not valid JSON ({err.msg}): {snippet}")
    if failures:
        return "; ".join(failures)
    if not TOOL_CALL_PATTERN.search(text):
        return "a TOOL_CALL tag was not closed or is malformed, so no tool ran"
    return None


def parse_failure_step(text: str, iteration: int) -> dict | None:
    """Execution-history entry telling the model its TOOL_CALL did not parse, or None. (#21843)

    The first iteration of a plan-first reply (``[PLANNING]`` + TOOL_CALL) is
    deferred on purpose and is not a failure.
    """
    if iteration == 1 and "[planning]" in (text or "").lower():
        return None
    if (error := tool_call_parse_error(text)) is None:
        return None
    advice = "Re-emit the call with params as strict JSON using double quotes; escape any quote inside a value."
    return {
        "tool": "tool_call_parse",
        "status": "error",
        "error": f"Your TOOL_CALL was not executed: {error}. {advice}",
    }


def clean_reply_text(text: str) -> str:
    """User-visible reply text with no raw tool-call markup, parsed or not. (#21843)

    ``strip_unparsed_tool_tags`` trusts any full-grammar match as "already parsed";
    a match whose args fail ``parse_tool_args`` never ran, so it is removed here.
    """

    def _drop_if_failed(match: re.Match) -> str:
        try:
            parse_tool_args(match.group(3))
        except json.JSONDecodeError:
            return ""
        return match.group(0)

    return strip_unparsed_tool_tags(TOOL_CALL_PATTERN.sub(_drop_if_failed, text or "")).strip()
