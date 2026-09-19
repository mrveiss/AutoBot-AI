# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ConnectorCredentialStore against a REAL SecretsService (#16579).

``test_credential_store.py`` builds its service with ``_make_svc()``, a
``MagicMock`` whose stored dicts already carry ``created_by``. Every ownership
test therefore passed while the real row shape never carried that key at all:
``_build_get_secret_query`` did not select it and ``_row_to_secret_dict`` did
not map it, so ``_require_owner`` saw a missing owner and refused the
credential's actual owner on ``load()``, ``rotate()`` and ``revoke()``.

The mock was not wrong about the contract; it was the only thing being tested.
These cases use a real ``SecretsService`` on a throwaway SQLite file so the
column has to survive the round trip, and the last one keeps #13628's
fail-closed rule honest — a row with no recorded owner is still denied, which
is the half a naive fix would quietly delete.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from cryptography.fernet import Fernet

from autobot_shared.auth.connector_auth import ApiKeyAuth
from knowledge.connectors.credential_store import (
    VAULT_READ_ENV,
    VAULT_WRITE_ENV,
    ConnectorCredentialStore,
)
from services.secrets_service import SecretsService

OWNER = "user-owner"
STRANGER = "user-stranger"
CONFIG = {"key": "sk-secret-value", "header": "X-Api-Key"}


def _clear_recorded_owner(db_path: str, secret_id: str) -> None:
    """Blank ``created_by`` the way a direct DB write or an older row would."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE secrets SET created_by = NULL WHERE id = ?", (secret_id,))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "secrets.db")


@pytest.fixture
def svc(db_path, monkeypatch) -> SecretsService:
    """A real service on a throwaway database, with both vault flags off.

    Off is the default path and the one the defect lives on: with
    ``AUTOBOT_SECRETS_UNIFIED_READ`` set, ``load()`` tries the vault envelope
    store first and could mask the SQLite row shape entirely.
    """
    monkeypatch.setenv(VAULT_READ_ENV, "false")
    monkeypatch.setenv(VAULT_WRITE_ENV, "false")
    return SecretsService(db_path=db_path, encryption_key=Fernet.generate_key().decode())


@pytest.fixture
def store(svc) -> ConnectorCredentialStore:
    return ConnectorCredentialStore(svc)


async def _store_for_owner(store) -> tuple[str, dict]:
    """``(secret_id, sanitized_config)`` for a credential owned by OWNER.

    A plain helper rather than a fixture: an ``async def`` fixture under
    pytest-asyncio's strict mode hands the test a coroutine object instead of
    its value, and the resulting failure points at the assertion rather than at
    the fixture.
    """
    return await store.store("connector-1", OWNER, ApiKeyAuth, CONFIG)


class TestTheOwnerIsNotLockedOut:
    """The regression: the real owner was refused their own credential."""

    @pytest.mark.asyncio
    async def test_the_owner_loads_the_credential_they_stored(self, store) -> None:
        secret_id, sanitized = await _store_for_owner(store)
        assert await store.load(secret_id, sanitized, ApiKeyAuth, OWNER) == CONFIG

    @pytest.mark.asyncio
    async def test_the_owner_rotates_their_own_credential(self, store) -> None:
        secret_id, sanitized = await _store_for_owner(store)
        await store.rotate(secret_id, {"key": "sk-rotated"}, OWNER)
        merged = await store.load(secret_id, sanitized, ApiKeyAuth, OWNER)
        assert merged["key"] == "sk-rotated"

    @pytest.mark.asyncio
    async def test_rotate_validates_the_merged_bundle_like_store_does(self, svc) -> None:
        """#16428 review: create() validates via validate_config_against_schema;
        rotate() previously did not, so a credential that reached an incomplete
        state (a pre-#16428 row, or a bug elsewhere) could stay incomplete
        forever, discovered only when the connector next tries to authenticate.

        Seeds a row missing the auth_type's required token_url directly
        through the real service (bypassing store()'s own validation, the
        same way an old or corrupted row would exist) rather than asserting
        against update()'s field-presence semantics, which cannot itself
        drop a key that store() already validated as present.
        """
        store_ = ConnectorCredentialStore(svc)
        incomplete = {"client_id": "cid", "client_secret": "csecret", "refresh_token": "rtok"}
        created = svc.create_secret(
            name="connector:oauth:auth",
            secret_type="connector_oauth_token",  # pragma: allowlist secret
            value=json.dumps(incomplete),
            scope="user",
            metadata={"auth_type": "OAuthRefreshAuth"},
            created_by=OWNER,
        )

        with pytest.raises(ValueError, match="missing required auth field: token_url"):
            await store_.rotate(created["id"], {}, OWNER)

    @pytest.mark.asyncio
    async def test_the_owner_revokes_their_own_credential(self, store) -> None:
        secret_id, sanitized = await _store_for_owner(store)
        await store.revoke(secret_id, OWNER)
        with pytest.raises(LookupError):
            await store.load(secret_id, sanitized, ApiKeyAuth, OWNER)


class TestTheBoundaryStillHolds:
    """Returning the column must not weaken what #13628 put in place."""

    @pytest.mark.asyncio
    async def test_a_stranger_cannot_load(self, store) -> None:
        secret_id, sanitized = await _store_for_owner(store)
        with pytest.raises(PermissionError, match="owner_id mismatch"):
            await store.load(secret_id, sanitized, ApiKeyAuth, STRANGER)

    @pytest.mark.asyncio
    async def test_a_stranger_cannot_rotate(self, store) -> None:
        secret_id, _ = await _store_for_owner(store)
        with pytest.raises(PermissionError, match="owner_id mismatch"):
            await store.rotate(secret_id, {"key": "sk-hijacked"}, STRANGER)  # pragma: allowlist secret

    @pytest.mark.asyncio
    async def test_a_stranger_cannot_revoke(self, store) -> None:
        secret_id, sanitized = await _store_for_owner(store)
        with pytest.raises(PermissionError, match="owner_id mismatch"):
            await store.revoke(secret_id, STRANGER)
        assert await store.load(secret_id, sanitized, ApiKeyAuth, OWNER) == CONFIG

    @pytest.mark.asyncio
    async def test_a_row_with_no_recorded_owner_is_denied_even_to_its_creator(self, store, db_path) -> None:
        """#13628's fail-closed rule: unattributable means nobody, not everybody."""
        secret_id, sanitized = await _store_for_owner(store)
        _clear_recorded_owner(db_path, secret_id)
        with pytest.raises(PermissionError, match="no recorded owner"):
            await store.load(secret_id, sanitized, ApiKeyAuth, OWNER)


class TestTheRowShapeItself:
    """Pinning the column directly, so the cause is named when this breaks."""

    def test_get_secret_returns_created_by(self, svc) -> None:
        created = svc.create_secret(
            name="connector:direct:auth",
            # A stored-secret TYPE name, not a credential -- the scanner sees `api_key`
            # next to a quoted literal and cannot tell the two apart.
            secret_type="connector_api_key",  # pragma: allowlist secret
            value="{}",
            scope="user",
            created_by=OWNER,
        )
        assert svc.get_secret(secret_id=created["id"])["created_by"] == OWNER

    def test_the_other_mapped_columns_did_not_shift(self, svc) -> None:
        """created_by was appended, not inserted; positional reads must be intact."""
        created = svc.create_secret(
            name="connector:shape:auth",
            # A stored-secret TYPE name, not a credential -- the scanner sees `api_key`
            # next to a quoted literal and cannot tell the two apart.
            secret_type="connector_api_key",  # pragma: allowlist secret
            value="{}",
            scope="user",
            created_by=OWNER,
        )
        secret = svc.get_secret(secret_id=created["id"])
        assert secret["name"] == "connector:shape:auth"
        assert secret["secret_type"] == "connector_api_key"  # pragma: allowlist secret
        assert secret["scope"] == "user"
        assert secret["access_count"] == 0
