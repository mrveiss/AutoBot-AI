# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit middleware records the caller's canonical id as the actor, never the mutable username (#22338)."""

from types import SimpleNamespace

from middleware import audit_middleware
from testkit.canonical_gate import HUMAN_PRINCIPAL, NAME_ONLY_PRINCIPAL, SERVICE_PRINCIPAL


def _request_with(user):
    return SimpleNamespace(state=SimpleNamespace(user=user), headers={})


def test_the_actor_is_the_id_and_an_admitted_service_is_its_name():
    assert audit_middleware._extract_user(_request_with(HUMAN_PRINCIPAL)) == "u-123"
    middleware = object.__new__(audit_middleware.AuditMiddleware)
    assert middleware._get_user_from_request(_request_with(HUMAN_PRINCIPAL)) == "u-123"
    assert middleware._get_user_from_request(_request_with(SERVICE_PRINCIPAL)) == "service:ci-runner"


def test_an_identity_less_principal_has_no_actor():
    """A bare username or empty principal resolves to None; the audit logger records that as ``system``."""
    middleware = object.__new__(audit_middleware.AuditMiddleware)
    assert middleware._get_user_from_request(_request_with(NAME_ONLY_PRINCIPAL)) is None
    assert middleware._get_user_from_request(_request_with({})) is None
    assert audit_middleware._extract_user(_request_with(NAME_ONLY_PRINCIPAL)) is None
