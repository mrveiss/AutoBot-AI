# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSO signs in only to an eligible account, and links by email only under policy (#18338).

#18322 made SSO token minting work for the first time, which turned
``_find_or_provision_user`` into a live token path. These tests drive the real method
(loaded by ``test_sso_service``'s bootstrap) and check each refusal. The contrast
re-runs every refused case with the policy functions bypassed: each one then returns
a user, which is what the code did before #18338.
"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sso_service import SSOAuthenticationError, SSOService, _sso_mod  # noqa: E402

_LINKED, _EMAIL = "linked", "email"


_ORG_A, _ORG_B = uuid.uuid4(), uuid.uuid4()


def _account(*, active: bool = True, deleted: bool = False, admin: bool = False, org=None) -> SimpleNamespace:
    deleted_at = object() if deleted else None
    return SimpleNamespace(
        id=uuid.uuid4(), is_active=active, deleted_at=deleted_at, is_platform_admin=admin, org_id=org
    )


def _provider(link_policy: bool = True, org=None) -> SimpleNamespace:
    config = {"link_existing_by_verified_email": True} if link_policy else {}
    return SimpleNamespace(id=uuid.uuid4(), org_id=org, allow_user_creation=True, config=config, group_mapping={})


def _service(user, path: str) -> SSOService:  # type: ignore[valid-type]
    session = MagicMock(flush=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=user)))
    service = SSOService(session=session)
    link = MagicMock(user_id=user.id) if path == _LINKED else None
    service._find_existing_sso_link = AsyncMock(return_value=link)  # type: ignore[method-assign]
    by_email = user if path == _EMAIL else None
    service._find_user_by_email = AsyncMock(return_value=by_email)  # type: ignore[method-assign]
    service._create_sso_link = AsyncMock()  # type: ignore[method-assign]
    service._create_sso_user = AsyncMock()  # type: ignore[method-assign]
    service._sync_idp_groups_to_roles = AsyncMock()  # type: ignore[method-assign]
    return service


def _identity(verified: bool = True) -> dict:
    return {"email": "someone@example.test", "username": "someone", "email_verified": verified}


#: (label, account, link path, provider, identity, refusal text)
_REFUSED = [
    ("inactive linked account", _account(active=False), _LINKED, _provider(), _identity(), "account_inactive"),
    ("deleted linked account", _account(deleted=True), _LINKED, _provider(), _identity(), "account_deleted"),
    ("unverified email match", _account(), _EMAIL, _provider(), _identity(verified=False), "verified"),
    ("platform-admin email match", _account(admin=True), _EMAIL, _provider(), _identity(), "platform admin"),
    ("email match without the policy", _account(), _EMAIL, _provider(link_policy=False), _identity(), "explicitly"),
    ("inactive email match", _account(active=False), _EMAIL, _provider(), _identity(), "account_inactive"),
    ("cross-org email match", _account(org=_ORG_B), _EMAIL, _provider(org=_ORG_A), _identity(), "another organization"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "user", "path", "provider", "identity", "reason"), _REFUSED, ids=[r[0] for r in _REFUSED]
)
async def test_each_ineligible_case_is_refused(label, user, path, provider, identity, reason):
    service = _service(user, path)
    with pytest.raises(SSOAuthenticationError, match=reason):
        await service._find_or_provision_user(provider, "ext-1", identity)
    service._create_sso_link.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "user", "path", "provider", "identity", "reason"), _REFUSED, ids=[r[0] for r in _REFUSED]
)
async def test_contrast_without_the_policy_every_refused_case_signs_in(label, user, path, provider, identity, reason):
    service = _service(user, path)
    with (
        patch.object(_sso_mod.account_policy, "account_refusal", lambda _user: None),
        patch.object(_sso_mod.account_policy, "email_link_refusal", lambda *_args: None),
    ):
        assert await service._find_or_provision_user(provider, "ext-1", identity) is user


@pytest.mark.asyncio
async def test_a_verified_match_under_the_policy_links_a_non_admin():
    user = _account()
    service = _service(user, _EMAIL)
    assert await service._find_or_provision_user(_provider(), "ext-1", _identity()) is user
    service._create_sso_link.assert_awaited_once()
    service._create_sso_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_same_org_verified_match_under_the_policy_links():
    user = _account(org=_ORG_A)
    service = _service(user, _EMAIL)
    assert await service._find_or_provision_user(_provider(org=_ORG_A), "ext-1", _identity()) is user
    service._create_sso_link.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_eligible_linked_account_signs_in():
    user = _account()
    assert await _service(user, _LINKED)._find_or_provision_user(_provider(), "ext-1", _identity()) is user
