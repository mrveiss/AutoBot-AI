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
    """A classified failure: the category, the provider's words, and its stated reset if any."""

    category: ProviderErrorCategory
    message: str
    retry_after: Optional[float] = None


#: A bare number is only a status when something says so ("HTTP 503", "status: 503", "error code 503").
_CODE = r"(?:http|status|error|code)\D{0,8}"

_BILLING_RE = re.compile(
    r"insufficient.quota|exceeded your current quota|billing|credit balance|payment required|plan limit|"
    + _CODE
    + r"402",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    _CODE + r"40[13]|unauthori[sz]ed|forbidden|invalid.{0,12}(api.?key|token|credential)|authentication",
    re.IGNORECASE,
)
_UNAVAILABLE_RE = re.compile(
    _CODE + r"5\d\d|overloaded|service unavailable|bad gateway|temporarily unavailable|server error",
    re.IGNORECASE,
)
_TIMEOUT_RE = re.compile(r"time.?d? ?out|deadline exceeded", re.IGNORECASE)
_NETWORK_RE = re.compile(
    r"connection (refused|reset|error|aborted)|cannot connect|unreachable|name resolution|dns|broken pipe",
    re.IGNORECASE,
)
_PERMANENT_RE = re.compile(
    _CODE + r"(400|404|413|422)|invalid request|model.{0,20}not found|context.length|content.policy",
    re.IGNORECASE,
)

#: Checked in order, after BILLING and RATE_LIMIT: the first match wins.
_TEXT_RULES: tuple[tuple[re.Pattern, ProviderErrorCategory], ...] = (
    (_AUTH_RE, ProviderErrorCategory.AUTHENTICATION),
    (_TIMEOUT_RE, ProviderErrorCategory.TIMEOUT),
    (_NETWORK_RE, ProviderErrorCategory.NETWORK),
    (_UNAVAILABLE_RE, ProviderErrorCategory.PROVIDER_UNAVAILABLE),
    (_PERMANENT_RE, ProviderErrorCategory.PERMANENT),
)


def _category_of(text: str) -> ProviderErrorCategory:
    """BILLING before RATE_LIMIT: a 429 that names billing is a plan limit, not a throttle."""
    if _BILLING_RE.search(text):
        return ProviderErrorCategory.BILLING
    if extract_rate_limit_info(LLMResponse(content="", error=text))[0]:
        return ProviderErrorCategory.RATE_LIMIT
    for pattern, category in _TEXT_RULES:
        if pattern.search(text):
            return category
    return ProviderErrorCategory.UNKNOWN


def classify_error(text: str, retry_after: Optional[float] = None) -> ProviderFailure:
    """Classify a provider error string. Rate limits are decided by ``rate_limit_backoff``'s pattern set."""
    return ProviderFailure(_category_of(text), text, retry_after)


def failure_from_response(response: LLMResponse) -> Optional[ProviderFailure]:
    """The classified failure of an error response, or ``None`` when the response succeeded."""
    if not response.error:
        return None
    _, retry_after = extract_rate_limit_info(response)
    return classify_error(str(response.error), retry_after)


def failure_from_status(status: int) -> ProviderFailure:
    """Classify a bare HTTP status (the chat path sees the status, not a provider's error string)."""
    return classify_error(f"HTTP {status}")


def failure_from_exception(exc: BaseException) -> ProviderFailure:
    """Classify a raised transport/auth error by type first, then by its message."""
    message = str(exc) or type(exc).__name__
    if isinstance(exc, ProviderAuthError):
        return ProviderFailure(ProviderErrorCategory.AUTHENTICATION, message)
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ProviderFailure(ProviderErrorCategory.TIMEOUT, message)
    if isinstance(exc, aiohttp.ClientResponseError):
        return failure_from_status(exc.status)
    if isinstance(exc, (aiohttp.ClientError, OSError)):
        return ProviderFailure(ProviderErrorCategory.NETWORK, message)
    return classify_error(message)


__all__ = [
    "ProviderErrorCategory",
    "ProviderFailure",
    "classify_error",
    "failure_from_exception",
    "failure_from_response",
    "failure_from_status",
]
