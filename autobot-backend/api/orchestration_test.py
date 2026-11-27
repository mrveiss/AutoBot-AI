# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The planning context carries the authenticated caller's identity, never the request body's (#16692)."""

from api.orchestration import _with_identity


def test_the_verified_identity_replaces_the_bodys_own():
    ctx = _with_identity(
        {"tenant_id": "other-org", "user_id": "victim", "k": 1}, {"user_id": "alice", "org_id": "org-1"}
    )
    assert ctx == {"tenant_id": "org-1", "user_id": "alice", "k": 1}


def test_a_body_identity_is_dropped_when_nothing_is_verified():
    ctx = _with_identity({"tenant_id": "other-org", "user_id": "victim"}, {})
    assert "tenant_id" not in ctx and "user_id" not in ctx


def test_the_callers_context_is_not_mutated():
    body = {"tenant_id": "other-org"}
    _with_identity(body, {"user_id": "alice", "org_id": "org-1"})
    assert body == {"tenant_id": "other-org"}
