# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared webhook verifier and its former callers (#18452)."""

import hashlib
import hmac

import pytest

from autobot_shared.webhook_signature import verify_webhook_signature


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature():
    assert verify_webhook_signature(b"x", _sign(b"x", "s"), "s") is True


@pytest.mark.parametrize(
    "header,secret",
    [(None, "s"), ("", "s"), ("md5=ab", "s"), ("deadbeef", "s"), ("sha256=00", "s"), (None, ""), ("sha256=00", "")],
)
def test_rejected(header, secret):
    assert verify_webhook_signature(b"x", header, secret) is False


def test_empty_secret_fails_closed_even_with_matching_hmac():
    assert verify_webhook_signature(b"x", _sign(b"x", ""), "") is False


def test_former_callers_resolve_to_the_shared_function():
    from autobot_shared import webhook_signature as shared

    github = pytest.importorskip("llc.api.github_webhooks")
    whatsapp = pytest.importorskip("api.whatsapp")
    assert github.verify_webhook_signature is shared.verify_webhook_signature
    assert whatsapp.verify_webhook_signature is shared.verify_webhook_signature


@pytest.mark.parametrize("header", ["sha256=é" * 2, "sha256=" + "€" * 64, "sha256=\udcff"])
def test_non_ascii_header_returns_false_not_typeerror_18464(header):
    assert verify_webhook_signature(b"x", header, "s") is False
