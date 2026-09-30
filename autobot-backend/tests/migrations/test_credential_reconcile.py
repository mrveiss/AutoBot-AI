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
from services.credential_read import read_imported_credential_in_session
from services.credential_reconcile import reconcile_connector_credentials
from services.envelope_secrets_service import EnvelopeSecretsService
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


async def _seed_vault(session, marker: str, value: str):
    svc = EnvelopeSecretsService(root_key=_ROOT)
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
    await _seed_vault(session, "rev", "x")
    await _seed_vault(session, "drift", "old")
    await _seed_vault(session, "ok", "same")
    await _seed_vault(session, "orphan", "y")
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
    await _seed_vault(session, "keep", "v")
    await session.commit()
    report = await reconcile_connector_credentials(
        session, sqlite_path=str(tmp_path / "nope.db"), fernet=_FERNET, root_key=_ROOT
    )
    await session.commit()
    assert report.aborted is True and report.deleted == 0
    assert (await _read(session, "keep"))["value"] == "v"


async def test_reconcile_aborts_on_empty_canonical_table(session, tmp_path):
    # Present-but-EMPTY secrets table (e.g. an auto-created secrets.db at a misconfigured path):
    # a populated mirror against an empty canonical store must abort, never mass-delete.
    db = str(tmp_path / "secrets.db")
    _make_db(db, [])  # table exists, zero rows
    await _seed_vault(session, "keep", "v")
    await session.commit()
    report = await reconcile_connector_credentials(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.aborted is True and report.deleted == 0
    assert (await _read(session, "keep"))["value"] == "v"


async def test_reconcile_aborts_on_total_wipe(session, tmp_path):
    # Canonical has other secrets but every mirrored copy is revoked → "delete all" is suspicious → abort.
    db = str(tmp_path / "secrets.db")
    _make_db(db, [{"id": "rev1", "active": 0, "value": "a"}, {"id": "rev2", "active": 0, "value": "b"}])
    await _seed_vault(session, "rev1", "a")
    await _seed_vault(session, "rev2", "b")
    await session.commit()
    report = await reconcile_connector_credentials(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.aborted is True and report.deleted == 0
    assert (await _read(session, "rev1"))["value"] == "a"


async def test_reconcile_skips_a_collided_marker_and_never_deletes_it(session, tmp_path):
    # Two envelope rows claim the same canonical id. `extra_data` has no unique constraint on
    # the marker, so this is reachable, and a revocation cannot be attributed to one owner --
    # deleting "the" copy would remove one the revocation was never about (#17773).
    db = str(tmp_path / "secrets.db")
    _make_db(db, [{"id": "dup", "active": 0, "value": "a"}, {"id": "solo", "active": 1, "value": "s"}])
    await _seed_vault(session, "dup", "a")
    await _seed_vault(session, "dup", "a")
    # `solo` is seeded DRIFTED. Without it the sweep has no unique row left once the collision
    # filter runs, so the test proved the collided marker was skipped but not that the skip let
    # anything else through -- a filter that dropped every row would have passed it identically
    # (#17776 review).
    await _seed_vault(session, "solo", "old")
    await session.commit()
    report = await reconcile_connector_credentials(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.collided == 1, f"the collided marker was not detected: {report}"
    assert report.deleted == 0, "a collided marker must never be deleted -- ownership is ambiguous"
    assert report.aborted is False, "one ambiguous marker must not abort the whole sweep"
    assert any("dup" in f for f in report.failed), f"the skip was not reported: {report.failed}"
    assert (await _read(session, "dup"))["value"] == "a"
    # The skip is a skip, not a halt: the uncollided marker still reconciles in the same sweep.
    assert report.resynced == 1, f"the uncollided marker did not reconcile past the skip: {report}"
    assert (await _read(session, "solo"))["value"] == "s"


async def test_reconcile_still_aborts_on_an_empty_store_when_every_marker_collided(session, tmp_path):
    """The empty-store abort must not depend on surviving the collision filter (#17773).

    Regression for a real gap in the first version of that filter: it ran *before* the
    circuit breaker, so when every marker collided `rows` became empty, the breaker's
    `rows and ...` prefix short-circuited, and a sweep against a wiped canonical store
    reported `aborted=False`. Nothing was deleted, so the effect was harmless and the
    *report* was wrong -- "could not evaluate" rendered as "nothing to do".
    """
    db = str(tmp_path / "secrets.db")
    _make_db(db, [])  # table exists, zero rows -- the wiped/misconfigured store case
    await _seed_vault(session, "dup", "a")
    await _seed_vault(session, "dup", "a")
    await session.commit()
    report = await reconcile_connector_credentials(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.aborted is True, f"an empty canonical store must abort even with every marker collided: {report}"
    assert report.deleted == 0
    assert (await _read(session, "dup"))["value"] == "a"


async def test_a_collided_marker_that_is_not_revoked_does_not_suppress_the_wipe_abort(session, tmp_path):
    """Why the wipe arm belongs AFTER the collision filter, not before it.

    `all()` over a subset is more readily true than over the superset, so filtering can
    only make this abort fire more eagerly. The proving case is a collided row that is NOT
    revoked: counted in, it makes `all(...)` false and suppresses an abort that should
    happen; excluded, the abort is restored.
    """
    db = str(tmp_path / "secrets.db")
    _make_db(db, [{"id": "dup", "active": 1, "value": "live"}, {"id": "rev", "active": 0, "value": "r"}])
    await _seed_vault(session, "dup", "live")
    await _seed_vault(session, "dup", "live")
    await _seed_vault(session, "rev", "r")
    await session.commit()
    report = await reconcile_connector_credentials(session, sqlite_path=db, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.aborted is True, (
        "every reconcilable row was revoked once the collided non-revoked pair was excluded, "
        f"so the wipe abort must fire: {report}"
    )
    assert report.deleted == 0
    assert (await _read(session, "rev"))["value"] == "r"
