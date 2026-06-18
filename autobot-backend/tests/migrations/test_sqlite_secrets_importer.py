# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the legacy SQLite → unified envelope importer (#10088 / Task 3c).

Builds a legacy SQLite ``secrets.db`` in a temp dir, imports it into a Postgres
unified store (migration-gate), and verifies each row is envelope-readable via
UnifiedSecretsService owned by the creator's user vault.
"""

import base64
import sqlite3
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.sqlite_secrets_importer import import_sqlite_secrets
from services.unified_secrets_service import UnifiedSecretsService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_KEY = Fernet.generate_key()
_FERNET = Fernet(_KEY)
_ALICE = uuid.uuid4()
_BOB = uuid.uuid4()


def _make_db(path: str, rows: list[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE secrets (id TEXT PRIMARY KEY, name TEXT, description TEXT, secret_type TEXT, "
        "encrypted_value TEXT NOT NULL, scope TEXT DEFAULT 'general', chat_id TEXT, created_by TEXT, "
        "is_active INTEGER DEFAULT 1)"
    )
    for r in rows:
        conn.execute(
            "INSERT INTO secrets (id, name, secret_type, encrypted_value, scope, created_by, is_active) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                r["id"],
                r["name"],
                r.get("secret_type", "password"),
                _FERNET.encrypt(r["value"]).decode("utf-8"),
                r.get("scope", "general"),
                r.get("created_by"),
                r.get("is_active", 1),
            ),
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


async def test_imports_and_envelope_readable(session, tmp_path):
    db = str(tmp_path / "secrets.db")
    _make_db(
        db,
        [
            {"id": "s1", "name": "alice-key", "value": b"a-val", "created_by": str(_ALICE)},
            {"id": "s2", "name": "bob-key", "value": b"b-val", "created_by": str(_BOB), "scope": "chat"},
        ],
    )
    report = await import_sqlite_secrets(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.total == 2 and report.imported == 2 and report.failed == []

    svc = UnifiedSecretsService(root_key=_ROOT)
    alice_secrets = await svc.list_for_vaults(session, accessible_vaults={VaultRef(VaultKind.USER, str(_ALICE))})
    assert len(alice_secrets) == 1
    assert (
        await svc.read(
            session, secret_id=alice_secrets[0].id, accessible_vaults={VaultRef(VaultKind.USER, str(_ALICE))}
        )
        == b"a-val"
    )
    # legacy scope is preserved for traceability
    assert alice_secrets[0].extra_data["legacy_scope"] == "general"
    assert alice_secrets[0].extra_data["imported_from_sqlite"] == "s1"


async def test_idempotent_skips_already_imported(session, tmp_path):
    db = str(tmp_path / "secrets.db")
    _make_db(db, [{"id": "s1", "name": "k", "value": b"v", "created_by": str(_ALICE)}])
    first = await import_sqlite_secrets(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    second = await import_sqlite_secrets(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert first.imported == 1
    assert second.total == 1 and second.imported == 0 and second.skipped_existing == 1


async def test_missing_and_invalid_owner_skipped(session, tmp_path):
    db = str(tmp_path / "secrets.db")
    _make_db(
        db,
        [
            {"id": "no-owner", "name": "k1", "value": b"v1", "created_by": None},
            {"id": "bad-owner", "name": "k2", "value": b"v2", "created_by": "not-a-uuid"},
            {"id": "ok", "name": "k3", "value": b"v3", "created_by": str(_ALICE)},
        ],
    )
    report = await import_sqlite_secrets(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.total == 3 and report.imported == 1 and len(report.failed) == 2


async def test_bad_ciphertext_reported(session, tmp_path):
    db = str(tmp_path / "secrets.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE secrets (id TEXT PRIMARY KEY, name TEXT, description TEXT, secret_type TEXT, "
        "encrypted_value TEXT NOT NULL, scope TEXT, chat_id TEXT, created_by TEXT, is_active INTEGER DEFAULT 1)"
    )
    conn.execute(
        "INSERT INTO secrets (id, name, secret_type, encrypted_value, created_by, is_active) VALUES (?,?,?,?,?,1)",
        ("bad", "k", "password", "not-a-fernet-token", str(_ALICE)),
    )
    conn.commit()
    conn.close()
    report = await import_sqlite_secrets(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    assert report.total == 1 and report.imported == 0 and len(report.failed) == 1


async def test_oversized_name_reported_not_batch_abort(session, tmp_path):
    # Dirty legacy data: a name longer than PG name column raises DataError on flush. It must be
    # reported as one failed row (per-row savepoint + broad SQLAlchemyError), not abort the batch.
    db = str(tmp_path / "secrets.db")
    _make_db(
        db,
        [
            {"id": "huge", "name": "x" * 5000, "value": b"v1", "created_by": str(_ALICE)},
            {"id": "ok", "name": "fine", "value": b"v2", "created_by": str(_ALICE)},
        ],
    )
    report = await import_sqlite_secrets(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.total == 2 and report.imported == 1 and len(report.failed) == 1


async def test_null_ciphertext_skipped(session, tmp_path):
    db = str(tmp_path / "secrets.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE secrets (id TEXT PRIMARY KEY, name TEXT, description TEXT, secret_type TEXT, "
        "encrypted_value TEXT, scope TEXT, chat_id TEXT, created_by TEXT, is_active INTEGER DEFAULT 1)"
    )
    conn.execute(
        "INSERT INTO secrets (id, name, secret_type, encrypted_value, created_by, is_active) VALUES (?,?,?,?,?,1)",
        ("nul", "k", "password", None, str(_ALICE)),
    )
    conn.commit()
    conn.close()
    report = await import_sqlite_secrets(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    assert report.total == 1 and report.imported == 0 and len(report.failed) == 1
