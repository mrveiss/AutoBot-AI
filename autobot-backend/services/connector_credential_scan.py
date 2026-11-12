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
from knowledge.connectors.credential_store import get_credential_store
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

OAUTH_AUTH_TYPE = "OAuthRefreshAuth"
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
        try:
            record = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            record = None
        if isinstance(record, dict) and record.get("connector_type"):
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
    """None when the secrets store still holds what is about to be stripped; otherwise why not."""
    klass = ConnectorRegistry.get_registered_class(record["connector_type"])
    sanitized = {k: v for k, v in (record.get("config") or {}).items() if k not in fields}
    try:
        merged = await get_credential_store().load(
            record["secret_id"], sanitized, klass.auth_schema(), record.get("owner_id") or "system"
        )
    except (LookupError, PermissionError) as exc:
        return f"secrets store cannot supply the credential ({type(exc).__name__})"
    if record.get("auth_type") != OAUTH_AUTH_TYPE and not all(merged.get(f) for f in fields):
        return "secrets store does not hold every field that would be removed"
    return None


def _rewrite(connector_id: str, fields: tuple[str, ...]) -> str | None:
    """Drop *fields* from the stored record if it is unchanged since it was read; blocking, run in a thread."""
    redis = get_redis_client(database=_DATABASE)
    key = "%s%s" % (_REDIS_KEY_PREFIX, connector_id)
    with redis.pipeline() as pipe:
        try:
            pipe.watch(key)
            record = json.loads(pipe.get(key))
            record["config"] = {k: v for k, v in record["config"].items() if k not in fields}
            pipe.multi()
            pipe.set(key, json.dumps(record, ensure_ascii=False))
            pipe.execute()
        except WatchError:
            return "the record changed while it was being rewritten; propose again"
    return None


async def strip_sensitive_fields(connector_id: str) -> tuple[bool, str | None]:
    """Remove the clear-text copies from one record; (done, reason). Only the approval handler calls this.

    Refused unless the record still holds them and the secrets store holds the same credential, so the
    rewrite can never be the only copy's loss.
    """
    found = [r for cid, r in await asyncio.to_thread(_read_records) if cid == connector_id]
    sensitive = sensitive_fields_for(found[0]["connector_type"]) if found else None
    if not found or sensitive is None:
        return False, "connector record not found or its type is not registered"
    fields = held_fields(found[0], sensitive)
    if not fields:
        return False, "the record no longer holds a sensitive value"
    if not found[0].get("secret_id"):
        return False, "no secrets-store copy exists; removing the value would lose the only copy"
    reason = await _secret_holds(found[0], fields) or await asyncio.to_thread(_rewrite, connector_id, fields)
    return reason is None, reason
