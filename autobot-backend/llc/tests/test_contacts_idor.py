# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Route-level access control for contacts.py routes (#13969).

Mirrors test_secrets_idor.py / test_goals_idor.py's shape:
  - no auth at all                  -> 401
  - authenticated, wrong company_id -> 404 (assert_company_access, #12238)
  - authenticated, own company_id   -> the expected success status
  - platform admin, any company_id  -> allowed

"Wrong company_id" here is a scoping check, not a tenant-isolation boundary —
companies inside one AutoBot installation are organisational units, not
separate customers (umbrella #13935 owner correction) — but the same
``assert_company_access`` guard every other LLC router uses still applies:
a company's contact list is that company's view, not another company's.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
_OTHER_COMPANY = "99999999-9999-9999-9999-999999999999"


def _make_contact_dict(company_id: str, contact_id: str) -> dict:
    return {
        "id": contact_id,
        "company_id": company_id,
        "full_name": "Ada Lovelace",
        "email": "ada@supplier.test",
        "phone": None,
        "role_title": None,
        "notes": None,
        "created_at": "2026-08-11T00:00:00+00:00",
        "updated_at": "2026-08-11T00:00:00+00:00",
    }


def _make_client(caller_company_id: str, is_platform_admin: bool = False) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.contacts import router as contacts_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(contacts_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_company_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    contact_id = str(uuid.uuid4())
    created = MagicMock(**_make_contact_dict(caller_company_id, contact_id))
    for key, value in _make_contact_dict(caller_company_id, contact_id).items():
        setattr(created, key, value)

    patch("llc.api.contacts.ContactService.list_by_company", new=AsyncMock(return_value=[])).start()
    patch("llc.api.contacts.ContactService.create", new=AsyncMock(return_value=created)).start()
    patch("llc.api.contacts.ContactService.get", new=AsyncMock(return_value=created)).start()
    patch("llc.api.contacts.ContactService.update", new=AsyncMock(return_value=created)).start()
    patch("llc.api.contacts.ContactService.delete", new=AsyncMock(return_value=True)).start()

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestContactsNoAuth:
    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.contacts import router as contacts_router
        from user_management.database import get_async_session

        app = FastAPI()
        app.include_router(contacts_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_async_session] = _fake_session
        return TestClient(app)

    def test_list_contacts_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get(f"/api/llc/contacts/{_OTHER_COMPANY}")
        assert resp.status_code == 401

    def test_create_contact_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post(f"/api/llc/contacts/{_OTHER_COMPANY}", json={"full_name": "Ada"})
        assert resp.status_code == 401


class TestContactsScopeGuard:
    def test_list_own_company_returns_200(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.get(f"/api/llc/contacts/{company_id}")
        assert resp.status_code == 200

    def test_list_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.get(f"/api/llc/contacts/{_OTHER_COMPANY}")
        assert resp.status_code == 404

    def test_list_platform_admin_other_company_allowed(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id, is_platform_admin=True)
        resp = client.get(f"/api/llc/contacts/{_OTHER_COMPANY}")
        assert resp.status_code == 200

    def test_create_own_company_returns_201(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.post(f"/api/llc/contacts/{company_id}", json={"full_name": "Ada Lovelace"})
        assert resp.status_code == 201

    def test_create_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.post(f"/api/llc/contacts/{_OTHER_COMPANY}", json={"full_name": "Ada Lovelace"})
        assert resp.status_code == 404

    def test_delete_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.delete(f"/api/llc/contacts/{_OTHER_COMPANY}/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_own_company_returns_204(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.delete(f"/api/llc/contacts/{company_id}/{uuid.uuid4()}")
        assert resp.status_code == 204

    def test_get_by_id_own_company_returns_200(self):
        """GET /{contact_id} — the write-path guard exists (list/create/delete
        were already covered); this closes the missing read-single-item case."""
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.get(f"/api/llc/contacts/{company_id}/{uuid.uuid4()}")
        assert resp.status_code == 200

    def test_get_by_id_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.get(f"/api/llc/contacts/{_OTHER_COMPANY}/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_patch_own_company_returns_200(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.patch(f"/api/llc/contacts/{company_id}/{uuid.uuid4()}", json={"phone": "+1-555-0100"})
        assert resp.status_code == 200

    def test_patch_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.patch(f"/api/llc/contacts/{_OTHER_COMPANY}/{uuid.uuid4()}", json={"phone": "+1-555-0100"})
        assert resp.status_code == 404


class TestContactsActorDerivation:
    """#13969 review M1: the audit-trail actor must come from the authenticated
    session, never from client-supplied input — and a client sending garbage
    in the (now-removed) actor fields must not be able to reach that path at
    all, let alone crash it."""

    def test_create_derives_actor_from_authenticated_user(self):
        from llc.api.contacts import ContactService  # noqa: PLC0415

        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.post(f"/api/llc/contacts/{company_id}", json={"full_name": "Ada Lovelace"})
        assert resp.status_code == 201
        _, kwargs = ContactService.create.call_args
        assert kwargs["actor"] == _FIXED_USER_ID

    def test_delete_derives_actor_from_authenticated_user(self):
        from llc.api.contacts import ContactService  # noqa: PLC0415

        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.delete(f"/api/llc/contacts/{company_id}/{uuid.uuid4()}")
        assert resp.status_code == 204
        _, kwargs = ContactService.delete.call_args
        assert kwargs["actor"] == _FIXED_USER_ID

    def test_client_supplied_actor_field_in_body_is_ignored_not_500(self):
        """Before the fix, an unparseable client-supplied ``actor`` reached
        ``uuid.UUID(actor_id)`` inside ``ActivityLogService.record`` unguarded
        — an unhandled 500. The field no longer exists on the schema at all,
        so pydantic silently drops it as an unknown extra key."""
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.post(
            f"/api/llc/contacts/{company_id}",
            json={"full_name": "Ada Lovelace", "actor": "not-a-uuid-at-all"},
        )
        assert resp.status_code == 201
