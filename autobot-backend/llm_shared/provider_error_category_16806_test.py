# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The provider error taxonomy (#16806): classification, and agreement with the special cases it absorbs."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import aiohttp
import pytest

from llm_shared.models import LLMResponse
from llm_shared.provider_auth import ProviderAuthError, TokenExpiredError
from llm_shared.provider_error_category import (
    ProviderErrorCategory,
    classify_provider_error,
    failure_from_exception,
    failure_from_response,
    failure_from_status,
)
from llm_shared.rate_limit_backoff import extract_rate_limit_info

C = ProviderErrorCategory


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("HTTP 503", C.PROVIDER_UNAVAILABLE),
        ("status: 529 overloaded", C.PROVIDER_UNAVAILABLE),
        ("The server is overloaded", C.PROVIDER_UNAVAILABLE),
        ("Connection refused", C.NETWORK),
        ("request timed out after 30s", C.TIMEOUT),
        ("HTTP 401 Unauthorized", C.AUTHENTICATION),
        ("invalid api key provided", C.AUTHENTICATION),
        ("429 too many requests", C.RATE_LIMIT),
        ("You exceeded your current quota, check your plan and billing details (429)", C.BILLING),
        ("HTTP 402 payment required", C.BILLING),
        ("HTTP 400 invalid request", C.PERMANENT),
        ("model 'x' not found", C.PERMANENT),
        ("something nobody anticipated", C.UNKNOWN),
        ("listening on port 5432 with 512 tokens", C.UNKNOWN),  # a bare number is not a status
        ("error: limit 512", C.UNKNOWN),  # "error" is not a status marker, and 512 is not a status
        ("Invalid value for max_tokens", C.UNKNOWN),  # not an auth failure: "token" inside a parameter name
        ("HTTP 408 Request Timeout", C.TIMEOUT),
    ],
)
def test_text_is_classified(text, expected):
    assert classify_provider_error(text).category is expected


def test_a_plan_limit_outranks_the_429_it_arrives_in():
    assert classify_provider_error("429 insufficient_quota").category is C.BILLING


@pytest.mark.parametrize(
    "text", ["rate limit hit", "Too Many Requests", "429", "quota exceeded", "throttled", "all good"]
)
def test_rate_limit_agrees_with_the_backoff_pattern_set(text):
    """The rate-limit special case is mapped, not copied: the same patterns decide it (#16806 AC2)."""
    flagged = extract_rate_limit_info(LLMResponse(content="", error=text))[0]
    category = classify_provider_error(text).category
    assert flagged == (category in (C.RATE_LIMIT, C.BILLING))


def test_response_carries_the_stated_reset():
    response = LLMResponse(content="", error="429 rate limit, retry after: 12")
    failure = failure_from_response(response)
    assert failure.category is C.RATE_LIMIT
    assert failure.retry_after == 12.0


def test_a_successful_response_has_no_failure():
    assert failure_from_response(LLMResponse(content="ok")) is None


def test_status_and_exception_entry_points():
    assert failure_from_status(503).category is C.PROVIDER_UNAVAILABLE
    assert failure_from_exception(asyncio.TimeoutError()).category is C.TIMEOUT
    assert failure_from_exception(ConnectionResetError("reset")).category is C.NETWORK
    assert failure_from_exception(aiohttp.ClientConnectionError("refused")).category is C.NETWORK
    assert failure_from_exception(aiohttp.ServerTimeoutError("slow")).category is C.TIMEOUT
    http_error = aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=503)
    assert failure_from_exception(http_error).category is C.PROVIDER_UNAVAILABLE


def test_the_auth_exception_family_is_authentication():
    """``TokenExpiredError`` is what marks ``DegradationCause.NEEDS_REAUTH``; both map to AUTHENTICATION (#16806 AC2)."""
    assert issubclass(TokenExpiredError, ProviderAuthError)
    assert failure_from_exception(ProviderAuthError("no token")).category is C.AUTHENTICATION
    assert failure_from_exception(TokenExpiredError("expired")).category is C.AUTHENTICATION


def test_only_recoverable_categories_are_failover_eligible():
    assert {c for c in C if c.failover_eligible} == {
        C.RATE_LIMIT,
        C.BILLING,
        C.PROVIDER_UNAVAILABLE,
        C.NETWORK,
        C.TIMEOUT,
        C.AUTHENTICATION,
    }
    assert [c for c in C if c.holds_until_reset] == [C.BILLING]


@pytest.mark.parametrize(
    "body",
    [
        "HTTP 400: max_tokens must be at most 4096",
        "HTTP 400: the timeout parameter is invalid",
        "HTTP 400: billing address is malformed",
        "Error code: 400 - the request timed out while validating billing",
        "HTTP 404 model not found",
        "HTTP 413 request too large",
        "HTTP 422 unprocessable",
        "HTTP 418",
    ],
)
def test_a_4xx_outside_the_auth_billing_timeout_set_is_permanent_whatever_its_body_says(body):
    """The status decides; the body only refines inside it. A 400 that mentions timeout/billing is still a bad request."""
    failure = classify_provider_error(body)
    assert failure.category is C.PERMANENT
    assert not failure.category.failover_eligible


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, C.AUTHENTICATION), (402, C.BILLING), (403, C.AUTHENTICATION), (408, C.TIMEOUT), (429, C.RATE_LIMIT),
     (500, C.PROVIDER_UNAVAILABLE), (503, C.PROVIDER_UNAVAILABLE), (529, C.PROVIDER_UNAVAILABLE), (400, C.PERMANENT)],
)  # fmt: skip
def test_the_status_alone_decides(status, expected):
    assert failure_from_status(status).category is expected


def test_a_429_that_names_a_plan_limit_is_billing_and_a_plain_429_is_a_throttle():
    assert classify_provider_error("HTTP 429 insufficient_quota").category is C.BILLING
    assert classify_provider_error("HTTP 429 slow down").category is C.RATE_LIMIT


def test_an_explicit_status_beats_the_words_around_it():
    assert classify_provider_error("connection refused", status=503).category is C.PROVIDER_UNAVAILABLE
    assert classify_provider_error("HTTP 503 but the text says unauthorized").category is C.PROVIDER_UNAVAILABLE


def test_an_exception_type_beats_its_message():
    assert failure_from_exception(asyncio.TimeoutError("HTTP 401")).category is C.TIMEOUT
