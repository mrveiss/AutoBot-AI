# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Identity audit actions reach the analyzers in their own vocabulary (#19035).

``mfa_failed`` and ``account_locked`` used to read as ``api_request`` and were ignored by the
authentication analyzers. Asserted against the real ``SecurityEvent`` predicates.
"""

from __future__ import annotations

import time

import pytest

from security.enterprise.threat_detection.ingest import audit_event_to_engine_event, engine_action
from security.enterprise.threat_detection.models import SecurityEvent


def _event(action: str, outcome: str) -> SecurityEvent:
    payload = {
        "id": "e1",
        "category": "security",
        "action": action,
        "actor_id": "alice",
        "occurred_at": time.time(),
        "outcome": outcome,
    }
    return SecurityEvent(raw_event=audit_event_to_engine_event(payload))


@pytest.mark.parametrize("stored", ["mfa_failed", "auth.mfa", "account_locked", "auth.lockout"])
def test_mfa_and_lockout_are_authentication_failures(stored: str) -> None:
    assert engine_action(stored) == "authentication"
    assert _event(stored, "denied").is_authentication_failure()


@pytest.mark.parametrize("stored", ["mfa_failed", "account_locked"])
def test_a_successful_outcome_is_not_a_failure(stored: str) -> None:
    assert not _event(stored, "success").is_authentication_failure()


@pytest.mark.parametrize("stored", ["team_created", "org_updated", "mfa_enabled", "sso_linked"])
def test_non_authentication_identity_actions_stay_api_request(stored: str) -> None:
    assert engine_action(stored) == "api_request"


def test_access_denied_is_not_an_authentication_failure() -> None:
    """An RBAC denial is an authorization verdict by an authenticated caller, not a credential guess."""
    assert engine_action("permission_denied") == engine_action("access.denied") == "api_request"
