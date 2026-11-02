# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One named taxonomy for LLM provider failures (#16806).

Before this, "what kind of failure was that" was answered separately by each
mechanism: the circuit breaker excluded rate limits (``base_provider``), the
degradation store knew only ``NEEDS_REAUTH`` vs ``TRANSIENT``
(``provider_degradation``), and everything else was an untyped string. This is
the additive layer both can read -- it replaces neither, so
``BaseProvider.chat_completion()`` is untouched.

The existing special cases are *mapped onto* it, not copied:

* rate limit  -- the pattern set stays in ``rate_limit_backoff``
  (``extract_rate_limit_info``); a response it flags is ``RATE_LIMIT`` here.
* auth        -- the ``ProviderAuthError`` family (``TokenExpiredError`` is what marks
  ``DegradationCause.NEEDS_REAUTH``) is ``AUTHENTICATION`` here. Failover marks it with the
  plain skip window, not ``NEEDS_REAUTH``: that state is the credential machine's, set from a
  known-dead token, and a text-derived 401 must not park a provider until someone clears it.

Named ``ProviderErrorCategory`` because ``utils.error_boundaries`` already owns
an ``ErrorCategory`` for application errors, which is a different question.
The failover decision (#19753) is the first consumer; unifying breaker +
degradation onto this taxonomy is deliberately a separate follow-up.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import aiohttp

from .models import LLMResponse
from .provider_auth import ProviderAuthError
from .rate_limit_backoff import extract_rate_limit_info


class ProviderErrorCategory(str, Enum):
    """Why a provider call failed, in the terms a recovery decision needs."""

    RATE_LIMIT = "rate_limit"  # transient throttle; the backoff handler owns the retry
    BILLING = "billing"  # plan, quota or credit exhausted -- holds until it resets
    PROVIDER_UNAVAILABLE = "provider_unavailable"  # 5xx, overloaded
    NETWORK = "network"  # connection refused / reset / DNS
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"  # 401 / 403 / bad credential
    PERMANENT = "permanent"  # the request itself is wrong; another model will fail the same way
    UNKNOWN = "unknown"  # unclassified: surfaced, never failed over

    @property
    def failover_eligible(self) -> bool:
        """True when a different model/provider can plausibly succeed where this one failed."""
        return self not in (ProviderErrorCategory.PERMANENT, ProviderErrorCategory.UNKNOWN)

    @property
    def holds_until_reset(self) -> bool:
        """True when the failed model stays unusable until a quota resets, not just for a skip window."""
        return self is ProviderErrorCategory.BILLING


@dataclass(frozen=True)
class ProviderFailure:
    """A classified failure: the category, the provider's words, its stated reset and HTTP status if any."""

    category: ProviderErrorCategory
    message: str
    retry_after: Optional[float] = None
    status: Optional[int] = None


#: An HTTP status is only read where the text says so ("HTTP 503", "status: 503", "Error code: 503").
_STATUS_RE = re.compile(r"\b(?:http(?:/\d(?:\.\d)?)?|status(?: code)?|error code)\b[\s:=]*(\d{3})\b", re.IGNORECASE)

_BILLING_RE = re.compile(
    r"\binsufficient[_ ]quota\b|\bexceeded your current quota\b|\bbilling\b|\bcredit balance\b"
    r"|\bpayment required\b|\bplan limit\b",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    r"\bunauthori[sz]ed\b|\bforbidden\b|\binvalid[_ -]?(?:api[_ -]?key|token|credentials?)\b"
    r"|\bauthentication (?:failed|error)\b",
    re.IGNORECASE,
)
_UNAVAILABLE_RE = re.compile(
    r"\boverloaded\b|\bservice unavailable\b|\bbad gateway\b|\btemporarily unavailable\b|\binternal server error\b",
    re.IGNORECASE,
)
_TIMEOUT_RE = re.compile(r"\btimed out\b|\b(?:read|connect|request) time-?out\b|\bdeadline exceeded\b", re.IGNORECASE)
_NETWORK_RE = re.compile(
    r"\bconnection (?:refused|reset|error|aborted)\b|\bcannot connect\b|\bunreachable\b|\bname resolution\b"
    r"|\bbroken pipe\b",
    re.IGNORECASE,
)
_PERMANENT_RE = re.compile(
    r"\binvalid request\b|\bmodel\b.{0,20}\bnot found\b|\bcontext length\b|\bcontent policy\b", re.IGNORECASE
)

#: Used only when the error carries no status; first match wins, after BILLING and RATE_LIMIT.
_TEXT_RULES: tuple[tuple[re.Pattern, ProviderErrorCategory], ...] = (
    (_AUTH_RE, ProviderErrorCategory.AUTHENTICATION),
    (_TIMEOUT_RE, ProviderErrorCategory.TIMEOUT),
    (_NETWORK_RE, ProviderErrorCategory.NETWORK),
    (_UNAVAILABLE_RE, ProviderErrorCategory.PROVIDER_UNAVAILABLE),
    (_PERMANENT_RE, ProviderErrorCategory.PERMANENT),
)

#: The only 4xx statuses that mean something other than "the request is wrong".
_STATUS_CATEGORIES = {
    401: ProviderErrorCategory.AUTHENTICATION,
    402: ProviderErrorCategory.BILLING,
    403: ProviderErrorCategory.AUTHENTICATION,
    408: ProviderErrorCategory.TIMEOUT,
    429: ProviderErrorCategory.RATE_LIMIT,
}


def _category_of_status(status: int, text: str) -> Optional[ProviderErrorCategory]:
    """The category a status decides on its own, or ``None`` for a status that says nothing (2xx, 3xx).

    Any 4xx outside ``_STATUS_CATEGORIES`` is PERMANENT whatever its body mentions: a 400 about
    ``max_tokens``, a timeout setting or billing is still a malformed request. A 429 is a throttle,
    or a plan limit when its body says so (the one place text refines a status).
    """
    if status == 429 and _BILLING_RE.search(text):
        return ProviderErrorCategory.BILLING
    if status in _STATUS_CATEGORIES:
        return _STATUS_CATEGORIES[status]
    if 500 <= status <= 599:
        return ProviderErrorCategory.PROVIDER_UNAVAILABLE
    return ProviderErrorCategory.PERMANENT if 400 <= status <= 499 else None


def _category_of_text(text: str) -> ProviderErrorCategory:
    """Text-only classification, for an error that carries no status. BILLING outranks RATE_LIMIT."""
    if _BILLING_RE.search(text):
        return ProviderErrorCategory.BILLING
    if extract_rate_limit_info(LLMResponse(content="", error=text))[0]:
        return ProviderErrorCategory.RATE_LIMIT
    for pattern, category in _TEXT_RULES:
        if pattern.search(text):
            return category
    return ProviderErrorCategory.UNKNOWN


def classify_provider_error(
    text: str, retry_after: Optional[float] = None, status: Optional[int] = None
) -> ProviderFailure:
    """Classify a provider error: *status* (given, or read from the text) first; text only when none decides."""
    if status is None:
        found = _STATUS_RE.search(text)
        status = int(found.group(1)) if found else None
    category = None if status is None else _category_of_status(status, text)
    return ProviderFailure(category or _category_of_text(text), text, retry_after, status)


def failure_from_response(response: LLMResponse) -> Optional[ProviderFailure]:
    """The classified failure of an error response, or ``None`` when the response succeeded."""
    if not response.error:
        return None
    _, retry_after = extract_rate_limit_info(response)
    return classify_provider_error(str(response.error), retry_after)


def failure_from_status(status: int) -> ProviderFailure:
    """Classify a bare HTTP status (the chat path sees the status, not a provider's error string)."""
    return classify_provider_error(f"HTTP {status}", status=status)


def failure_from_exception(exc: BaseException) -> ProviderFailure:
    """Classify a raised transport/auth error by type first, then by its message."""
    message = str(exc) or type(exc).__name__
    if isinstance(exc, ProviderAuthError):
        return ProviderFailure(ProviderErrorCategory.AUTHENTICATION, message)
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ProviderFailure(ProviderErrorCategory.TIMEOUT, message)
    if isinstance(exc, aiohttp.ClientResponseError):
        return classify_provider_error(message, status=exc.status)
    if isinstance(exc, (aiohttp.ClientError, OSError)):
        return ProviderFailure(ProviderErrorCategory.NETWORK, message)
    return classify_provider_error(message)


__all__ = [
    "ProviderErrorCategory",
    "ProviderFailure",
    "classify_provider_error",
    "failure_from_exception",
    "failure_from_response",
    "failure_from_status",
]
