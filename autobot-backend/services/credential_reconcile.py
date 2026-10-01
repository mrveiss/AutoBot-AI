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
- SQLite present but **empty** → abort. A populated mirror against an empty canonical store is
  indistinguishable from a misconfigured or wiped DB (``get_secrets_service`` auto-creates an
  empty ``secrets.db`` at a bad path), so it must never be read as "everything revoked". Checked
  before the collision filter, which can otherwise empty the row set and skip this (#17773).
- The sweep would delete **every** reconcilable copy → abort. Checked after that filter, because
  ``all()`` over a subset is more readily true, so filtering only makes this fire more eagerly.
- Two envelope rows claiming the same canonical id → that marker is skipped, not deleted. The
  marker→owner coupling the delete relies on is unenforced in the schema (#17773), so it is
  verified per sweep rather than trusted.
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
    collided: int = 0  # markers claimed by >1 envelope row → skipped, never deleted (#17773)
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
    """Reconcile one envelope row against its canonical counterpart *src*.

    **This sweep is a cross-owner system principal and holds no user's authority.**
    It walks every marker'd row regardless of owner, by design, so there is no
    principal to scope against and the vault set below is NOT an authorization
    (#17773). It is the row's own ``owner_id``, handed to a parameter the service
    requires -- a value compared against itself, which cannot refuse anything.
    Calling it "the authorizing vault", as this comment previously did, described
    the argument's name rather than its effect.

    What actually constrains the destructive paths is stated in the module
    docstring and lives in the caller: the canonical store must be readable and
    non-empty, and a sweep that would delete every copy aborts. ``delete`` takes
    no vault at all (``EnvelopeSecretsService.delete``), so for that path the
    canonical verdict is the *only* authority -- which is why the circuit
    breaker, not a grant, is the safety property to preserve.

    Neither of the coordinator's two principals fits this caller: its user path
    needs a ``user_id`` and ``permissions``, and its service path is strictly the
    system vault, while these rows are USER-vault. A third principal -- a
    cross-owner system reconciler -- has no representation there, which is why
    this reaches the service directly. Recorded on #17773 rather than invented
    here.
    """
    from autobot_shared.secrets_vault import VaultKind, VaultRef

    # Not an authorization -- see the docstring. Named for what it is so the next
    # reader does not mistake a satisfied parameter for a passed check.
    row_owner_vault = {VaultRef(VaultKind.USER, str(row.owner_id))}
    if src is None or not src["active"]:
        await svc.delete(session, secret_id=row.id)  # revoked or absent in canonical store
        report.deleted += 1
        return
    current = await svc.read(session, secret_id=row.id, accessible_vaults=row_owner_vault)
    if src["value"] is not None and current.decode("utf-8") != src["value"]:
        await svc.rotate_value(
            session, secret_id=row.id, new_plaintext=src["value"].encode("utf-8"), actor_vaults=row_owner_vault
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

    # Arm 1 of the circuit breaker, hoisted ABOVE the collision filter (review, #17773).
    # It asks "is the canonical store empty", which does not depend on how many rows survive
    # that filter -- and the filter can empty `rows` completely when every marker is collided.
    # Left below, the `rows and ...` prefix short-circuited and this abort never ran, so a
    # sweep against a wiped canonical store reported `aborted=False` with nothing deleted:
    # harmless in effect and wrong in report, which is *could not evaluate* rendering as
    # *nothing to do*. Tested against the rows as FOUND, before filtering.
    if rows and not sqlite_state:
        logger.error(
            "Reconcile aborted — canonical store readable but EMPTY; %d envelope copy(ies) found. "
            "An empty canonical store is never 'everything revoked'.",
            len(rows),
        )
        report.aborted = True
        return report

    # The 1:1 coupling `_reconcile_one` depends on -- marker → one canonical row → one owner --
    # is checked here rather than assumed. `extra_data` is a JSON column with no unique
    # constraint or index on the marker, so two envelope rows CAN claim the same canonical id;
    # nothing in the import path prevents it and `credential_read.py` resolves such a pair with
    # `.first()`, silently picking one. For a sweep that DELETES, ambiguity is not the worst of
    # it: "revoked in canonical" would remove every row claiming that id, including an owner's
    # copy the revocation was never about. A collided marker cannot be attributed to one owner,
    # so it is reported and skipped -- never reconciled, never deleted (#17773).
    by_marker: dict[str, list] = {}
    for row in rows:
        by_marker.setdefault(str(row.extra_data.get(_MARKER)), []).append(row)
    for marker_value, claimants in sorted(by_marker.items()):
        if len(claimants) > 1:
            report.collided += 1
            report.failed.append(
                f"marker {marker_value}: {len(claimants)} envelope rows claim it; "
                "not reconciled -- a revocation cannot be attributed to one owner"
            )
    rows = [row for row in rows if len(by_marker[str(row.extra_data.get(_MARKER))]) == 1]

    # Arm 2: refuse a total wipe. This one DOES belong after the collision filter, and the
    # reason is that `all()` over a subset is more readily true than over the superset, so
    # filtering can only make this fire more eagerly, never less. The proving case is a
    # collided row that is NOT revoked: left in, it makes `all(...)` false and suppresses an
    # abort that should happen. `rows and` stays as the vacuity guard -- `all([])` is True.
    if rows and all(_is_revoked(sqlite_state, r) for r in rows):
        logger.error("Reconcile aborted — would delete all %d reconcilable envelope copies", len(rows))
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
