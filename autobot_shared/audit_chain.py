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
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
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
GENESIS_MISSING = "genesis_missing"

_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


def _scalar(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).strftime(_TIME_FORMAT)
    return value


def _json_key(key: Any) -> str:
    """A dict key as ``json.dumps`` writes it: JSONB keys are always strings, and they sort as strings."""
    if isinstance(key, str):
        return key
    if key is None or isinstance(key, bool):
        return json.dumps(key)
    return repr(key) if isinstance(key, float) else str(key)


def jsonb_form(value: Any) -> Any:
    """*value* as PostgreSQL JSONB hands it back, so the hash taken before the insert equals the one after the read.

    JSONB stores numbers as ``numeric``: a float written with a positive exponent (``1e+22``) comes back as a plain
    integer, while ``1.0`` keeps its scale and comes back as a float; ``-0.0`` comes back as ``0.0``; dict keys come
    back as strings. Everything else round-trips unchanged.
    """
    if isinstance(value, dict):
        return {_json_key(k): jsonb_form(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonb_form(v) for v in value]
    if isinstance(value, float) and value == 0:
        return 0.0  # numeric has no negative zero
    if isinstance(value, float) and "e+" in repr(value):
        return int(Decimal(repr(value)))
    return value


def covered_values(row: Any) -> dict[str, Any]:
    """The covered columns of *row* (an ORM row or any object with those attributes), normalised."""
    values = {name: _scalar(getattr(row, name, None)) for name in COVERED_FIELDS}
    values["details"] = jsonb_form(values["details"])
    return values


def is_digest(value: Any) -> bool:
    """True for a well-formed stored hash or MAC: 64 lowercase hex characters."""
    return isinstance(value, str) and _HEX_DIGEST.fullmatch(value) is not None


def same_digest(left: Any, right: Any) -> bool:
    """Constant-time equality of two stored values; safe for any string, including non-ASCII."""
    return hmac.compare_digest(str(left or "").encode("utf-8"), str(right or "").encode("utf-8"))


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
        found = self._ordering(row, seq)
        if all(is_digest(getattr(row, name)) for name in ("prev_hash", "row_hash", "row_mac")):
            found += self._content(row, seq)
        else:
            found.append(Finding(MODIFIED, seq, "a stored hash or mac is not 64 lowercase hex characters"))
        self._prev_seq = seq
        self._prev_hash = row.row_hash if is_digest(row.row_hash) else ""
        self.rows_checked += 1
        return found

    def _ordering(self, row: Any, seq: int) -> list[Finding]:
        found = []
        if seq != self._prev_seq + 1:
            found.append(Finding(GAP, self._prev_seq + 1, f"{seq - self._prev_seq - 1} sequence number(s) missing"))
        if not same_digest(row.prev_hash, self._prev_hash):
            found.append(Finding(REORDERED, seq, "prev_hash does not link to the previous row"))
        return found

    def _content(self, row: Any, seq: int) -> list[Finding]:
        try:
            canonical = canonical_bytes(covered_values(row))
        except (ValueError, TypeError, OverflowError):  # a stored value the encoder refuses (e.g. a non-finite number)
            return [Finding(MODIFIED, seq, "covered columns cannot be canonicalised")]
        digest = row_hash(row.prev_hash, canonical)
        found = []
        if not same_digest(digest, row.row_hash):
            found.append(Finding(MODIFIED, seq, "row_hash does not match the stored columns"))
        if not same_digest(row_mac(self._key, row.row_hash), row.row_mac):
            found.append(Finding(MAC_INVALID, seq, "row_mac does not verify under the key"))
        return found


def verify_rows(rows: Iterable[Any], key: bytes, *, genesis: str, start_seq: int = GENESIS_SEQ) -> list[Finding]:
    """All findings for *rows* (in ``chain_seq`` order) following *genesis* (or the row at *start_seq*)."""
    verifier = ChainVerifier(key, prev_seq=start_seq, prev_hash=genesis)
    return [finding for row in rows for finding in verifier.check(row)]
