# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Find connector records that hold a credential in clear text (#20701).

Before the sync stopped saving merged credentials, a finished sync could write the decrypted secret back
into the connector's Redis record. ``scan_connector_credentials`` is READ-ONLY and never returns or logs a
value: it reports counts, record ids and field NAMES. ``strip_sensitive_fields`` rewrites a record and is
reachable only from the post-approval handler in ``connector_credential_cleanup_action``.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from redis.exceptions import WatchError

from api._connector_keys import _REDIS_KEY_PREFIX, is_config_key
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.security.constant_time import secure_compare
from knowledge.connectors.credential_store import get_credential_store
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

_DATABASE = "knowledge"


@dataclass(frozen=True)
class CredentialFinding:
    """One record holding sensitive values. ``fields`` are field names only; ``secret_backed`` = a copy exists."""

    connector_id: str
    connector_type: str
    fields: tuple[str, ...]
    secret_backed: bool


@dataclass
class CredentialScanReport:
    """Counts first. ``unscannable_ids`` could not be checked (type not registered): not a clean result."""

    scanned: int = 0
    findings: list[CredentialFinding] = field(default_factory=list)
    unscannable_ids: list[str] = field(default_factory=list)

    @property
    def with_secret_copy(self) -> int:
        return sum(1 for f in self.findings if f.secret_backed)

    @property
    def without_secret_copy(self) -> int:
        return len(self.findings) - self.with_secret_copy


def sensitive_fields_for(connector_type: str) -> frozenset[str] | None:
    """The auth schema's sensitive field names; empty for no schema, ``None`` when the type is not registered."""
    klass = ConnectorRegistry.get_registered_class(connector_type)
    if klass is None:
        return None
    auth_cls = klass.auth_schema()
    return frozenset(getattr(auth_cls, "__sensitive_fields__", None) or ())


def held_fields(record: dict[str, Any], sensitive: frozenset[str]) -> tuple[str, ...]:
    """Names of the sensitive fields that hold a non-empty value in the record's ``config``."""
    config = record.get("config")
    if not isinstance(config, dict):
        return ()
    return tuple(sorted(name for name in sensitive if config.get(name) not in (None, "")))


def _read_records() -> list[tuple[str, dict[str, Any]]]:
    """Every parseable connector config record as (id, record); blocking, run in a thread."""
    redis = get_redis_client(database=_DATABASE)
    records = []
    for key in redis.scan_iter(match="%s*" % _REDIS_KEY_PREFIX):
        key_str = key.decode("utf-8") if isinstance(key, bytes) else key
        raw = redis.get(key_str) if is_config_key(key_str) else None
        record = _parse(raw)
        if record is not None:
            records.append((key_str[len(_REDIS_KEY_PREFIX) :], record))
    return records


async def scan_connector_credentials() -> CredentialScanReport:
    """Count stored connector records holding a value for a sensitive field of their auth schema (read-only)."""
    report = CredentialScanReport()
    for connector_id, record in await asyncio.to_thread(_read_records):
        report.scanned += 1
        sensitive = sensitive_fields_for(record["connector_type"])
        if sensitive is None:
            report.unscannable_ids.append(connector_id)
            continue
        fields = held_fields(record, sensitive)
        if fields:
            report.findings.append(
                CredentialFinding(connector_id, record["connector_type"], fields, bool(record.get("secret_id")))
            )
    return report


async def _secret_holds(record: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    """None when the secrets store holds, per field, a value EQUAL to the record's; otherwise why not.

    A field is stripped only if its stored copy matches, compared in constant time: a different or missing
    stored value means the record's value may be the only copy of what it holds, so it is kept (#17038).
    """
    klass = ConnectorRegistry.get_registered_class(record["connector_type"])
    config = record.get("config") or {}
    sanitized = {k: v for k, v in config.items() if k not in fields}
    try:
        merged = await get_credential_store().load(
            record["secret_id"], sanitized, klass.auth_schema(), record.get("owner_id") or "system"
        )
    except (LookupError, PermissionError) as exc:
        return f"secrets store cannot supply the credential ({type(exc).__name__})"
    unequal = [name for name in fields if not secure_compare(merged.get(name), config.get(name))]
    if unequal:
        names = ", ".join(unequal)
        return (
            f"secrets store does not hold an equal value for: {names} "
            "(stale copy \u2014 rotate or re-save the connector); nothing removed"
        )
    return None


def _read_raw(connector_id: str) -> Any:
    """The stored record exactly as Redis holds it (``None`` when absent); blocking, run in a thread."""
    return get_redis_client(database=_DATABASE).get("%s%s" % (_REDIS_KEY_PREFIX, connector_id))


def _parse(raw: Any) -> dict[str, Any] | None:
    try:
        record = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("connector_type") else None


def _rewrite(connector_id: str, fields: tuple[str, ...], validated_raw: Any) -> str | None:
    """Drop *fields* from the stored record, only if it is byte-for-byte the one that was validated.

    The compare runs inside the WATCH, so a write between the validation and the MULTI/EXEC is refused
    either way: by the equality check here, or by WatchError at EXEC. Blocking, run in a thread.
    """
    redis = get_redis_client(database=_DATABASE)
    key = "%s%s" % (_REDIS_KEY_PREFIX, connector_id)
    with redis.pipeline() as pipe:
        try:
            pipe.watch(key)
            raw = pipe.get(key)
            if raw is None:
                return "the connector record is gone"
            if raw != validated_raw:
                return "the record changed after it was checked; propose again"
            record = json.loads(raw)
            record["config"] = {k: v for k, v in record["config"].items() if k not in fields}
            pipe.multi()
            pipe.set(key, json.dumps(record, ensure_ascii=False))
            pipe.execute()
        except WatchError:
            return "the record changed while it was being rewritten; propose again"
    return None


async def strip_sensitive_fields(connector_id: str) -> tuple[bool, str | None]:
    """Remove the clear-text copies from one record; (done, reason). Only the approval handler calls this.

    Refused unless the record still holds them and the secrets store holds an EQUAL value for each field,
    so the rewrite can never be the only copy's loss. The record that is validated is the record that is
    rewritten: the WATCH transaction refuses it if it is not the same bytes.
    """
    raw = await asyncio.to_thread(_read_raw, connector_id)
    record = _parse(raw)
    sensitive = sensitive_fields_for(record["connector_type"]) if record else None
    if record is None or sensitive is None:
        return False, "connector record not found or its type is not registered"
    fields = held_fields(record, sensitive)
    if not fields:
        return False, "the record no longer holds a sensitive value"
    if not record.get("secret_id"):
        return False, "no secrets-store copy exists; removing the value would lose the only copy"
    reason = await _secret_holds(record, fields) or await asyncio.to_thread(_rewrite, connector_id, fields, raw)
    return reason is None, reason
