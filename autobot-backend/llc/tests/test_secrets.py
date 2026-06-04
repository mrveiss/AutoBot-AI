# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for SecretService (GH#8217)."""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.secret import SecretNotFound, SecretService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MASTER_KEY = "test-master-key-32-bytes-padding!!"
_COMPANY_A = "company-aaa"
_COMPANY_B = "company-bbb"
_ACTOR = "agent-001"


def _make_secret_row(
    company_id: str = _COMPANY_A,
    name: str = "db_password",
    plaintext: str = "s3cr3t",
    version: int = 1,
    revoked: bool = False,
) -> MagicMock:
    """Build a mock LLCSecret row with an encrypted value."""
    from llc.services.secret import _derive_fernet_key

    SecretService()
    fernet = _derive_fernet_key(_MASTER_KEY.encode(), company_id)
    ciphertext = fernet.encrypt(plaintext.encode())

    row = MagicMock()
    row.id = uuid.uuid4()
    row.company_id = company_id
    row.name = name
    row.value = ciphertext
    row.version = version
    row.created_by_agent_id = _ACTOR
    row.revoked_at = MagicMock() if revoked else None
    row.is_revoked = revoked
    return row


def _make_session(row=None, rows=None) -> AsyncMock:
    """Build a minimal async session mock."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    result.scalar_one.return_value = row
    if rows is not None:
        result.scalars.return_value.all.return_value = rows
    session.execute.return_value = result
    return session


# ---------------------------------------------------------------------------
# set() — create path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_creates_new_secret() -> None:
    session = _make_session(row=None)  # no existing secret

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        await svc.set(session, _COMPANY_A, "api_key", "mysecretvalue", _ACTOR)

    session.add.assert_called_once()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_updates_existing_secret_version() -> None:
    existing = _make_secret_row(version=1, revoked=False)
    session = _make_session(row=existing)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        await svc.set(session, _COMPANY_A, "db_password", "newvalue", _ACTOR)

    assert existing.version == 2
    assert existing.revoked_at is None


@pytest.mark.asyncio
async def test_set_reactivates_revoked_secret() -> None:
    existing = _make_secret_row(version=3, revoked=True)
    existing.revoked_at = MagicMock()  # non-None = revoked
    session = _make_session(row=existing)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        await svc.set(session, _COMPANY_A, "db_password", "newvalue", _ACTOR)

    assert existing.version == 1  # reset to 0 + 1 = 1 for reactivated revoked
    assert existing.revoked_at is None


# ---------------------------------------------------------------------------
# get() — decrypt path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_decrypted_value() -> None:
    plaintext = "super-secret-db-password"
    row = _make_secret_row(plaintext=plaintext)
    session = _make_session(row=row)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        result = await svc.get(session, _COMPANY_A, "db_password")

    assert result == plaintext


@pytest.mark.asyncio
async def test_get_raises_not_found_for_missing_secret() -> None:
    session = _make_session(row=None)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        with pytest.raises(SecretNotFound) as exc_info:
            await svc.get(session, _COMPANY_A, "nonexistent")

    assert exc_info.value.company_id == _COMPANY_A
    assert exc_info.value.name == "nonexistent"


@pytest.mark.asyncio
async def test_get_cannot_decrypt_with_wrong_company_key() -> None:
    """A secret encrypted for company-A cannot be decrypted as company-B."""
    from cryptography.fernet import InvalidToken

    from llc.services.secret import _derive_fernet_key

    plaintext = "cross-company-secret"
    fernet_a = _derive_fernet_key(_MASTER_KEY.encode(), _COMPANY_A)
    ciphertext = fernet_a.encrypt(plaintext.encode())

    row = MagicMock()
    row.id = uuid.uuid4()
    row.company_id = _COMPANY_B
    row.name = "db_password"
    row.value = ciphertext
    row.version = 1
    row.revoked_at = None
    row.is_revoked = False

    session = _make_session(row=row)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        with pytest.raises(InvalidToken):
            await svc.get(session, _COMPANY_B, "db_password")


# ---------------------------------------------------------------------------
# revoke()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_sets_revoked_at() -> None:
    row = _make_secret_row(revoked=False)
    session = _make_session(row=row)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        await svc.revoke(session, _COMPANY_A, "db_password", _ACTOR)

    assert row.revoked_at is not None
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_raises_not_found_for_missing_secret() -> None:
    session = _make_session(row=None)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        with pytest.raises(SecretNotFound):
            await svc.revoke(session, _COMPANY_A, "nonexistent", _ACTOR)


# ---------------------------------------------------------------------------
# list()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_names_and_versions_only() -> None:
    rows = [
        _make_secret_row(name="api_key", version=2),
        _make_secret_row(name="db_password", version=1),
    ]
    session = _make_session(rows=rows)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        result = await svc.list(session, _COMPANY_A)

    assert len(result) == 2
    for entry in result:
        assert "value" not in entry
        assert "name" in entry
        assert "version" in entry


@pytest.mark.asyncio
async def test_list_excludes_values() -> None:
    rows = [_make_secret_row(name="token", version=1, plaintext="should-not-appear")]
    session = _make_session(rows=rows)

    with patch.dict(os.environ, {_ENV_KEY: _MASTER_KEY}):
        svc = SecretService()
        result = await svc.list(session, _COMPANY_A)

    assert all("value" not in entry for entry in result)


# ---------------------------------------------------------------------------
# Encryption isolation — company key separation
# ---------------------------------------------------------------------------


def test_different_companies_get_different_fernet_keys() -> None:
    from llc.services.secret import _derive_fernet_key

    master = _MASTER_KEY.encode()
    fernet_a = _derive_fernet_key(master, _COMPANY_A)
    fernet_b = _derive_fernet_key(master, _COMPANY_B)

    ciphertext = fernet_a.encrypt(b"secret")

    # Company B's fernet cannot decrypt company A's ciphertext
    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        fernet_b.decrypt(ciphertext)


# ---------------------------------------------------------------------------
# Missing master key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_raises_on_missing_master_key() -> None:
    session = _make_session(row=None)
    env = {k: v for k, v in os.environ.items() if k != _ENV_KEY}

    with patch.dict(os.environ, env, clear=True):
        svc = SecretService()
        with pytest.raises(RuntimeError, match="LLC_SECRET_MASTER_KEY"):
            await svc.set(session, _COMPANY_A, "key", "val", _ACTOR)


# ---------------------------------------------------------------------------
# Module-level constant (keep in sync with services/secret.py)
# ---------------------------------------------------------------------------

_ENV_KEY = "LLC_SECRET_MASTER_KEY"
