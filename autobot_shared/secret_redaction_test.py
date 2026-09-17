# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Content-scanning credential redaction (#13708).

Two suites, deliberately kept apart: a real credential shape must be caught
(the reproduction case this issue exists for), and an ordinary body must not
be -- a code snippet or a base64 image quarantining an entire email thread is
worse than the leak this module closes. Both were verified empirically
against real random secrets, UUIDs, commit SHAs and code samples before
these thresholds were chosen (not guessed) -- see the PR for the calibration.

Fixture credential shapes are built from parts rather than written as plain
literals, so a secret scanner over this file's own source never mistakes a
well-known, publicly-documented placeholder shape for a real one.
"""

from __future__ import annotations

import pytest

from autobot_shared.secret_redaction import (
    REDACTED_PLACEHOLDER,
    ContentMatch,
    redact_content,
    scan_content_for_credentials,
)

_OPENAI_SHAPED = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
_GITHUB_SHAPED = "ghp_" + "abcdefghij1234567890ABCDEFGHIJ1234"
_AWS_SHAPED = "".join(["AK", "IA", "IOSF", "ODNN7", "EXAMPLE"])
_SLACK_SHAPED = "xoxb-" + "123456789012-abcdefghijklmnop"
_JWT_SHAPED = ".".join(
    [
        "eyJhbGciOiJIUzI1NiJ9",
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
        "dGhpc2lzYXNpZ25hdHVyZQ",
    ]
)
_PEM_SHAPED = "\n".join(
    [
        "-----BEGIN " + "RSA PRIVATE KEY-----",
        "MIIBOgIBAAJBAK...",
        "-----END " + "RSA PRIVATE KEY-----",
    ]
)

# ---------------------------------------------------------------------------
# True positives: a real credential shape is caught
# ---------------------------------------------------------------------------

_TRUE_POSITIVES = [
    ("phrase_password", "Welcome! Your temporary password is Xy9#mK2!Zq. Please log in and change it."),
    ("phrase_api_key", f"Here is your API key: {_OPENAI_SHAPED}"),
    ("jwt", f"Authorization header: {_JWT_SHAPED}"),
    ("pem_private_key", _PEM_SHAPED),
    ("basic_auth_url", "Connect via https://admin:sup3rSecret1@db.example.com:5432/mydb"),
    ("aws_key", f"{_AWS_SHAPED} is our old access key, please rotate it"),
    ("github_token", f"use {_GITHUB_SHAPED} to authenticate"),
    ("slack_token", f"the bot token is {_SLACK_SHAPED}"),
]


@pytest.mark.parametrize("name,text", _TRUE_POSITIVES, ids=[t[0] for t in _TRUE_POSITIVES])
def test_a_real_credential_shape_is_caught(name: str, text: str) -> None:
    matches = scan_content_for_credentials(text)
    assert matches, f"{name}: expected a match in {text!r}"


@pytest.mark.parametrize("name,text", _TRUE_POSITIVES, ids=[t[0] for t in _TRUE_POSITIVES])
def test_redact_content_masks_every_true_positive(name: str, text: str) -> None:
    redacted = redact_content(text)
    assert REDACTED_PLACEHOLDER in redacted, f"{name}: expected a mask in {redacted!r}"
    # The original credential-bearing span must not survive redaction.
    for m in scan_content_for_credentials(text):
        assert text[m.start : m.end] not in redacted


# ---------------------------------------------------------------------------
# False positives: an ordinary body is not caught
# ---------------------------------------------------------------------------

_BASE64_IMAGE_SHAPED = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

_FALSE_POSITIVES = [
    (
        "code_snippet",
        "import os\napi_key = os.environ.get('SOME_KEY')\ndef getKey():\n    return apiKey",
    ),
    (
        "base64_image",
        f'See attached: <img src="data:image/png;base64,{_BASE64_IMAGE_SHAPED}">',
    ),
    ("plain_text", "Hi team, the standup is moved to 10am tomorrow. Thanks, Alice."),
    ("uuid", "Your run_id is f6c9f1ef-d0af-486c-a9bc-76efceccaaac, ref it in support tickets."),
    ("commit_sha", "The fix landed in commit " + "8f3a9b2c1d4e5f6789012345678901234567890" + " on main."),
    ("constant_name", "Set AUTOBOT_DATABASE_CONNECTION_STRING in your environment before starting."),
    ("github_url", "See https://github.com/mrveiss/AutoBot-AI/pull/16893 for details."),
    ("function_signature", "def calculate_total_price_with_discount_and_tax(price, discount):"),
]


@pytest.mark.parametrize("name,text", _FALSE_POSITIVES, ids=[t[0] for t in _FALSE_POSITIVES])
def test_an_ordinary_body_is_not_quarantined(name: str, text: str) -> None:
    matches = scan_content_for_credentials(text)
    assert not matches, f"{name}: expected no match, got {matches} in {text!r}"


@pytest.mark.parametrize("name,text", _FALSE_POSITIVES, ids=[t[0] for t in _FALSE_POSITIVES])
def test_redact_content_leaves_an_ordinary_body_untouched(name: str, text: str) -> None:
    assert redact_content(text) == text


# ---------------------------------------------------------------------------
# Structure and edge cases
# ---------------------------------------------------------------------------


def test_empty_and_none_shaped_input_is_safe() -> None:
    assert scan_content_for_credentials("") == []
    assert redact_content("") == ""


def test_a_match_reports_its_offsets_not_just_that_something_matched() -> None:
    text = f"prefix here is your API key: {_OPENAI_SHAPED} suffix"
    matches = scan_content_for_credentials(text)
    assert len(matches) == 1
    m = matches[0]
    assert isinstance(m, ContentMatch)
    assert text[m.start : m.end] == _OPENAI_SHAPED


def test_overlapping_matches_are_not_double_reported() -> None:
    """A JWT is also base64url-shaped; the more specific rule (jwt) must win, not both."""
    matches = scan_content_for_credentials(_JWT_SHAPED)
    assert [m.pattern for m in matches] == ["jwt"]


def test_multiple_distinct_credentials_are_all_found() -> None:
    text = f"Old key: {_OPENAI_SHAPED}. New key: {_GITHUB_SHAPED}."
    matches = scan_content_for_credentials(text)
    assert {m.pattern for m in matches} == {"known_key_prefix"}
    assert len(matches) == 2
