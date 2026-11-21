# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Postgres core tests for the connector-credential dual-write mirror (#10088 / Task 3c-2).

Drives the mirror/delete cores against a real Postgres unified store and verifies the
mirrored copy is envelope-readable (via the read core) after create, update, and delete.
"""

import base64
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.secret import SECRET_OWNER_VAULT_NAME_UNIQUE, Secret
from services.credential_read import read_imported_credential_in_session
from services.credential_write import delete_in_session, mirror_in_session
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_OWNER = uuid.uuid4()
_TYPE = "connector_oauth_token"
_OTHER_TYPE = "other_type"


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_mirror_creates_then_readable(session):
    await mirror_in_session(
        session,
        "sid-1",
        str(_OWNER),
        '{"token":"v1"}',
        _ROOT,
        name="connector:c:auth",
        secret_type=_TYPE,
    )
    await session.commit()
    out = await read_imported_credential_in_session(session, "sid-1", str(_OWNER), _ROOT)
    assert out == {"created_by": str(_OWNER), "value": '{"token":"v1"}'}


async def test_mirror_updates_existing_in_place(session):
    await mirror_in_session(
        session,
        "sid-1",
        str(_OWNER),
        '{"token":"v1"}',
        _ROOT,
        name="connector:c:auth",
        secret_type=_TYPE,
    )
    await session.commit()
    # second mirror without name/type → rotates the existing copy in place
    await mirror_in_session(session, "sid-1", str(_OWNER), '{"token":"v2"}', _ROOT)
    await session.commit()
    out = await read_imported_credential_in_session(session, "sid-1", str(_OWNER), _ROOT)
    assert out == {"created_by": str(_OWNER), "value": '{"token":"v2"}'}


async def test_update_only_skips_when_absent(session):
    # no existing copy + no name/type → no-op (nothing to rotate, cannot create)
    await mirror_in_session(session, "sid-x", str(_OWNER), '{"token":"v"}', _ROOT)
    await session.commit()
    assert await read_imported_credential_in_session(session, "sid-x", str(_OWNER), _ROOT) is None


async def test_delete_removes_unified_copy(session):
    await mirror_in_session(
        session,
        "sid-1",
        str(_OWNER),
        '{"token":"v1"}',
        _ROOT,
        name="connector:c:auth",
        secret_type=_TYPE,
    )
    await session.commit()
    await delete_in_session(session, "sid-1", str(_OWNER), _ROOT)
    await session.commit()
    assert await read_imported_credential_in_session(session, "sid-1", str(_OWNER), _ROOT) is None


_NAME = "connector:c:auth"


async def _seed(session, *, value=b"old", secret_type=_TYPE, active=True, extra=None, name=_NAME):
    """A same-name row made by the user (not the mirror), through the real envelope service."""
    from autobot_shared.secrets_vault import VaultKind, VaultRef
    from services.envelope_secrets_service import EnvelopeSecretsService

    row = await EnvelopeSecretsService(root_key=_ROOT).create(
        session, owner_vault=VaultRef(VaultKind.USER, str(_OWNER)), name=name, secret_type=secret_type,
        plaintext=value, created_by=_OWNER, extra_data=extra,
    )  # fmt: skip
    row.is_active = active
    await session.commit()
    return row.id


async def _mirror(session, sid="sid-1"):
    await mirror_in_session(
        session,
        sid,
        str(_OWNER),
        '{"token":"new"}',
        _ROOT,
        name=_NAME,
        secret_type=_TYPE,
    )


async def _value(session, secret_id) -> bytes:
    from autobot_shared.secrets_vault import VaultKind, VaultRef
    from services.envelope_secrets_service import EnvelopeSecretsService

    vault = VaultRef(VaultKind.USER, str(_OWNER))
    return await EnvelopeSecretsService(root_key=_ROOT).read(session, secret_id=secret_id, accessible_vaults=[vault])


async def test_unmarked_same_name_row_is_rotated_and_marked(session):
    sid = await _seed(session)
    await _mirror(session)
    await session.commit()
    assert await _value(session, sid) == b'{"token":"new"}'
    assert (await session.get(Secret, sid)).extra_data == {"imported_from_sqlite": "sid-1"}


async def test_duplicate_same_name_rows_raise_and_write_nothing(session):
    from services.envelope_secrets_service import AmbiguousSecretError

    first = await _seed(session, value=b"one")
    await session.execute(text(f'ALTER TABLE secrets DROP CONSTRAINT "{SECRET_OWNER_VAULT_NAME_UNIQUE}"'))
    second = await _seed(session, value=b"two")
    with pytest.raises(AmbiguousSecretError):
        await _mirror(session)
    await session.rollback()
    assert (await _value(session, first), await _value(session, second)) == (
        b"one",
        b"two",
    )
    rows = (await session.execute(select(Secret).where(Secret.name == _NAME))).scalars().all()
    assert all(not (r.extra_data or {}).get("imported_from_sqlite") for r in rows)


async def test_inactive_same_name_row_is_not_rotated(session):
    sid = await _seed(session, active=False)
    await _mirror(session)
    await session.commit()
    assert await _value(session, sid) == b"old"
    assert (await session.get(Secret, sid)).is_active is False


async def test_other_type_same_name_row_is_not_rotated(session):
    sid = await _seed(session, secret_type=_OTHER_TYPE)
    await _mirror(session)
    await session.commit()
    assert await _value(session, sid) == b"old"
    assert not (await session.get(Secret, sid)).extra_data


async def test_row_marked_for_another_credential_is_not_taken_over(session):
    sid = await _seed(session, extra={"imported_from_sqlite": "other-sid"})
    await _mirror(session)
    await session.commit()
    assert await _value(session, sid) == b"old"
    assert (await session.get(Secret, sid)).extra_data == {"imported_from_sqlite": "other-sid"}
