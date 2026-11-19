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
from typing import Any

from autobot_shared.logging_manager import get_logger
from chat_workflow.tool_call_grammar import (
    TOOL_CALL_COMPLETE_RE,
    TOOL_CALL_OPENING_RE,
    TOOL_CALL_PATTERN,
    TOOL_CALL_TRUNCATED_OPENING_RE,
    normalize_tool_call_brackets,
    strip_unparsed_tool_tags,
)

logger = get_logger(__name__)

_PARSE_ERROR_SNIPPET_CHARS = 200
#: Everything ``ast.literal_eval`` can raise on model-written text; none may escape the reply path (#21843).
_LITERAL_EVAL_ERRORS = (ValueError, SyntaxError, TypeError, RecursionError, MemoryError)
# `'key': '` at the start of a dict, or `', 'key': '` between entries.
_QUOTED_KEY_START_RE = re.compile(r"(?:^\{\s*|'\s*,\s*)'(\w+)'\s*:\s*'")
_QUOTED_DICT_END_RE = re.compile(r"'\s*\}\s*$")
# A quoted key inside a recovered value: the entry after it is not a quoted string, so it cannot be split off.
_NON_STRING_ENTRY_RE = re.compile(r"'\s*,\s*'\w+'\s*:")


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
        value = text[m.end() : stop]
        if _NON_STRING_ENTRY_RE.search(value):  # e.g. `'timeout': 10` swallowed into the previous value
            return None
        out[m.group(1)] = value
    return out


def parse_tool_args(raw: str) -> dict:
    """Parse tool call args: JSON, then literals, then apostrophe-tolerant dicts. (#4483, #21843)

    ``ast.literal_eval`` only accepts Python literal structures, so it is safe.
    Raises ``json.JSONDecodeError`` when nothing parses to a dict (a non-object JSON value is a failure).
    """
    try:
        parsed = json.loads(raw, strict=False)  # strict=False: raw newlines/tabs inside strings
        if isinstance(parsed, dict):
            return parsed
        # `null`, `[]`, `"x"` are valid JSON but not arguments: a caller would call `.get` on them (#21843)
        first_error = json.JSONDecodeError("tool args must be a JSON object", raw[:_PARSE_ERROR_SNIPPET_CHARS], 0)
    except json.JSONDecodeError as err:
        first_error = err
    except RecursionError:  # a deeply nested blob is unparseable, not a crash
        first_error = json.JSONDecodeError("nesting too deep", raw[:_PARSE_ERROR_SNIPPET_CHARS], 0)
    try:
        result = ast.literal_eval(raw)  # noqa: S307 - literals only, safe
        if isinstance(result, dict):
            logger.warning("Tool args parsed via ast.literal_eval fallback — LLM produced near-valid JSON")
            return result
    except _LITERAL_EVAL_ERRORS:  # `{[1]: 2}` is a TypeError, deep nesting a RecursionError/MemoryError
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
    if not text or not (TOOL_CALL_OPENING_RE.search(text) or TOOL_CALL_TRUNCATED_OPENING_RE.search(text)):
        return None
    matches = list(TOOL_CALL_PATTERN.finditer(text))
    failures = _param_failures(matches)
    outside = _outside_calls(text, matches)
    if TOOL_CALL_OPENING_RE.search(outside):  # an opening beside complete calls never closed
        failures.append("a TOOL_CALL tag was not closed or is malformed, so no tool ran")
    elif TOOL_CALL_TRUNCATED_OPENING_RE.search(outside):  # generation stopped before the tag's `>`
        failures.append("a TOOL_CALL tag was cut off before its closing '>', so no tool ran")
    return "; ".join(failures) or None


def _outside_calls(text: str, matches: list[re.Match]) -> str:
    """*text* with every complete call removed: a tag quoted inside a call's params is not an opening."""
    pieces, pos = [], 0
    for match in matches:
        pieces.append(text[pos : match.start()])
        pos = match.end()
    pieces.append(text[pos:])
    return " ".join(pieces)


def _param_failures(matches: list[re.Match]) -> list[str]:
    """One message per complete call whose params do not parse."""
    failures = []
    for match in matches:
        try:
            parse_tool_args(match.group(3))
        except json.JSONDecodeError as err:
            snippet = match.group(3)[:_PARSE_ERROR_SNIPPET_CHARS]
            failures.append(f"tool '{match.group(1)}': params are not valid JSON ({err.msg}): {snippet}")
    return failures


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


def record_parse_failure(ctx: Any, text: str, iteration: int, max_iterations: int) -> bool:
    """Append the parse-error step to ``ctx.execution_history``; True when the turn should continue. (#21843)

    Bounded by *max_iterations*: the last iteration ends the turn (the reply is still cleaned).
    """
    step = parse_failure_step(text, iteration) if iteration < max_iterations else None
    if step is None:
        return False
    logger.warning("[Issue #21843] Iteration %d: TOOL_CALL did not parse - feeding error back", iteration)
    ctx.execution_history.append(step)
    return True


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

    normalized = normalize_tool_call_brackets(text or "")  # `[TOOL_CALL ...]` must meet the same parse check
    kept = TOOL_CALL_PATTERN.sub(_drop_if_failed, normalized)
    return strip_unparsed_tool_tags(_drop_unmatched_fragments(kept)).strip()


def _drop_unmatched_fragments(text: str) -> str:
    """*text* without opening/closing tag fragments that sit outside every complete call (kept calls untouched)."""
    out, pos = [], 0
    for match in TOOL_CALL_PATTERN.finditer(text):
        out.append(TOOL_CALL_COMPLETE_RE.sub("", TOOL_CALL_OPENING_RE.sub("", text[pos : match.start()])))
        out.append(match.group(0))
        pos = match.end()
    tail = TOOL_CALL_COMPLETE_RE.sub("", TOOL_CALL_OPENING_RE.sub("", text[pos:]))
    out.append(TOOL_CALL_TRUNCATED_OPENING_RE.sub("", tail))  # a tag cut off before its `>` (#21843)
    return "".join(out)
