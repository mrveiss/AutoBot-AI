# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
One policy for every LLM tracing observer (#19933).

Two decisions live here so no observer carries its own copy:

* ``destination_allowed`` -- may this tracing destination be activated at all
  (egress policy; external destinations need ``AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL``)?
* ``trace_messages`` / ``trace_text`` -- what prompt and response text an observer
  may send (nothing unless ``AUTOBOT_LLM_TRACING_INCLUDE_CONTENT``, then redacted).
"""

from __future__ import annotations

from typing import Any

from autobot_shared.egress_allowlist import normalize_origin, static_internal_origins
from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger
from autobot_shared.url_safety import is_public_url
from llm_shared.credential_redaction import redact_dict, redact_string

logger = get_logger(__name__)

CONTENT_OMITTED = "[content omitted: AUTOBOT_LLM_TRACING_INCLUDE_CONTENT is off]"


def _refusal(url: str) -> str:
    """Why *url* may not be a tracing destination, or ``""`` when it may."""
    origin = normalize_origin(url)
    if origin is None:
        return "destination is not a valid http(s) URL"
    if origin in static_internal_origins():
        return ""
    if not env("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL"):
        return "destination is outside this deployment and AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL is off"
    if not is_public_url(url):
        return "destination is not a public address"
    return ""


def destination_allowed(service: str, url: str) -> bool:
    """Apply the egress policy to a tracing destination and log the decision (never a key)."""
    reason = _refusal(url)
    origin = normalize_origin(url) or "<invalid>"
    if reason:
        logger.warning("LLM tracing to %s refused (%s): %s", service, origin, reason)
        return False
    logger.info("LLM tracing active: %s -> %s (content sent: %s)", service, origin, include_content())
    return True


def include_content() -> bool:
    return bool(env("AUTOBOT_LLM_TRACING_INCLUDE_CONTENT"))


def trace_messages(messages: Any) -> Any:
    """Request messages as a tracing observer may send them."""
    if not include_content():
        return CONTENT_OMITTED
    return redact_dict({"messages": messages})["messages"]


def trace_text(text: Any) -> Any:
    """Response or error text as a tracing observer may send it."""
    if not include_content():
        return CONTENT_OMITTED
    return redact_string(text) if isinstance(text, str) else text
