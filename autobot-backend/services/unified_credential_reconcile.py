# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reconcile mirrored unified credential copies against canonical SQLite (#10088 / #10337).

Closes the revoke-resurrection + silent-desync gate of the connector-store cutover. The
dual-write mirror (#10334) is best-effort, so a swallowed unified delete/rotate can leave the
unified copy out of sync with the canonical SQLite store — and with read-first enabled a
revoked credential could be resurrected, or a stale token served. This sweep walks every
marker'd unified row and reconciles it against SQLite:

- SQLite row absent **or inactive** (revoked) → delete the unified copy.
- SQLite row active but the value drifted → re-seal the unified copy to the SQLite value.

**Safety:** if the canonical SQLite store is missing or unreadable the sweep aborts without
deleting anything — a missing canonical store must never be read as "everything revoked".
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
    """Counts for one reconciliation sweep (``aborted`` when SQLite was unreadable)."""

    checked: int = 0
    deleted: int = 0  # revoked/absent in SQLite → removed from unified
    resynced: int = 0  # value drifted → re-sealed to the SQLite value
    ok: int = 0  # already consistent
    failed: list[str] = field(default_factory=list)
    aborted: bool = False


def _read_sqlite_state(sqlite_path: str, fernet) -> dict[str, dict]:
    """Canonical {id: {"active": bool, "value": str|None}} from the SQLite store.

    Raises ``FileNotFoundError`` / ``sqlite3.OperationalError`` when the store or its table is
    absent — the caller treats that as "abort", never as "everything revoked".
    """
    from cryptography.fernet import InvalidToken

    if not Path(sqlite_path).exists():
        raise FileNotFoundError(sqlite_path)
    conn = sqlite3.connect(sqlite_path)
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
                    value = None  # undecryptable → keep the unified copy, skip value resync
            state[str(r["id"])] = {"active": bool(r["is_active"]), "value": value}
        return state
    finally:
        conn.close()


async def _reconcile_one(session, svc, row, src, report: ReconcileReport) -> None:
    from autobot_shared.secrets_vault import VaultKind, VaultRef

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
    """Reconcile every marker'd unified row against the canonical SQLite store. Caller commits."""
    from sqlalchemy import select

    from autobot_shared.secrets_envelope import DecryptionError, UnsupportedFormatError
    from models.secret import Secret
    from services.unified_secrets_service import SecretAccessError, SecretNotFoundError, UnifiedSecretsService

    report = ReconcileReport()
    try:
        sqlite_state = _read_sqlite_state(sqlite_path, fernet)
    except (FileNotFoundError, sqlite3.OperationalError) as exc:
        logger.warning("Reconcile aborted — canonical SQLite store unreadable (%s): %s", sqlite_path, exc)
        report.aborted = True
        return report

    marker = Secret.extra_data[_MARKER].astext
    rows = (await session.execute(select(Secret).where(marker.isnot(None), Secret.is_active.is_(True)))).scalars().all()
    svc = UnifiedSecretsService(root_key=root_key)
    for row in rows:
        report.checked += 1
        src = sqlite_state.get(str(row.extra_data.get(_MARKER)))
        try:
            await _reconcile_one(session, svc, row, src, report)
        except (SecretAccessError, SecretNotFoundError, DecryptionError, UnsupportedFormatError, KeyError) as exc:
            report.failed.append(f"{row.id}: {exc}")
    return report
