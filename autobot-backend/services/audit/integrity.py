# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Verification of the ``audit_logs`` hash chain (#17219).

``verify_chain`` streams the chained rows in ``chain_seq`` order and reports, with the sequence
where each was found: a modified row, a removed row (a gap), a reordered row, a row whose MAC does
not verify, and a row inserted without a chain entry (the count of ``chain_seq IS NULL`` rows
differs from the genesis anchor's ``pre_chain_count``). It uses the same hash and serialization as
the writer (``autobot_shared/audit_chain.py``).

Limits, stated: a removed tail row is not detectable until the head is published elsewhere
(#22005), and the database does not yet refuse a change (#22004). A failed verification is a
report, never a lockout: nothing here blocks an operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from autobot_shared import audit_chain
from autobot_shared.audit_chain import Finding
from autobot_shared.audit_chain_writer import chain_key
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.models.audit import AuditLog
from autobot_shared.user_management.models.audit_chain_anchor import GENESIS_KIND, AuditChainAnchor
from user_management.database import db_session_context

logger = get_logger(__name__)

#: Rows read per batch while verifying.
VERIFY_BATCH_SIZE = env_int("AUTOBOT_AUDIT_VERIFY_BATCH_SIZE", 1000)


@dataclass
class IntegrityReport:
    """The result of one verification run."""

    ok: bool
    checked_at: datetime
    rows_checked: int = 0
    chain_started: bool = False
    head_seq: int = 0
    head_hash: str | None = None
    pre_chain_count: int = 0
    unchained_count: int = 0
    from_seq: int = 1
    findings: list[Finding] = field(default_factory=list)


_last_report: IntegrityReport | None = None


def last_report() -> IntegrityReport | None:
    """The result of the most recent run in this process, or None."""
    return _last_report


async def _genesis(session: Any) -> Any:
    stmt = select(AuditChainAnchor).where(AuditChainAnchor.kind == GENESIS_KIND)
    return (await session.execute(stmt)).scalars().first()


async def current_head(session: Any) -> tuple[int, str | None]:
    """``(chain_seq, row_hash)`` of the last chained row, ``(0, None)`` when there is none."""
    stmt = select(AuditLog.chain_seq, AuditLog.row_hash).where(AuditLog.chain_seq.is_not(None))
    row = (await session.execute(stmt.order_by(AuditLog.chain_seq.desc()).limit(1))).first()
    return (int(row.chain_seq), row.row_hash) if row else (0, None)


async def _start_hash(session: Any, genesis: Any, start_seq: int) -> str | None:
    """The hash the row after *start_seq* must link to; None when that row is gone."""
    if start_seq <= audit_chain.GENESIS_SEQ:
        return genesis.hash
    stmt = select(AuditLog.row_hash).where(AuditLog.chain_seq == start_seq)
    return (await session.execute(stmt)).scalars().first()


async def _batches(session: Any, after_seq: int):
    """Chained rows after *after_seq*, ``VERIFY_BATCH_SIZE`` at a time, in sequence order."""
    while True:
        stmt = select(AuditLog).where(AuditLog.chain_seq > after_seq).order_by(AuditLog.chain_seq)
        rows = (await session.execute(stmt.limit(VERIFY_BATCH_SIZE))).scalars().all()
        if not rows:
            return
        yield rows
        after_seq = int(rows[-1].chain_seq)
        session.expunge_all()


async def _unchained_finding(session: Any, genesis: Any, head_seq: int) -> tuple[int, Finding | None]:
    """``(live count, finding)``: the unchained-row count must equal what the genesis recorded."""
    count = int((await session.execute(select(func.count()).where(AuditLog.chain_seq.is_(None)))).scalar_one())
    if count == genesis.pre_chain_count:
        return count, None
    where = await _position_of(session, genesis, head_seq)
    detail = f"{count} row(s) without a chain entry; the genesis recorded {genesis.pre_chain_count}"
    return count, Finding(audit_chain.UNCHAINED, where, detail)


async def _position_of(session: Any, genesis: Any, head_seq: int) -> int:
    """Where, by time, the newest unchained row written since the genesis sits in the chain.

    Approximate: it is the last chained row not newer than that row. The head when nothing placed it
    (a removed pre-chain row leaves no row to place).
    """
    stmt = select(func.max(AuditLog.created_at)).where(
        AuditLog.chain_seq.is_(None), AuditLog.created_at >= genesis.created_at
    )
    latest = (await session.execute(stmt)).scalar()
    if latest is None:
        return head_seq
    stmt = select(func.max(AuditLog.chain_seq)).where(AuditLog.created_at <= latest)
    return int((await session.execute(stmt)).scalar() or head_seq)


def _genesis_findings(genesis: Any, key: bytes) -> list[Finding]:
    """The anchor is itself covered: its hash binds the pre-chain count, its MAC the hash."""
    expected = audit_chain.genesis_hash(int(genesis.pre_chain_count), genesis.pre_chain_max_created_at)
    found = []
    if expected != genesis.hash:
        found.append(
            Finding(audit_chain.MODIFIED, audit_chain.GENESIS_SEQ, "genesis hash does not match its recorded count")
        )
    if audit_chain.row_mac(key, genesis.hash) != genesis.mac:
        found.append(
            Finding(audit_chain.MAC_INVALID, audit_chain.GENESIS_SEQ, "genesis mac does not verify under the key")
        )
    return found


async def _verify(session: Any, genesis: Any, from_seq: int) -> IntegrityReport:
    key, _kid = chain_key()
    start_seq = max(from_seq - 1, audit_chain.GENESIS_SEQ)
    head_seq, head_hash = await current_head(session)
    report = IntegrityReport(ok=True, checked_at=datetime.now(timezone.utc), chain_started=True, from_seq=start_seq + 1)
    report.head_seq, report.head_hash, report.pre_chain_count = head_seq, head_hash, int(genesis.pre_chain_count)
    report.findings.extend(_genesis_findings(genesis, key))
    start_hash = await _start_hash(session, genesis, start_seq)
    if start_hash is None:
        report.findings.append(Finding(audit_chain.GAP, start_seq, "the row before the requested start is missing"))
        start_hash = ""
    verifier = audit_chain.ChainVerifier(key, prev_seq=start_seq, prev_hash=start_hash)
    async for rows in _batches(session, start_seq):
        report.findings.extend(f for row in rows for f in verifier.check(row))
    report.rows_checked = verifier.rows_checked
    report.unchained_count, unchained = await _unchained_finding(session, genesis, head_seq)
    report.findings.extend([unchained] if unchained else [])
    report.ok = not report.findings
    return report


async def verify_chain(from_seq: int | None = None) -> IntegrityReport:
    """Verify the chain from *from_seq* (default: the genesis) and remember the result.

    Raises ``ChainKeyUnavailable`` when the MAC key cannot be derived: without it a MAC cannot be checked.
    """
    global _last_report
    async with db_session_context() as session:
        genesis = await _genesis(session)
        if genesis is None:
            report = IntegrityReport(ok=True, checked_at=datetime.now(timezone.utc))
        else:
            report = await _verify(session, genesis, from_seq or 1)
    _last_report = report
    logger.info("Audit chain verified: ok=%s rows=%d findings=%d", report.ok, report.rows_checked, len(report.findings))
    return report


def report_summary(report: IntegrityReport) -> dict[str, Any]:
    """*report* as plain JSON-able data: the one shape the API and the CLI both emit."""
    return {
        "ok": report.ok,
        "checked_at": report.checked_at.isoformat(),
        "rows_checked": report.rows_checked,
        "chain_started": report.chain_started,
        "head_seq": report.head_seq,
        "head_hash": report.head_hash,
        "pre_chain_count": report.pre_chain_count,
        "unchained_count": report.unchained_count,
        "from_seq": report.from_seq,
        "findings": [{"kind": f.kind, "seq": f.seq, "detail": f.detail} for f in report.findings],
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m services.audit.integrity [--from-seq N]``; exit 0 when the chain verifies, 1 when not."""
    import argparse  # noqa: PLC0415
    import asyncio  # noqa: PLC0415
    import json  # noqa: PLC0415
    import sys  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Verify the audit_logs hash chain (#17219)")
    parser.add_argument("--from-seq", type=int, default=None, help="verify from this chain_seq (default: the genesis)")
    report = asyncio.run(verify_chain(parser.parse_args(argv).from_seq))
    sys.stdout.write(json.dumps(report_summary(report), indent=2) + "\n")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
