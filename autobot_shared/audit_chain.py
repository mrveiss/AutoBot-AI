# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The tamper-evident hash chain over ``audit_logs`` rows (#17219): pure functions, no database.

One serialization and one hash function, shared by the writer
(``audit_chain_writer``) and the verifier (``services/audit/integrity``)::

    row_hash = SHA-256(prev_hash || canonical_bytes(row))        unkeyed, anyone can recompute
    row_mac  = HMAC-SHA-256(key, row_hash)                       keyed: not recomputable from the table

The chain detects a modified, removed or reordered row; the MAC stops a database-only
attacker from recomputing the chain after an edit. It cannot show truncation of the tail
(a head published elsewhere is needed, #22005) and it does not stop a change (#22004).

``user_id`` / ``org_id`` are NOT covered: they are foreign keys the database sets to NULL
when the user or organisation is deleted, which would fail verification after a legitimate
delete. ``actor`` and ``org_ref`` carry the same identities as text.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

#: First byte of every serialization: the format can change without invalidating older rows.
FORMAT_VERSION = 1
#: ``chain_seq`` of the genesis anchor; the first chained row is ``GENESIS_SEQ + 1``.
GENESIS_SEQ = 0
#: The columns the hash covers, in documentation order (the JSON itself is key-sorted).
COVERED_FIELDS = (
    "id",
    "chain_seq",
    "created_at",
    "category",
    "actor",
    "action",
    "resource_type",
    "resource_ref",
    "resource_id",
    "outcome",
    "details",
    "ip_address",
    "user_agent",
    "session_id",
    "org_ref",
)
_GENESIS_LABEL = b"autobot-audit-chain-genesis:v1"
_KEY_ID_LABEL = b"autobot-audit-chain-key-id:v1"
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f+00:00"

# Finding kinds, as ``Finding.kind``.
MODIFIED = "modified_row"
GAP = "removed_row"
REORDERED = "reordered_row"
MAC_INVALID = "mac_invalid"
UNCHAINED = "unchained_row"


def _scalar(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).strftime(_TIME_FORMAT)
    return value


def covered_values(row: Any) -> dict[str, Any]:
    """The covered columns of *row* (an ORM row or any object with those attributes), normalised."""
    return {name: _scalar(getattr(row, name, None)) for name in COVERED_FIELDS}


def canonical_bytes(values: Mapping[str, Any]) -> bytes:
    """One stable byte string for *values*: version byte, then key-sorted ASCII JSON."""
    body = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return bytes([FORMAT_VERSION]) + body.encode("ascii")


def row_hash(prev_hash: str, canonical: bytes) -> str:
    """Hex SHA-256 over the previous hash and this row's canonical bytes."""
    return hashlib.sha256(prev_hash.encode("ascii") + canonical).hexdigest()


def row_mac(key: bytes, digest: str) -> str:
    """Hex HMAC-SHA-256 of a row hash under *key*."""
    return hmac.new(key, digest.encode("ascii"), hashlib.sha256).hexdigest()


def key_id(key: bytes) -> str:
    """A short public name for *key*, for rotation; reveals nothing usable about it."""
    return hmac.new(key, _KEY_ID_LABEL, hashlib.sha256).hexdigest()[:16]


def genesis_hash(pre_chain_count: int, pre_chain_max_created_at: datetime | None) -> str:
    """The hash the first chained row links to; binds the count of rows that predate the chain."""
    latest = "" if pre_chain_max_created_at is None else _scalar(pre_chain_max_created_at)
    return hashlib.sha256(_GENESIS_LABEL + f":{pre_chain_count}:{latest}".encode("ascii")).hexdigest()


def seal_row(row: Any, prev_hash: str, key: bytes) -> tuple[str, str]:
    """``(row_hash, row_mac)`` of *row* (``chain_seq`` already set) chained after *prev_hash*."""
    digest = row_hash(prev_hash, canonical_bytes(covered_values(row)))
    return digest, row_mac(key, digest)


@dataclass(frozen=True)
class Finding:
    """One integrity finding, with the ``chain_seq`` where it was found."""

    kind: str
    seq: int
    detail: str = ""


class ChainVerifier:
    """Checks chained rows in ``chain_seq`` order; feed every row to :meth:`check`."""

    def __init__(self, key: bytes, *, prev_seq: int = GENESIS_SEQ, prev_hash: str) -> None:
        self._key = key
        self._prev_seq = prev_seq
        self._prev_hash = prev_hash
        self.rows_checked = 0

    def check(self, row: Any) -> list[Finding]:
        """Findings for *row*; the next row is judged against this row's STORED hash."""
        seq = int(row.chain_seq)
        found = self._ordering(row, seq) + self._content(row, seq)
        self._prev_seq, self._prev_hash = seq, row.row_hash
        self.rows_checked += 1
        return found

    def _ordering(self, row: Any, seq: int) -> list[Finding]:
        found = []
        if seq != self._prev_seq + 1:
            found.append(Finding(GAP, self._prev_seq + 1, f"{seq - self._prev_seq - 1} sequence number(s) missing"))
        if not hmac.compare_digest(str(row.prev_hash or ""), self._prev_hash):
            found.append(Finding(REORDERED, seq, "prev_hash does not link to the previous row"))
        return found

    def _content(self, row: Any, seq: int) -> list[Finding]:
        digest = row_hash(str(row.prev_hash or ""), canonical_bytes(covered_values(row)))
        stored = str(row.row_hash or "")
        found = []
        if not hmac.compare_digest(digest, stored):
            found.append(Finding(MODIFIED, seq, "row_hash does not match the stored columns"))
        if not hmac.compare_digest(row_mac(self._key, stored), str(row.row_mac or "")):
            found.append(Finding(MAC_INVALID, seq, "row_mac does not verify under the key"))
        return found


def verify_rows(rows: Iterable[Any], key: bytes, *, genesis: str, start_seq: int = GENESIS_SEQ) -> list[Finding]:
    """All findings for *rows* (in ``chain_seq`` order) following *genesis* (or the row at *start_seq*)."""
    verifier = ChainVerifier(key, prev_seq=start_seq, prev_hash=genesis)
    return [finding for row in rows for finding in verifier.check(row)]
