# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``verify_chain`` reports every kind of tampering with the sequence where it was found (#17219).

Runs on in-memory SQLite: the chain columns are plain columns, so rows are sealed here with the
shared ``audit_chain.seal`` exactly as the PostgreSQL listener seals them, then mutated in place.
The lock and sequence allocation are covered by the PostgreSQL test in ``tests/migrations``.
"""

import asyncio
import contextlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import Column, MetaData, Table, Uuid, delete, insert, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.types import JSON

from autobot_shared import audit_chain as chain
from autobot_shared.user_management.models.audit import AuditLog
from autobot_shared.user_management.models.audit_chain_anchor import GENESIS_KIND, AuditChainAnchor
from services.audit import integrity

KEY = b"k" * 32
WHEN = datetime(2026, 11, 22, 9, 0, 0, tzinfo=timezone.utc)
_AUDIT = AuditLog.__table__
_ANCHORS = AuditChainAnchor.__table__


def _sqlite_metadata() -> MetaData:
    """The two real tables, with the JSONB column created as JSON (SQLite has no JSONB)."""
    metadata = MetaData()
    for referenced in ("organizations", "users"):  # the foreign-key targets, reduced to their key
        Table(referenced, metadata, Column("id", Uuid, primary_key=True))
    for table in (_AUDIT, _ANCHORS):
        copy = table.to_metadata(metadata)
        for column in copy.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    return metadata


def _values(seq: int, prev_hash: str) -> dict:
    row = AuditLog(
        id=uuid.UUID(int=(0xABCD << 96) | seq),  # a hex letter: an all-digit id would take SQLite's NUMERIC affinity
        chain_seq=seq,
        created_at=WHEN + timedelta(seconds=seq),
        category="security",
        actor="alice",
        action="auth.login",
        resource_type="user",
        outcome="success",
        details={"n": seq},
    )
    row.prev_hash = prev_hash
    row.row_hash, row.row_mac = chain.seal_row(row, prev_hash, KEY)
    return {c.name: getattr(row, c.name) for c in _AUDIT.columns if getattr(row, c.name) is not None} | {
        "key_id": "kid"
    }


async def _seed(sessions) -> None:
    """A genesis recording 2 pre-chain rows, those 2 rows, and a sealed chain of 5."""
    genesis = chain.genesis_hash(2, WHEN)
    async with sessions.begin() as session:
        await session.execute(
            insert(_ANCHORS).values(
                kind=GENESIS_KIND,
                seq=0,
                hash=genesis,
                mac=chain.row_mac(KEY, genesis),
                key_id="kid",
                pre_chain_count=2,
                pre_chain_max_created_at=WHEN,
            )
        )
        for _ in range(2):  # the two pre-chain rows the genesis counts
            await session.execute(insert(_AUDIT).values(id=uuid.uuid4(), action="old", resource_type="x", details={}))
        prev = genesis
        for seq in range(1, 6):
            values = _values(seq, prev)
            await session.execute(insert(_AUDIT).values(**values))
            prev = values["row_hash"]


@pytest_asyncio.fixture
async def chained(monkeypatch):
    """A seeded chain; yields ``(sessionmaker, hashes)`` (hashes unused, kept for the tests' unpacking)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine
    async with engine.begin() as conn:
        await conn.run_sync(_sqlite_metadata().create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
    await _seed(sessions)
    hashes: list = []

    @contextlib.asynccontextmanager
    async def _context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(integrity, "db_session_context", _context)
    monkeypatch.setattr(integrity, "chain_key", lambda: (KEY, "kid"))
    monkeypatch.setattr(integrity, "_last_report", None)
    yield sessions, hashes
    await engine.dispose()


async def _mutate(sessions, statement) -> None:
    async with sessions.begin() as session:
        await session.execute(statement)


def _found(report) -> set[tuple[str, int]]:
    return {(f.kind, f.seq) for f in report.findings}


@pytest.mark.asyncio
async def test_an_untouched_chain_verifies(chained) -> None:
    report = await integrity.verify_chain()
    assert report.ok and report.rows_checked == 5 and report.head_seq == 5
    assert (report.pre_chain_count, report.unchained_count, report.chain_started) == (2, 2, True)


@pytest.mark.asyncio
async def test_a_mutated_middle_record_is_reported_at_its_sequence(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, update(_AUDIT).where(_AUDIT.c.chain_seq == 3).values(action="auth.logout"))
    report = await integrity.verify_chain()
    assert not report.ok and _found(report) == {(chain.MODIFIED, 3)}


@pytest.mark.asyncio
async def test_a_removed_middle_record_is_reported_as_a_gap(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, delete(_AUDIT).where(_AUDIT.c.chain_seq == 3))
    assert (chain.GAP, 3) in _found(await integrity.verify_chain())


@pytest.mark.asyncio
async def test_two_swapped_records_are_reported(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, update(_AUDIT).where(_AUDIT.c.chain_seq == 2).values(chain_seq=-2))
    await _mutate(sessions, update(_AUDIT).where(_AUDIT.c.chain_seq == 3).values(chain_seq=2))
    await _mutate(sessions, update(_AUDIT).where(_AUDIT.c.chain_seq == -2).values(chain_seq=3))
    assert integrity.verify_chain and not (await integrity.verify_chain()).ok


@pytest.mark.asyncio
async def test_a_recomputed_chain_without_the_key_fails_the_mac(chained) -> None:
    sessions, _ = chained
    forged = b"x" * 32
    async with sessions.begin() as session:
        prev = chain.genesis_hash(2, WHEN)
        for seq in range(1, 6):
            row = AuditLog(**{k: v for k, v in _values(seq, prev).items() if k not in ("row_hash", "row_mac")})
            row_hash, mac = chain.seal_row(row, prev, forged)
            await session.execute(
                update(_AUDIT).where(_AUDIT.c.chain_seq == seq).values(row_hash=row_hash, row_mac=mac)
            )
            prev = row_hash
    report = await integrity.verify_chain()
    assert {kind for kind, _ in _found(report)} == {chain.MAC_INVALID}


@pytest.mark.asyncio
async def test_a_row_inserted_without_a_chain_entry_is_reported(chained) -> None:
    sessions, _ = chained
    await _mutate(
        sessions,
        insert(_AUDIT).values(id=uuid.uuid4(), action="sneaky", resource_type="x", details={}),
    )
    report = await integrity.verify_chain()
    kinds = {f.kind: f for f in report.findings}
    assert set(kinds) == {chain.UNCHAINED} and kinds[chain.UNCHAINED].seq == 5 and report.unchained_count == 3


@pytest.mark.asyncio
async def test_a_removed_pre_chain_row_is_reported(chained) -> None:
    sessions, _ = chained
    async with sessions.begin() as session:
        await session.execute(delete(_AUDIT).where(_AUDIT.c.chain_seq.is_(None), _AUDIT.c.action == "old"))
    assert chain.UNCHAINED in {f.kind for f in (await integrity.verify_chain()).findings}


@pytest.mark.asyncio
async def test_pre_chain_rows_are_never_faults(chained) -> None:
    assert (await integrity.verify_chain()).findings == []


@pytest.mark.asyncio
async def test_verifying_from_a_sequence_checks_only_the_rows_after_it(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, update(_AUDIT).where(_AUDIT.c.chain_seq == 2).values(action="x"))
    assert (await integrity.verify_chain(from_seq=4)).ok
    assert not (await integrity.verify_chain(from_seq=2)).ok


@pytest.mark.asyncio
async def test_a_modified_genesis_is_reported(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, update(_ANCHORS).values(pre_chain_count=0))
    assert (chain.MODIFIED, 0) in _found(await integrity.verify_chain())


@pytest.mark.asyncio
async def test_before_the_first_chained_insert_there_is_nothing_to_verify(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, delete(_ANCHORS))
    await _mutate(sessions, delete(_AUDIT).where(_AUDIT.c.chain_seq.is_not(None)))  # no chained row either
    report = await integrity.verify_chain()
    assert report.ok and not report.chain_started and report.rows_checked == 0


@pytest.mark.asyncio
async def test_the_summary_shape_and_the_remembered_result(chained) -> None:
    assert integrity.last_report() is None
    report = await integrity.verify_chain()
    summary = integrity.report_summary(report)
    assert set(summary) == {
        "ok",
        "checked_at",
        "rows_checked",
        "chain_started",
        "head_seq",
        "head_hash",
        "pre_chain_count",
        "unchained_count",
        "from_seq",
        "findings",
    }
    assert integrity.last_report() is report and summary["findings"] == []


@pytest.mark.asyncio
async def test_batches_smaller_than_the_chain_still_verify_it_whole(chained, monkeypatch) -> None:
    monkeypatch.setattr(integrity, "VERIFY_BATCH_SIZE", 2)
    report = await integrity.verify_chain()
    assert report.ok and report.rows_checked == 5


# --- the CLI (#17219): the same function, an exit code and the report -----------------------------


def _file_db(tmp_path, monkeypatch) -> str:
    """A seeded SQLite file; ``integrity`` opens a fresh engine per call so ``asyncio.run`` owns its loop."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}"

    async def _build() -> None:
        engine = create_async_engine(url)  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.run_sync(_sqlite_metadata().create_all)
        await _seed(async_sessionmaker(engine, expire_on_commit=False))  # canonical: ignore py-adhoc-db-engine
        await engine.dispose()

    asyncio.run(_build())

    @contextlib.asynccontextmanager
    async def _context():
        engine = create_async_engine(url)  # canonical: ignore py-adhoc-db-engine
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
            async with factory() as session:
                yield session
        finally:
            await engine.dispose()

    monkeypatch.setattr(integrity, "db_session_context", _context)
    monkeypatch.setattr(integrity, "chain_key", lambda: (KEY, "kid"))
    return url


def test_the_cli_exits_zero_and_prints_the_report_for_a_clean_chain(tmp_path, monkeypatch, capsys) -> None:
    _file_db(tmp_path, monkeypatch)
    assert integrity.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True and report["rows_checked"] == 5 and report["findings"] == []


def test_the_cli_exits_non_zero_and_names_the_tampered_row(tmp_path, monkeypatch, capsys) -> None:
    url = _file_db(tmp_path, monkeypatch)

    async def _tamper() -> None:
        engine = create_async_engine(url)  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.execute(update(_AUDIT).where(_AUDIT.c.chain_seq == 3).values(action="auth.logout"))
        await engine.dispose()

    asyncio.run(_tamper())
    assert integrity.main(["--from-seq", "1"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["findings"] == [{"kind": "modified_row", "seq": 3, "detail": report["findings"][0]["detail"]}]


@pytest.mark.asyncio
async def test_a_missing_genesis_with_chained_rows_is_a_finding(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, delete(_ANCHORS))
    report = await integrity.verify_chain()
    assert not report.ok and _found(report) == {(chain.GENESIS_MISSING, 0)} and report.head_seq == 5


@pytest.mark.asyncio
async def test_a_non_ascii_stored_hash_is_reported_not_raised(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, update(_AUDIT).where(_AUDIT.c.chain_seq == 4).values(row_hash="é" * 64))
    report = await integrity.verify_chain()
    assert not report.ok and (chain.MODIFIED, 4) in _found(report)


@pytest.mark.asyncio
async def test_a_non_ascii_genesis_is_reported_not_raised(chained) -> None:
    sessions, _ = chained
    await _mutate(sessions, update(_ANCHORS).values(mac="é" * 64))
    assert (chain.MAC_INVALID, 0) in _found(await integrity.verify_chain())
