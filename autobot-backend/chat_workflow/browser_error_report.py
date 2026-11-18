# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Model- and user-facing report for a failed browser tool call (#21769).

``handle_browser_tool`` used to replace every failure with a fixed string, so
the model could not tell a timeout from a missing selector from a navigation
failure. This builds a classified report from the tool name, the parameters the
model itself supplied and the exception TYPE/message *shape* -- the raw
exception text is never echoed (CWE-209): it can carry stack frames, internal
addresses and filesystem paths, and stays in the log.

The echoed selector/URL are model-supplied but still pass through the canonical
redactors in :mod:`autobot_shared.secret_redaction`.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from autobot_shared.env_utils import env_int
from autobot_shared.secret_redaction import redact_text, redact_url_credentials

# Upper bound on the echoed selector/URL so a pathological parameter cannot bloat the prompt.
BROWSER_ERROR_ECHO_MAX_CHARS = env_int("CHAT_BROWSER_ERROR_ECHO_MAX_CHARS", default=200)

_TIMEOUT_MS_RE = re.compile(r"Timeout\s+(\d+)\s*ms", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_NAVIGATION_TOOLS = frozenset({"navigate", "goto", "go_back", "go_forward", "reload", "open_url"})

CLASS_TIMEOUT = "timeout"
CLASS_SELECTOR_NOT_FOUND = "selector_not_found"
CLASS_NAVIGATION_FAILED = "navigation_failed"
CLASS_OTHER = "other"

_PLAIN_WORDS = {
    CLASS_TIMEOUT: "timed out",
    CLASS_SELECTOR_NOT_FOUND: "could not find the requested element",
    CLASS_NAVIGATION_FAILED: "could not load the page",
    CLASS_OTHER: "failed",
}


def _text_of(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def classify_browser_error(tool_name: str, error: BaseException) -> str:
    """Return one of the ``CLASS_*`` values for *error* raised by *tool_name*."""
    text = _text_of(error)
    lowered = text.lower()
    on_locator = "locator" in lowered or "selector" in lowered
    if "timeout" in lowered or isinstance(error, TimeoutError):
        if tool_name in _NAVIGATION_TOOLS and not on_locator:
            return CLASS_NAVIGATION_FAILED
        return CLASS_TIMEOUT if not on_locator else CLASS_SELECTOR_NOT_FOUND
    if on_locator and ("not found" in lowered or "no element" in lowered or "strict mode" in lowered):
        return CLASS_SELECTOR_NOT_FOUND
    if tool_name in _NAVIGATION_TOOLS or "net::err" in lowered:
        return CLASS_NAVIGATION_FAILED
    return CLASS_OTHER


def _timeout_ms(error: BaseException) -> int | None:
    match = _TIMEOUT_MS_RE.search(str(error))
    return int(match.group(1)) if match else None


def _without_query(url: str) -> str:
    """*url* without its query string and fragment: both routinely carry tokens and session ids (#21769)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.split("?", 1)[0].split("#", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _echo(value: Any, *, is_url: bool) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    cleaned = _CONTROL_RE.sub(" ", _without_query(value) if is_url else value)[:BROWSER_ERROR_ECHO_MAX_CHARS]
    return redact_text(redact_url_credentials(cleaned) if is_url else cleaned)


def build_browser_error_report(tool_name: str, params: dict[str, Any], error: BaseException) -> dict[str, Any]:
    """Structured, sanitised report: class, tool, selector/url given, elapsed timeout."""
    report: dict[str, Any] = {
        "tool": tool_name,
        "error_class": classify_browser_error(tool_name, error),
    }
    params = params if isinstance(params, dict) else {}
    for key, is_url in (("selector", False), ("url", True)):
        echoed = _echo(params.get(key), is_url=is_url)
        if echoed:
            report[key] = echoed
    timeout_ms = _timeout_ms(error)
    if timeout_ms is not None:
        report["timeout_ms"] = timeout_ms
    return report


def format_browser_error_text(report: dict[str, Any]) -> str:
    """One plain-language sentence describing *report* (shared by the model result and the chat message)."""
    text = f"Browser tool '{report['tool']}' {_PLAIN_WORDS[report['error_class']]} [{report['error_class']}]"
    for key in ("selector", "url"):
        if key in report:
            text += f" for {key} {report[key]!r}"
    if "timeout_ms" in report:
        text += f" after {report['timeout_ms']}ms"
    return text
