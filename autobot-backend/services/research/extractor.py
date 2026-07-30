# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Atomic-claim extraction from a fetched research page (#12622, design §4.5).

Reuses the shared LLM service and the shared fence-tolerant JSON parser
(``llm_shared.json_utils``) rather than inventing a new prompt-parsing layer.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from llm_shared.json_utils import extract_json_object

from .models import ExtractedClaim

logger = get_logger(__name__)

# A claim must share at least this fraction of its distinctive (4+ char)
# words with the source text to count as "supported" — a cheap, deterministic
# anti-hallucination guard (design §4.5: "no claim invented that isn't
# supported by the fetched text").
_MIN_SUPPORT_OVERLAP = 0.5
_WORD_RE = re.compile(r"[a-z0-9]{4,}")

_EXTRACTION_SYSTEM_PROMPT = (
    "You extract atomic factual claims from web page text for a research tool. "
    "Rules: (1) every claim must be directly stated or clearly implied by the "
    "given text — never add outside knowledge; (2) each claim is one "
    "self-contained sentence; (3) assign a confidence 0.0-1.0 reflecting how "
    "explicitly the text states it. Respond with ONLY a JSON object: "
    '{"claims": [{"content": str, "confidence": float}, ...]}. '
    "If the text contains no extractable factual claims, return an empty list."
)


def _build_extraction_messages(content: str) -> List[Dict[str, str]]:
    """Build the chat messages for one claim-extraction call."""
    return [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _distinctive_words(text: str) -> set:
    """Return the lowercase 4+ char word set of *text* (cheap overlap key)."""
    return set(_WORD_RE.findall(text.lower()))


def _is_supported_by_source(claim_text: str, source_content: str) -> bool:
    """Reject a claim whose wording has little overlap with the source text."""
    claim_words = _distinctive_words(claim_text)
    if not claim_words:
        return False
    source_words = _distinctive_words(source_content)
    overlap = len(claim_words & source_words) / len(claim_words)
    return overlap >= _MIN_SUPPORT_OVERLAP


def _parse_claims_payload(raw_content: str) -> List[Dict[str, Any]]:
    """Parse the LLM's JSON response into a list of raw claim dicts."""
    try:
        payload = extract_json_object(raw_content)
    except json.JSONDecodeError:
        logger.warning("extract_claims: LLM response was not valid JSON; skipping page")
        return []
    claims = payload.get("claims", [])
    return claims if isinstance(claims, list) else []


def _to_extracted_claim(raw: Dict[str, Any], url: str, doc_id: str) -> ExtractedClaim | None:
    """Convert one raw claim dict to an ``ExtractedClaim``, or None if malformed."""
    text = str(raw.get("content", "")).strip()
    if not text:
        return None
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return ExtractedClaim(content=text, confidence=confidence, source_url=url, source_doc_id=doc_id)


async def extract_claims(
    llm_service: Any,
    content: str,
    url: str,
    source_doc_id: str,
    max_content_chars: int,
) -> List[ExtractedClaim]:
    """Extract atomic, source-supported claims from one fetched page.

    Truncates *content* to *max_content_chars* (token-ceiling budget, design
    §4.1) before sending it to the LLM. Every returned claim has already
    passed the ``_is_supported_by_source`` overlap guard.
    """
    truncated = content[:max_content_chars]
    response = await llm_service.chat(messages=_build_extraction_messages(truncated), temperature=0.0)
    if response.error:
        logger.warning("extract_claims: LLM call failed for %s: %s", url, response.error)
        return []

    claims: List[ExtractedClaim] = []
    for raw in _parse_claims_payload(response.content):
        claim = _to_extracted_claim(raw, url, source_doc_id)
        if claim is not None and _is_supported_by_source(claim.content, truncated):
            claims.append(claim)
    return claims
