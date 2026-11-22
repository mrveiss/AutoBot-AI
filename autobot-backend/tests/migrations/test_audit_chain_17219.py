# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit hash chain against a real PostgreSQL (#17219).

Revision 122 adds the chain columns without touching a row; the ``before_insert`` listener
(``autobot_shared/audit_chain_writer.py``) then seals every new ``audit_logs`` row under an advisory
lock, and ``services.audit.integrity.verify_chain`` finds every kind of tampering.
"""

import asyncio
import base64
import contextlib
import uuid

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_PRE = "20261122_121"
_ROOT_KEY = base64.urlsafe_b64encode(b"r" * 32).decode("ascii")
_SENTINEL = object()


@pytest.fixture
def chain_env(monkeypatch):
    """The root key the chain key derives from, and a fresh key cache."""
    from autobot_shared import audit_chain_writer
    from autobot_shared.secrets_envelope import ROOT_KEY_ENV

    monkeypatch.setenv(ROOT_KEY_ENV, _ROOT_KEY)
    monkeypatch.setattr(audit_chain_writer, "_key_cache", {})
    return audit_chain_writer


@pytest.fixture
async def migrated(fresh_db_url, chain_env):
    """``(sessionmaker, engine)`` on a database migrated to head; verification reads through it."""
    from services.audit import integrity

    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _context():
        async with sessions() as session:
            yield session

    patcher = pytest.MonkeyPatch()
    patcher.setattr(integrity, "db_session_context", _context)
    yield sessions, engine
    patcher.undo()
    await engine.dispose()


def _row(**over):
    from autobot_shared.user_management.audit_rows import audit_row

    kwargs = dict(action="auth.login", resource_type="user", actor="alice", details={"n": 1})
    return audit_row(**{**kwargs, **over})


async def _insert(sessions, count: int = 1, **over) -> None:
    async with sessions.begin() as session:
        session.add_all([_row(**over) for _ in range(count)])


async def _verify():
    from services.audit import integrity

    return await integrity.verify_chain()


async def _scalar(sessions, sql: str, **params):
    async with sessions() as session:
        return (await session.execute(text(sql), params)).scalar()


def _found(report) -> set[tuple[str, int]]:
    return {(f.kind, f.seq) for f in report.findings}


async def test_the_first_chained_insert_writes_the_genesis_and_numbers_from_one(migrated) -> None:
    sessions, _ = migrated
    await _insert(sessions, 3)
    report = await _verify()
    assert report.ok and report.chain_started and report.rows_checked == 3 and report.head_seq == 3
    assert await _scalar(sessions, "SELECT count(*) FROM audit_chain_anchors WHERE kind = 'genesis'") == 1
    assert await _scalar(sessions, "SELECT min(chain_seq) FROM audit_logs") == 1


async def test_concurrent_writers_through_both_paths_make_a_contiguous_chain(migrated) -> None:
    sessions, _ = migrated

    async def _own_transaction() -> None:  # the canonical service: one row, its own commit
        await _insert(sessions, 1)

    async def _in_callers_transaction() -> None:  # identity writers: rows inside a larger transaction
        async with sessions.begin() as session:
            await session.execute(text("SELECT 1"))
            session.add_all([_row(actor="bob"), _row(actor="bob")])
            await session.flush()
            session.add(_row(actor="bob"))

    await asyncio.gather(*[(_own_transaction if n % 2 else _in_callers_transaction)() for n in range(16)])
    report = await _verify()
    assert report.ok, report.findings
    assert report.rows_checked == 8 + 8 * 3
    assert await _scalar(sessions, "SELECT count(DISTINCT chain_seq) = max(chain_seq) FROM audit_logs") is True


async def test_a_rolled_back_transaction_leaves_no_gap(migrated) -> None:
    sessions, _ = migrated
    await _insert(sessions, 2)
    with pytest.raises(RuntimeError):
        async with sessions.begin() as session:
            session.add_all([_row(), _row()])
            await session.flush()
            raise RuntimeError("abort")
    await _insert(sessions, 1)
    report = await _verify()
    assert report.ok and report.head_seq == 3, report.findings


async def test_a_details_value_survives_the_jsonb_round_trip_with_the_same_hash(migrated) -> None:
    sessions, _ = migrated
    details = {"f": 1.0, "g": 0.1, "tiny": 1e-7, "big": 2**62, "u": "café ☃", "n": {"a": [1, 2.5, None, True]}}
    await _insert(sessions, 1, details=details)
    assert (await _verify()).ok


async def test_deleting_a_user_nulls_user_id_and_the_chain_still_verifies(migrated) -> None:
    sessions, _ = migrated
    user_id = uuid.uuid4()
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, username, is_active, is_verified, mfa_enabled, is_platform_admin) "
                "VALUES (:i, 'a@example.test', 'chainuser', true, true, false, false)"
            ),
            {"i": user_id},
        )
    await _insert(sessions, 2, user_id=user_id, actor=str(user_id))
    async with sessions.begin() as session:
        await session.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    assert await _scalar(sessions, "SELECT count(*) FROM audit_logs WHERE user_id IS NOT NULL") == 0
    assert (await _verify()).ok


async def test_the_upgrade_rewrites_no_row_and_genesis_counts_the_earlier_ones(fresh_db_url, chain_env) -> None:
    from services.audit import integrity

    assert run_alembic(["upgrade", _PRE], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        for _ in range(3):
            await session.execute(
                text(
                    "INSERT INTO audit_logs (id, action, resource_type, outcome, details) "
                    "VALUES (:i, 'old', 'x', 'success', '{}')"
                ),
                {"i": uuid.uuid4()},
            )
    before = await _rows_with_versions(sessions)
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    assert await _rows_with_versions(sessions) == before, "the migration rewrote a stored row"
    await _insert(sessions, 2)
    genesis = await _scalar(sessions, "SELECT pre_chain_count FROM audit_chain_anchors WHERE kind = 'genesis'")
    pre_chain = await _scalar(sessions, "SELECT count(*) FROM audit_logs WHERE chain_seq IS NULL")
    assert genesis == pre_chain == 3
    patcher = pytest.MonkeyPatch()
    patcher.setattr(integrity, "db_session_context", lambda: _session_cm(sessions))
    try:
        assert (await _verify()).ok
    finally:
        patcher.undo()
        await engine.dispose()


@contextlib.asynccontextmanager
async def _session_cm(sessions):
    async with sessions() as session:
        yield session


async def _rows_with_versions(sessions) -> list[tuple]:
    async with sessions() as session:
        result = await session.execute(text("SELECT id::text, xmin::text FROM audit_logs ORDER BY id"))
        return [tuple(r) for r in result]


async def _chained(sessions, count: int = 5) -> None:
    await _insert(sessions, count)
    assert (await _verify()).ok


async def _exec(sessions, sql: str, **params) -> None:
    async with sessions.begin() as session:
        await session.execute(text(sql), params)


async def test_a_mutated_middle_record_is_reported_at_its_sequence(migrated) -> None:
    sessions, _ = migrated
    await _chained(sessions)
    await _exec(sessions, "UPDATE audit_logs SET action = 'auth.logout' WHERE chain_seq = 3")
    assert _found(await _verify()) == {("modified_row", 3)}


async def test_a_removed_middle_record_is_reported_as_a_gap(migrated) -> None:
    sessions, _ = migrated
    await _chained(sessions)
    await _exec(sessions, "DELETE FROM audit_logs WHERE chain_seq = 3")
    assert ("removed_row", 3) in _found(await _verify())


async def test_two_swapped_records_are_reported(migrated) -> None:
    sessions, _ = migrated
    await _chained(sessions)
    # The unique index refuses a one-statement swap, so the attacker parks one row on a free number.
    for old, new in ((2, 99), (3, 2), (99, 3)):
        await _exec(sessions, "UPDATE audit_logs SET chain_seq = :new WHERE chain_seq = :old", new=new, old=old)
    assert not (await _verify()).ok


async def test_a_chain_recomputed_without_the_key_fails_the_mac(migrated) -> None:
    from autobot_shared import audit_chain
    from autobot_shared.user_management.models.audit import AuditLog

    sessions, _ = migrated
    await _chained(sessions)
    wrong = b"x" * 32
    async with sessions.begin() as session:
        rows = (await session.execute(AuditLog.__table__.select().order_by(AuditLog.chain_seq))).all()
        prev = (await session.execute(text("SELECT hash FROM audit_chain_anchors"))).scalar()
        for row in rows:
            digest, mac = audit_chain.seal_row(row, prev, wrong)
            await session.execute(
                update(AuditLog.__table__)
                .where(AuditLog.__table__.c.id == row.id)
                .values(row_hash=digest, row_mac=mac, prev_hash=prev)
            )
            prev = digest
    report = await _verify()
    assert {kind for kind, _ in _found(report)} == {"mac_invalid"}


async def test_a_row_inserted_without_a_chain_entry_is_reported(migrated) -> None:
    sessions, _ = migrated
    await _chained(sessions)
    await _exec(
        sessions,
        "INSERT INTO audit_logs (id, action, resource_type, outcome, details) "
        "VALUES (gen_random_uuid(), 'sneaky', 'x', 'success', '{}')",
    )
    report = await _verify()
    assert {f.kind for f in report.findings} == {"unchained_row"} and report.unchained_count == 1


async def test_the_chain_lock_wait_is_bounded(migrated, chain_env, monkeypatch) -> None:
    """A stuck holder turns into a failed audit write, not a hang: ``lock_timeout`` covers the advisory lock."""
    sessions, engine = migrated
    await _insert(sessions, 1)
    monkeypatch.setattr(chain_env, "LOCK_TIMEOUT_MS", 500)
    async with engine.connect() as holder:
        await holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": chain_env._LOCK_KEY})
        with pytest.raises(Exception) as raised:
            await asyncio.wait_for(_insert(sessions, 1), timeout=15)
        await holder.rollback()
    assert (
        "lock timeout" in str(raised.value).lower()
        or "LockNotAvailable" in type(raised.value.__cause__ or raised.value).__name__
    )
    await _insert(sessions, 1)
    assert (await _verify()).ok


async def test_without_the_key_nothing_is_written(migrated, monkeypatch) -> None:
    from autobot_shared import audit_chain_writer
    from autobot_shared.secrets_envelope import ROOT_KEY_ENV

    sessions, _ = migrated
    monkeypatch.delenv(ROOT_KEY_ENV)
    monkeypatch.setattr(audit_chain_writer, "_key_cache", {})
    with pytest.raises(audit_chain_writer.ChainKeyUnavailable):
        await _insert(sessions, 1)
    assert await _scalar(sessions, "SELECT count(*) FROM audit_logs") == 0


async def test_deleting_an_organisation_nulls_org_id_and_the_chain_still_verifies(migrated) -> None:
    from user_management.models.organization import Organization

    sessions, _ = migrated
    async with sessions.begin() as session:
        org = Organization(name="Chain Org", slug="chain-org")
        session.add(org)
        await session.flush()
        org_id = org.id
    await _insert(sessions, 2, org_id=org_id)
    assert await _scalar(sessions, "SELECT count(*) FROM audit_logs WHERE org_id IS NOT NULL") == 2
    await _exec(sessions, "DELETE FROM organizations WHERE id = :i", i=org_id)
    assert await _scalar(sessions, "SELECT count(*) FROM audit_logs WHERE org_id IS NOT NULL") == 0
    assert await _scalar(sessions, "SELECT count(*) FROM audit_logs WHERE org_ref = :r", r=str(org_id)) == 2
    assert (await _verify()).ok


# --- every in-transaction writer shape produces a chained row (#17219) -----------------------------


def _service(session):
    """The part of a service the shared ``_audit_log`` methods read: its session and caller context."""
    from types import SimpleNamespace

    return SimpleNamespace(session=session, context=SimpleNamespace(user_id=None, org_id=None))


async def _identity_writer(cls_path: str, sessions) -> None:
    import importlib

    module, name = cls_path.rsplit(".", 1)
    cls = getattr(importlib.import_module(module), name)
    async with sessions.begin() as session:
        extra = [None] if name == "OrganizationService" else []  # its signature also takes the org id
        await cls._audit_log(_service(session), "x.created", "thing", None, *extra, {"k": 1})


async def _rbac_denial(sessions, monkeypatch) -> None:
    from types import SimpleNamespace

    from autobot_shared.user_management.middleware import rbac_middleware as rbac

    @contextlib.asynccontextmanager
    async def _context():
        async with sessions.begin() as session:
            yield session

    monkeypatch.setattr(rbac, "_dependencies", SimpleNamespace(db_session_context=_context))
    await rbac._emit_permission_denied_audit(None, "perm.x", "/api/x", ip_address="203.0.113.7")


async def _slm_rollback(sessions, monkeypatch) -> None:
    import importlib.util
    import pathlib

    from tests.migrations.conftest import REPO_ROOT

    path = pathlib.Path(REPO_ROOT) / "autobot-slm-backend/services/rollback_audit.py"
    spec = importlib.util.spec_from_file_location("_slm_rollback_audit_17219", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    @contextlib.asynccontextmanager
    async def _slm_session():
        async with sessions.begin() as session:
            yield session

    import user_management.database as database

    monkeypatch.setattr(database, "get_slm_session", _slm_session, raising=False)
    await module.record_rollback(actor="admin", commit="abc123", outcome="success", phase="requested")


_IDENTITY_WRITERS = (
    "autobot_shared.user_management.organization_service.OrganizationService",
    "autobot_shared.user_management.team_service.TeamService",
    "autobot_shared.user_management.user_service_base.UserServiceBase",
)


@pytest.mark.parametrize("writer", [*_IDENTITY_WRITERS, "rbac_denial", "slm_rollback"])
async def test_every_in_transaction_writer_produces_a_chained_verifying_row(migrated, monkeypatch, writer) -> None:
    sessions, _ = migrated
    if writer == "rbac_denial":
        await _rbac_denial(sessions, monkeypatch)
    elif writer == "slm_rollback":
        await _slm_rollback(sessions, monkeypatch)
    else:
        await _identity_writer(writer, sessions)
    row = await _scalar(sessions, "SELECT count(*) FROM audit_logs WHERE chain_seq IS NOT NULL AND row_mac IS NOT NULL")
    assert row == 1, f"{writer} wrote an unchained row"
    assert (await _verify()).ok


async def test_a_row_sealed_in_a_rolled_back_savepoint_leaves_no_gap(migrated) -> None:
    sessions, _ = migrated
    async with sessions.begin() as session:
        session.add(_row(actor="first"))
        await session.flush()
        nested = await session.begin_nested()
        session.add(_row(actor="discarded"))
        await session.flush()
        await nested.rollback()
        session.add(_row(actor="second"))
    async with sessions() as session:
        seqs = (await session.execute(text("SELECT chain_seq FROM audit_logs ORDER BY chain_seq"))).scalars().all()
    assert seqs == [1, 2]
    assert (await _verify()).ok


async def test_float_details_with_an_exponent_keep_the_same_hash_after_jsonb(migrated) -> None:
    sessions, _ = migrated
    await _insert(sessions, 1, details={"big": 1e22, "huge": 1.5e300, "one": 1.0, "tiny": 1e-07, "n": [1e16, 2.5]})
    assert (await _verify()).ok


async def test_negative_zero_and_non_string_keys_keep_the_same_hash_after_jsonb(migrated) -> None:
    sessions, _ = migrated
    await _insert(sessions, 1, details={"z": -0.0, "k": {10: "a", 2: "b"}, 3: [-0.0, {7: 1.5}]})
    assert (await _verify()).ok


async def test_a_verification_reads_one_snapshot_even_when_a_row_commits_mid_run(migrated, monkeypatch) -> None:
    """Head and rows come from one REPEATABLE READ snapshot: a row committed after the head read is in neither."""
    from services.audit import integrity

    sessions, _ = migrated
    await _insert(sessions, 3)
    real = integrity._start_hash

    async def _commit_a_row_then_read(*args):
        await _insert(sessions, 1)  # committed by another session between the head read and the row scan
        return await real(*args)

    monkeypatch.setattr(integrity, "_start_hash", _commit_a_row_then_read)
    report = await _verify()
    assert report.ok and report.head_seq == 3 and report.rows_checked == 3, report
    monkeypatch.setattr(integrity, "_start_hash", real)
    assert (await _verify()).head_seq == 4


async def test_a_row_moved_below_one_is_reported_on_postgres(migrated) -> None:
    sessions, _ = migrated
    await _chained(sessions, 3)
    await _exec(sessions, "UPDATE audit_logs SET chain_seq = 0 WHERE chain_seq = 3")
    assert ("modified_row", 0) in _found(await _verify())
