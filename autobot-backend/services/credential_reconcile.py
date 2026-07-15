# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reconcile mirrored envelope credential copies against canonical SQLite (#10088 / #10337).

Closes the revoke-resurrection + silent-desync gate of the connector-store cutover. The
dual-write mirror (#10334) is best-effort, so a swallowed envelope delete/rotate can leave the
envelope copy out of sync with the canonical SQLite store — and with read-first enabled a
revoked credential could be resurrected, or a stale token served. This sweep walks every
marker'd envelope row and reconciles it against SQLite:

- SQLite row absent **or inactive** (revoked) → delete the envelope copy.
- SQLite row active but the value drifted → re-seal the envelope copy to the SQLite value.

**Destructive-safety.** Deletes are irreversible (hard delete), so the sweep refuses to run
when the canonical store can't be positively confirmed authoritative *and populated*:
- SQLite file missing or its table absent → abort (``OperationalError``/``FileNotFoundError``).
- SQLite present but **empty**, or the sweep would delete **every** envelope copy → abort. A
  populated mirror against an empty canonical store is indistinguishable from a misconfigured
  or wiped DB (``get_secrets_service`` auto-creates an empty ``secrets.db`` at a bad path), so
  it must never be read as "everything revoked".
Each row is reconciled inside its own SAVEPOINT so one poison row can't abort the sweep.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # typing only — avoid a hard cryptography import at module load
    from cryptography.fernet import Fernet, MultiFernet

logger = logging.getLogger(__name__)

_MARKER = "imported_from_sqlite"


@dataclass
class ReconcileReport:
    """Counts for one reconciliation sweep (``aborted`` when SQLite was unsafe to trust)."""

    checked: int = 0
    deleted: int = 0  # revoked/absent in SQLite → removed from envelope
    resynced: int = 0  # value drifted → re-sealed to the SQLite value
    ok: int = 0  # already consistent
    undecryptable: int = 0  # active SQLite rows whose value couldn't decrypt → drift-blind
    failed: list[str] = field(default_factory=list)
    aborted: bool = False


def _read_sqlite_state(sqlite_path: str, fernet) -> tuple[dict[str, dict], int]:
    """Canonical ``{id: {"active": bool, "value": str|None}}`` + undecryptable-row count.

    Raises ``FileNotFoundError`` / ``sqlite3.OperationalError`` when the store or its table is
    absent — the caller treats that as "abort", never as "everything revoked".
    """
    from cryptography.fernet import InvalidToken

    if not Path(sqlite_path).exists():
        raise FileNotFoundError(sqlite_path)
    conn = sqlite3.connect(sqlite_path)
    undecryptable = 0
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT id, is_active, encrypted_value FROM secrets")
        state: dict[str, dict] = {}
        for r in cur.fetchall():
            value = None
            if r["is_active"] and r["encrypted_value"]:
                try:
                    value = fernet.decrypt(r["encrypted_value"].encode("utf-8")).decode("utf-8")
                except (InvalidToken, ValueError):
                    undecryptable += 1  # keep the envelope copy, skip value resync (drift-blind)
            state[str(r["id"])] = {"active": bool(r["is_active"]), "value": value}
        return state, undecryptable
    finally:
        conn.close()


def _is_revoked(sqlite_state: dict, row) -> bool:
    """True when *row*'s canonical SQLite counterpart is absent or inactive (revoked)."""
    src = sqlite_state.get(str(row.extra_data.get(_MARKER)))
    return src is None or not src["active"]


async def _reconcile_one(session, svc, row, src, report: ReconcileReport) -> None:
    from autobot_shared.secrets_vault import VaultKind, VaultRef

    # The marker is the SQLite row's global PRIMARY KEY, so (marker → one row → one owner) is
    # 1:1; the authorizing vault is the envelope row's own owner. If SQLite ever adopts per-user
    # id namespaces this coupling must be revisited.
    vaults = {VaultRef(VaultKind.USER, str(row.owner_id))}
    if src is None or not src["active"]:
        await svc.delete(session, secret_id=row.id)  # revoked or absent in canonical store
        report.deleted += 1
        return
    current = await svc.read(session, secret_id=row.id, accessible_vaults=vaults)
    if src["value"] is not None and current.decode("utf-8") != src["value"]:
        await svc.rotate_value(
            session, secret_id=row.id, new_plaintext=src["value"].encode("utf-8"), actor_vaults=vaults
        )
        report.resynced += 1
    else:
        report.ok += 1


async def reconcile_connector_credentials(
    session, *, sqlite_path: str, fernet: "Fernet | MultiFernet", root_key: bytes
) -> ReconcileReport:
    """Reconcile every marker'd envelope row against the canonical SQLite store. Caller commits."""
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError

    from autobot_shared.secrets_envelope import DecryptionError, UnsupportedFormatError
    from models.secret import Secret
    from services.envelope_secrets_service import EnvelopeSecretsService, SecretAccessError, SecretNotFoundError

    report = ReconcileReport()
    try:
        sqlite_state, report.undecryptable = _read_sqlite_state(sqlite_path, fernet)
    except (FileNotFoundError, sqlite3.OperationalError) as exc:
        logger.warning("Reconcile aborted — canonical SQLite store unreadable (%s): %s", sqlite_path, exc)
        report.aborted = True
        return report

    marker = Secret.extra_data[_MARKER].astext
    rows = (await session.execute(select(Secret).where(marker.isnot(None), Secret.is_active.is_(True)))).scalars().all()
    report.checked = len(rows)

    # Destructive-safety circuit breaker: refuse to mass-delete when canonical looks empty or a
    # total wipe — that is far more likely a misconfigured/wiped store than a real "revoke all".
    if rows and (not sqlite_state or all(_is_revoked(sqlite_state, r) for r in rows)):
        logger.error(
            "Reconcile aborted — would delete all %d envelope copies (canonical empty=%s)", len(rows), not sqlite_state
        )
        report.aborted = True
        return report

    svc = EnvelopeSecretsService(root_key=root_key)
    for row in rows:
        src = sqlite_state.get(str(row.extra_data.get(_MARKER)))
        try:
            async with session.begin_nested():  # one poison row can't abort the sweep
                await _reconcile_one(session, svc, row, src, report)
        except (
            SecretAccessError,
            SecretNotFoundError,
            DecryptionError,
            UnsupportedFormatError,
            KeyError,
            ValueError,
            SQLAlchemyError,
        ) as exc:
            report.failed.append(f"{row.id}: {exc}")
    return report
