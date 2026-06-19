# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Postgres tests for the unified↔SQLite credential reconciliation sweep (#10088 / #10337).

Seeds marker'd unified rows in drifted states against a canonical SQLite store and verifies
the sweep deletes revoked/orphaned copies, re-seals drifted values, leaves consistent ones,
and — critically — aborts (deletes nothing) when the canonical store is missing.
"""

import base64
import sqlite3
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.unified_credential_read import read_imported_credential_in_session
from services.unified_credential_reconcile import reconcile_connector_credentials
from services.unified_secrets_service import UnifiedSecretsService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_FERNET = Fernet(Fernet.generate_key())
_OWNER = uuid.uuid4()


def _make_db(path: str, rows: list[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE secrets (id TEXT PRIMARY KEY, is_active INTEGER DEFAULT 1, encrypted_value TEXT)")
    for r in rows:
        enc = _FERNET.encrypt(r["value"].encode("utf-8")).decode("utf-8") if r.get("value") is not None else None
        conn.execute(
            "INSERT INTO secrets (id, is_active, encrypted_value) VALUES (?,?,?)", (r["id"], r.get("active", 1), enc)
        )
    conn.commit()
    conn.close()


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed_unified(session, marker: str, value: str):
    svc = UnifiedSecretsService(root_key=_ROOT)
    secret = await svc.create(
        session,
        owner_vault=VaultRef(VaultKind.USER, str(_OWNER)),
        name="connector:c:auth",
        secret_type="connector_oauth_token",
        plaintext=value.encode("utf-8"),
        created_by=_OWNER,
    )
    secret.extra_data = {"imported_from_sqlite": marker}
    await session.flush()
    return secret


async def _read(session, marker):
    return await read_imported_credential_in_session(session, marker, str(_OWNER), _ROOT)


async def test_reconcile_fixes_drift(session, tmp_path):
    db = str(tmp_path / "secrets.db")
    _make_db(
        db,
        [
            {"id": "rev", "active": 0, "value": "x"},  # revoked in SQLite
            {"id": "drift", "active": 1, "value": "new"},  # active, value differs from unified
            {"id": "ok", "active": 1, "value": "same"},  # already consistent
            # "orphan" deliberately absent from SQLite
        ],
    )
    await _seed_unified(session, "rev", "x")
    await _seed_unified(session, "drift", "old")
    await _seed_unified(session, "ok", "same")
    await _seed_unified(session, "orphan", "y")
    await session.commit()

    report = await reconcile_connector_credentials(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()

    assert report.aborted is False
    assert report.checked == 4 and report.deleted == 2 and report.resynced == 1 and report.ok == 1
    assert await _read(session, "rev") is None  # revoked → removed
    assert await _read(session, "orphan") is None  # absent in canonical → removed
    assert (await _read(session, "drift"))["value"] == "new"  # resynced to canonical
    assert (await _read(session, "ok"))["value"] == "same"  # untouched


async def test_reconcile_aborts_when_sqlite_missing(session, tmp_path):
    # No SQLite file → must abort and delete NOTHING (a missing canonical store is not "all revoked").
    await _seed_unified(session, "keep", "v")
    await session.commit()
    report = await reconcile_connector_credentials(
        session, sqlite_path=str(tmp_path / "nope.db"), fernet=_FERNET, root_key=_ROOT
    )
    await session.commit()
    assert report.aborted is True and report.deleted == 0
    assert (await _read(session, "keep"))["value"] == "v"
