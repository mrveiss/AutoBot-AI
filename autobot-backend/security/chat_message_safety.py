# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Raw-chat-message safety scan: PII + prompt-injection (#16529, #16530).

Internal audit of the LLM request pipeline found two gaps on the main chat
path in ``api/chat.py``:

- The only wired PII detector in the codebase (``a2a/pii_pipeline.py``) ran
  on outbound A2A task payloads only -- never on the literal user chat
  message.
- The prompt-injection detector (``security/prompt_injection_detector.py``)
  was wired to specific features (screen analysis, KB transcript,
  advanced-workflow intent) and the content firewall guards tool/web/MCP
  output -- neither ever ran on the raw chat message on a plain turn.

``scan_chat_message()`` is the one function every raw-message entry point in
``api/chat.py`` now calls before the message reaches an LLM or persistent
storage.

Policy
------
PII: reuses the exact BLOCK/REDACT/HASH table already proven on the A2A
path, via the same ``scrub_outbound()`` entry point -- SSN/API-key/card/JWT
-shaped content raises ``PIIBlocked`` (surfaced here as a 400, same as a
blocked A2A send); lower-severity types (email, phone, IP, ...) are
redacted in the text this returns, so neither the model nor chat history
ever see the raw value.

Injection: flagged and logged, not blocked, by default. The shared
detector's pattern set was built for narrower, structured inputs (a
screen-analysis goal, an intent string) and false-positives on ordinary
conversational phrasing -- measured directly against a realistic benign-
message sample while wiring this in, "You are a huge help, thank you so
much." and "I am writing a new instructions manual for my team, any tips?"
both read CRITICAL under ``detect_injection()``'s default risk mapping.
Hard-blocking every HIGH/CRITICAL hit would reject unremarkable chat turns,
which is the false-positive regression #16530 explicitly guards against.
Only ``hard_blocked`` -- the existing confidence-gated signal an operator
opts into via ``AUTOBOT_INJECTION_HARDBLOCK_ENABLED`` (default off) --
rejects the turn here; every other HIGH/CRITICAL hit is logged as a
security event for audit/trend visibility without disrupting the
conversation.
"""

from __future__ import annotations

from fastapi import HTTPException

from a2a.pii_pipeline import PIIBlocked, scrub_outbound
from autobot_shared.logging_manager import get_logger
from security.prompt_injection_detector import get_prompt_injection_detector

logger = get_logger(__name__)


def _scrub_pii(content: str, session_id: str | None) -> str:
    """Redact/block PII via the shared A2A pipeline; returns the safe text."""
    try:
        scrub_result = scrub_outbound(content, peer_id=session_id)
    except PIIBlocked as exc:
        logger.warning("Chat message blocked by PII pipeline (session=%s): %s", session_id, exc)
        raise HTTPException(
            status_code=400,
            detail="Message blocked: it appears to contain sensitive data "
            "(e.g. SSN, API key, card number) that cannot be sent to the assistant.",
        )
    if scrub_result.redaction_count:
        logger.info(
            "Chat message (session=%s): redacted %d PII item(s) before LLM/storage",
            session_id,
            scrub_result.redaction_count,
        )
    return scrub_result.text


def _flag_injection(content: str, session_id: str | None) -> None:
    """Flag-and-log injection risk; raise only on the opt-in hard-block signal."""
    # strict_mode=True matches every other caller of this singleton (prompt_manager.py,
    # screen_analysis_prompt.py, intent_analyzer.py, ...) -- lazy_singleton() raises if a
    # later caller passes different construction args than the first, so this must agree.
    detection = get_prompt_injection_detector(strict_mode=True).detect_injection(content, context="user_input")
    if detection.hard_blocked:
        logger.warning(
            "Chat message hard-blocked by injection detector (session=%s, confidence=%.2f, patterns=%s)",
            session_id,
            detection.confidence_score,
            detection.detected_patterns,
        )
        raise HTTPException(
            status_code=400,
            detail="Message blocked: detected a high-confidence prompt-injection pattern.",
        )
    if detection.blocked:
        logger.warning(
            "Chat message flagged by injection detector (session=%s, risk=%s, patterns=%s) -- "
            "not blocking, logged for review",
            session_id,
            detection.risk_level.value,
            detection.detected_patterns,
        )


def scan_chat_message(content: str, session_id: str | None = None) -> str:
    """Scan a raw chat message for PII and injection risk (#16529, #16530).

    Returns the text to use from here on (PII-redacted where policy
    requires it). Raises HTTPException(400) if the PII policy blocks the
    message, or if injection hard-block is enabled and this message trips it.
    """
    content = _scrub_pii(content, session_id)
    _flag_injection(content, session_id)
    return content
