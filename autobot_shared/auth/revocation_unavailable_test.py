# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared "revocation check unavailable" answer (#18892)."""

from autobot_shared.auth import revocation_unavailable as mod


def test_it_is_a_503_with_a_stable_detail_and_retry_after():
    exc = mod.revocation_unavailable_error()
    assert exc.status_code == 503
    assert exc.detail == "revocation_check_unavailable"
    assert exc.headers == {"Retry-After": str(max(1, mod.REVOCATION_RETRY_AFTER_SECONDS))}


def test_retry_after_is_never_below_one_second(monkeypatch):
    monkeypatch.setattr(mod, "REVOCATION_RETRY_AFTER_SECONDS", 0)
    assert mod.revocation_unavailable_error().headers["Retry-After"] == "1"


def test_it_does_not_set_a_bearer_challenge():
    """A WWW-Authenticate challenge would invite a client to re-authenticate."""
    assert "WWW-Authenticate" not in mod.revocation_unavailable_error().headers


def test_an_out_of_range_interval_is_clamped_to_the_registry_bounds(monkeypatch):
    """A Retry-After of a day would park every client; the registry's range corrects it."""
    low, high = mod._RETRY_AFTER_RANGE
    monkeypatch.setenv("AUTOBOT_REVOCATION_RETRY_AFTER_SECONDS", "86400")
    assert mod._read_retry_after_seconds() == high
    monkeypatch.setenv("AUTOBOT_REVOCATION_RETRY_AFTER_SECONDS", "0")
    assert mod._read_retry_after_seconds() == low


def test_an_in_range_interval_is_kept(monkeypatch):
    monkeypatch.setenv("AUTOBOT_REVOCATION_RETRY_AFTER_SECONDS", "7")
    assert mod._read_retry_after_seconds() == 7


def test_the_bounds_match_the_registry_spec():
    from autobot_shared.env_registry import REGISTRY

    spec = REGISTRY["AUTOBOT_REVOCATION_RETRY_AFTER_SECONDS"]
    assert (mod._RETRY_AFTER_DEFAULT, mod._RETRY_AFTER_RANGE) == (spec.default, spec.range)
