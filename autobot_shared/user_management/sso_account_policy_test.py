# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SSO account policy and the one login-eligibility rule it shares with password login (#18338)."""

from types import SimpleNamespace

import pytest

from autobot_shared.user_management import user_service_access
from autobot_shared.user_management.login_eligibility import login_refusal
from autobot_shared.user_management.sso_account_policy import (
    account_refusal,
    asserted_email_verified,
    email_link_refusal,
)


def _user(active=True, deleted=False, admin=False, org_id=None):
    return SimpleNamespace(
        is_active=active, deleted_at=object() if deleted else None, is_platform_admin=admin, org_id=org_id
    )


@pytest.mark.parametrize(
    ("user", "expected"),
    [(_user(), None), (_user(active=False), "account_inactive"), (_user(deleted=True), "account_deleted")],
)
def test_login_refusal(user, expected):
    assert login_refusal(user) == expected and account_refusal(user) == expected


def test_password_login_and_sso_apply_the_same_function():
    """One rule, not an SSO copy: password login imports the very function SSO uses."""
    assert user_service_access.login_refusal is login_refusal


@pytest.mark.parametrize(
    ("claims", "expected"),
    [({"email_verified": True}, True), ({"email_verified": "TRUE"}, True), ({"email_verified": "false"}, False),
     ({"email_verified": 1}, False), ({}, False)],
)  # fmt: skip
def test_asserted_email_verified(claims, expected):
    assert asserted_email_verified(claims) is expected


_POLICY = SimpleNamespace(config={"link_existing_by_verified_email": True}, org_id=None)
_ORG_A, _ORG_B = "org-a", "org-b"
_ORG_POLICY = SimpleNamespace(config={"link_existing_by_verified_email": True}, org_id=_ORG_A)


@pytest.mark.parametrize(
    ("provider", "identity", "user", "fragment"),
    [
        (_POLICY, {"email_verified": True}, _user(), None),
        (_POLICY, {"email_verified": True}, _user(admin=True), "platform admin"),
        (_POLICY, {"email_verified": False}, _user(), "verified"),
        (SimpleNamespace(config={}, org_id=None), {"email_verified": True}, _user(), "explicitly"),
        (SimpleNamespace(config=None, org_id=None), {"email_verified": True}, _user(), "explicitly"),
        (_ORG_POLICY, {"email_verified": True}, _user(org_id=_ORG_A), None),
        (_ORG_POLICY, {"email_verified": True}, _user(org_id=_ORG_B), "another organization"),
        (_ORG_POLICY, {"email_verified": True}, _user(org_id=None), "another organization"),
        (_POLICY, {"email_verified": True}, _user(active=False), "account_inactive"),
    ],
)
def test_email_link_refusal(provider, identity, user, fragment):
    reason = email_link_refusal(provider, identity, user)
    assert reason is None if fragment is None else fragment in reason
