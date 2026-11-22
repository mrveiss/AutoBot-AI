# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
One policy for every LLM tracing observer (#19933).

Two decisions live here so no observer carries its own copy:

* ``destination_allowed`` -- may this tracing destination be activated at all?
  The origin must be strictly shaped (``egress_allowlist.strict_origin``: no userinfo, backslash,
  encoded or non-ASCII authority) and either listed in ``AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS`` or,
  with ``AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL``, a public address. SSOT service origins (the LLM or
  backend URL) are deliberately NOT trusted: they are not tracing services.
* ``trace_messages`` / ``trace_text`` / ``trace_ident`` -- what an observer may send. Prompt,
  response and error text are withheld unless ``AUTOBOT_LLM_TRACING_INCLUDE_CONTENT``; then they pass
  ``credential_redaction`` and the outbound PII pipeline (``a2a.pii_pipeline.scrub_outbound``). A
  blocked or failing scrub sends the omitted marker, because an observer callback must not raise.

**Residual, stated rather than discovered.** ``destination_allowed`` is a *startup* check on the
configured URL. There is no redirect or DNS-rebind protection at send time, because the tracing
client libraries open their own connections instead of using the guarded HTTP client; a hostname
that resolves publicly at startup is trusted wherever it resolves later. Origins registered at
runtime by SLM (``egress_allowlist`` providers) are not consulted. A guarded tracing client is the
follow-up that closes both.
"""

from __future__ import annotations

import re
from typing import Any

from a2a.pii_pipeline import PIIBlocked, scrub_outbound
from autobot_shared.egress_allowlist import operator_origins, strict_origin
from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger
from autobot_shared.url_safety import is_public_url
from llm_shared.credential_redaction import redact_dict

logger = get_logger(__name__)

CONTENT_OMITTED = "[content omitted by tracing policy]"
_IDENT_RE = re.compile(r"[A-Za-z0-9_.:\-]{1,128}")


def _listed_origins() -> frozenset[str]:
    return operator_origins(e.strip() for e in str(env("AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS")).split(",") if e.strip())


def _refusal(url: str) -> str:
    """Why *url* may not be a tracing destination, or ``""`` when it may."""
    origin = strict_origin(url)
    if origin is None:
        return "destination is not a strictly shaped http(s) origin"
    if origin in _listed_origins():
        return ""
    if not env("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL"):
        return "destination is not in AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS and AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL is off"
    if not is_public_url(url):
        return "destination is not a public address"
    return ""


def destination_allowed(service: str, url: str) -> bool:
    """Apply the destination policy and log the decision (origin only, never a key)."""
    reason = _refusal(url)
    origin = strict_origin(url) or "<invalid>"
    if reason:
        logger.warning("LLM tracing to %s refused (%s): %s", service, origin, reason)
        return False
    logger.info("LLM tracing active: %s -> %s (content sent: %s)", service, origin, include_content())
    return True


def include_content() -> bool:
    return bool(env("AUTOBOT_LLM_TRACING_INCLUDE_CONTENT"))


def _scrub_strings(value: Any) -> Any:
    """Run every string leaf through the outbound PII pipeline; raises ``PIIBlocked``."""
    if isinstance(value, str):
        return scrub_outbound(value).text
    if isinstance(value, dict):
        return {k: _scrub_strings(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_strings(v) for v in value]
    return value


def _outbound(value: Any) -> Any:
    """Redact then scrub *value*; the omitted marker if the scrub blocks or fails."""
    try:
        return _scrub_strings(redact_dict({"v": value})["v"])
    except PIIBlocked as exc:
        logger.warning("LLM tracing content withheld: outbound PII policy blocked %s", exc.blocked_types)
    except Exception as exc:  # noqa: BLE001 -- an observer callback must not raise; fail closed
        logger.warning("LLM tracing content withheld: scrub failed (%s)", type(exc).__name__)
    return CONTENT_OMITTED


def trace_messages(messages: Any) -> Any:
    """Request messages as a tracing observer may send them."""
    return _outbound(messages) if include_content() else CONTENT_OMITTED


def trace_text(text: Any) -> Any:
    """Response or error text as a tracing observer may send it."""
    return _outbound(text) if include_content() else CONTENT_OMITTED


def trace_ident(value: Any) -> Any:
    """An id-like metadata field: kept only when it is a short token, else ``None``.

    ``request.metadata`` is caller-populated (``agent_id``/``run_id`` have no producer that
    guarantees an id shape), so free-form text must not reach a tracing service through it.
    """
    if isinstance(value, str) and _IDENT_RE.fullmatch(value):
        return value
    return None
