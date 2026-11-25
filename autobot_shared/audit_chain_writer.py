# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Seals every new ``audit_logs`` row into the hash chain (#17219).

A ``before_insert`` listener on ``AuditLog`` (see ``install_chain_listener``), so every writer that
inserts through the ORM is chained -- the canonical service and the identity writers that insert
inside the caller's transaction -- and a seventh writer cannot forget to. Per insert, on PostgreSQL:

1. take ``pg_advisory_xact_lock`` (bounded wait, ``lock_timeout``): the chain lock is the LAST lock a
   transaction takes, because it is taken at flush, and it is held to the caller's commit;
2. read the tail (the highest ``chain_seq``), or write the genesis anchor if the chain has no row yet;
3. set ``chain_seq`` = tail + 1 (gap-free: a rolled-back insert returns its number), ``prev_hash``,
   ``row_hash``, ``row_mac`` and ``key_id``.

Fail closed: without the MAC key (derived from the secrets root key, never stored) the insert raises
and nothing is written; ``require_chain_key`` makes a service refuse to start. Rows already stored
are never read for rewriting, only the tail is read.

Other dialects (the in-memory SQLite of the unit tests) have no advisory lock and no production
audit_logs: they get complete rows but no chain.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from typing import Any

from sqlalchemy import event, func, insert, select, text

from autobot_shared import audit_chain
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.secrets_envelope import derive_audit_chain_key
from autobot_shared.time_utils import now_utc
from autobot_shared.user_management.models.audit_chain_anchor import GENESIS_KIND, AuditChainAnchor

logger = get_logger(__name__)

#: How long an insert waits for the chain lock before the audit write fails
#: (a ``durable`` caller then refuses the action).
LOCK_TIMEOUT_MS = env_int("AUTOBOT_AUDIT_CHAIN_LOCK_TIMEOUT_MS", 5000)
#: A fixed namespace for the advisory lock; not configuration.
_LOCK_KEY = int.from_bytes(hashlib.sha256(b"autobot-audit-chain-lock").digest()[:8], "big", signed=True)
_TRANSACTION_TAIL = "audit_chain_tail"
_CHAINED_DIALECT = "postgresql"

_key_lock = threading.Lock()
_key_cache: dict[str, Any] = {}


class ChainKeyUnavailable(RuntimeError):
    """The audit-chain MAC key cannot be derived; an audit row must not be written without one."""


def chain_key() -> tuple[bytes, str]:
    """``(key, key_id)``, derived once per process from the secrets root key."""
    with _key_lock:
        if not _key_cache:
            try:
                key = derive_audit_chain_key()
            except RuntimeError as exc:
                raise ChainKeyUnavailable("audit chain key unavailable: the secrets root key is not usable") from exc
            _key_cache.update(key=key, key_id=audit_chain.key_id(key))
        return _key_cache["key"], _key_cache["key_id"]


def require_chain_key() -> None:
    """Startup check: raises :class:`ChainKeyUnavailable` so the service refuses to start without the key."""
    chain_key()
    logger.info("Audit chain key available")


def _complete(row: Any) -> None:
    """Fill what the database would default later, so the hashed value is the stored one."""
    row.id = row.id or uuid.uuid4()
    row.created_at = row.created_at or now_utc()
    row.category = row.category or "security"
    row.outcome = row.outcome or "success"
    row.details = {} if row.details is None else row.details
    row.org_ref = row.org_ref or (str(row.org_id) if row.org_id else None)


def _acquire_lock(connection: Any) -> None:
    """Take the chain lock, waiting at most ``LOCK_TIMEOUT_MS``; the caller's own timeout is restored."""
    previous = connection.execute(text("SELECT current_setting('lock_timeout')")).scalar_one()
    connection.execute(text("SELECT set_config('lock_timeout', :v, true)"), {"v": f"{LOCK_TIMEOUT_MS}ms"})
    connection.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    connection.execute(text("SELECT set_config('lock_timeout', :v, true)"), {"v": previous})


def _genesis(connection: Any, table: Any, key: bytes, kid: str) -> tuple[int, str]:
    """The genesis anchor as ``(seq, hash)``; written now if the chain has no anchor yet."""
    anchors = AuditChainAnchor.__table__
    found = connection.execute(select(anchors.c.seq, anchors.c.hash).where(anchors.c.kind == GENESIS_KIND)).first()
    if found:
        return int(found.seq), found.hash
    count, latest = connection.execute(
        select(func.count(), func.max(table.c.created_at)).where(table.c.chain_seq.is_(None))
    ).one()
    digest = audit_chain.genesis_hash(count, latest)
    connection.execute(
        insert(anchors).values(
            kind=GENESIS_KIND,
            seq=audit_chain.GENESIS_SEQ,
            hash=digest,
            mac=audit_chain.row_mac(key, digest),
            key_id=kid,
            pre_chain_count=count,
            pre_chain_max_created_at=latest,
        )
    )
    return audit_chain.GENESIS_SEQ, digest


def _tail(connection: Any, table: Any, key: bytes, kid: str) -> tuple[int, str]:
    """``(chain_seq, row_hash)`` of the chain's last row, or the genesis when it has none."""
    row = connection.execute(
        select(table.c.chain_seq, table.c.row_hash)
        .where(table.c.chain_seq.is_not(None))
        .order_by(table.c.chain_seq.desc())
        .limit(1)
    ).first()
    return (int(row.chain_seq), row.row_hash) if row else _genesis(connection, table, key, kid)


def _current_tail(connection: Any, table: Any, key: bytes, kid: str) -> tuple[int, str]:
    """The tail as this transaction sees it, including rows sealed earlier in this flush but not yet inserted."""
    scope = (connection.get_transaction(), connection.get_nested_transaction())
    cached = connection.info.get(_TRANSACTION_TAIL)
    if cached and cached[0][0] is scope[0] and cached[0][1] is scope[1]:
        return cached[1]
    _acquire_lock(connection)
    return _tail(connection, table, key, kid)


def _seal_row(mapper: Any, connection: Any, row: Any) -> None:
    """``before_insert``: complete the row and, on PostgreSQL, chain it."""
    _complete(row)
    if connection.dialect.name != _CHAINED_DIALECT:
        return
    key, kid = chain_key()
    table = mapper.local_table
    seq, prev_hash = _current_tail(connection, table, key, kid)
    row.chain_seq, row.prev_hash, row.key_id = seq + 1, prev_hash, kid
    row.row_hash, row.row_mac = audit_chain.seal_row(row, prev_hash, key)
    scope = (connection.get_transaction(), connection.get_nested_transaction())
    connection.info[_TRANSACTION_TAIL] = (scope, (row.chain_seq, row.row_hash))


def install_chain_listener(model: type) -> None:
    """Chain every ORM insert of *model*; called once where the model is defined."""
    event.listen(model, "before_insert", _seal_row)
