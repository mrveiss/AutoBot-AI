# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Strip the legacy copy of the OAuth app credentials from stored user bundles (#13630).

Before #13630 every user's ``connector_oauth_token`` secret carried a copy of the
operator's OAuth ``client_id`` / ``client_secret``. Refresh now resolves them from
provider config, so the copy is a secret at rest in a second place.

Removing it rewrites stored credentials, which no agent may do on its own
(#17038): this module only provides the read-only **preview** and the **strip**
that ``oauth_bundle_strip_action`` runs after a human approves a proposal.
Nothing here is reachable from a route that executes it.

Safety properties of the strip, per bundle:
  * only ``client_id`` / ``client_secret`` are removed; every other field is kept;
  * a bundle whose provider has no operator config is SKIPPED -- stripping it would
    break its refresh (the fallback copy is all it has);
  * each bundle is rewritten under the SAME per-credential refresh lease a token
    refresh takes (#13627), read and verified under it, so a refresh can never land
    between the strip's read and write and be overwritten with stale tokens; a bundle
    whose lease cannot be taken is skipped and recorded, never stripped unlocked;
  * a SHA-256 of every field except the app credentials is compared before and
    after, and the original value is restored (under the lease) on any mismatch;
  * every bundle gets a recorded outcome, including ``error`` and ``interrupted``;
  * no secret value, and no provider name outside the known registry, is returned
    or logged -- results are ids and counts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field

from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import SecretType
from services.credential_write import mirror_credential_to_vault

logger = get_logger(__name__)

APP_CREDENTIAL_KEYS = ("client_id", "client_secret")
UNKNOWN_PROVIDER = "unknown"

# Outcomes of one bundle.
STRIPPED, CLEAN, SKIPPED_UNCONFIGURED, UNREADABLE, VERIFY_FAILED = (
    "stripped",
    "clean",
    "skipped_unconfigured",
    "unreadable",
    "verify_failed",
)
LEASE_UNAVAILABLE, ERROR, INTERRUPTED = "lease_unavailable", "error", "interrupted"
#: Outcomes that leave a bundle still holding the app credentials or in doubt.
NOT_CLEAN_OUTCOMES = (SKIPPED_UNCONFIGURED, VERIFY_FAILED, LEASE_UNAVAILABLE, ERROR, INTERRUPTED)


@dataclass
class StripReport:
    """Ids and counts only. ``by_outcome`` maps outcome -> {provider -> count}."""

    by_outcome: dict[str, dict[str, int]] = field(default_factory=dict)
    secret_ids: dict[str, list[str]] = field(default_factory=dict)

    def add(self, outcome: str, provider: str, secret_id: str) -> None:
        counts = self.by_outcome.setdefault(outcome, {})
        counts[provider] = counts.get(provider, 0) + 1
        self.secret_ids.setdefault(outcome, []).append(secret_id)

    def count(self, outcome: str) -> int:
        return sum(self.by_outcome.get(outcome, {}).values())

    def summary(self) -> dict[str, dict[str, int]]:
        return {outcome: dict(counts) for outcome, counts in self.by_outcome.items()}


def token_digest(creds: dict) -> str:
    """SHA-256 over EVERY field but the app credentials, so before/after compare without values.

    A new token-bearing field (id_token, a rotated extra) is covered by default
    rather than by someone remembering to add it to a list.
    """
    kept = {k: v for k, v in creds.items() if k not in APP_CREDENTIAL_KEYS}
    material = json.dumps(kept, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _provider_label(creds: dict) -> str:
    """The provider name only when it is a registered one; anything else is not echoed."""
    from knowledge.connectors import oauth_flow

    name = creds.get("provider")
    return name if name in oauth_flow.OAUTH_PROVIDERS else UNKNOWN_PROVIDER


def _provider_configured(creds: dict) -> bool:
    """Whether the operator's OAuth app for this bundle's provider resolves from config."""
    from knowledge.connectors import oauth_flow

    try:
        oauth_flow.resolve_client_credentials(oauth_flow.get_provider(creds.get("provider") or ""))
    except (KeyError, ValueError):
        return False
    return True


def _read_bundle(svc, secret_id: str, accessed_by: str) -> tuple[dict | None, dict | None]:
    """(secret row, parsed bundle); (None, None) when unreadable, expired or not JSON."""
    secret = svc.get_secret(secret_id=secret_id, include_value=True, accessed_by=accessed_by)
    if secret is None:
        return None, None
    try:
        creds = json.loads(secret["value"])
    except (TypeError, ValueError):
        return secret, None
    return secret, creds if isinstance(creds, dict) else None


def _list_bundle_ids(svc) -> list[str]:
    rows = svc.list_secrets(secret_type=SecretType.CONNECTOR_OAUTH_TOKEN.value)
    return [row["id"] for row in rows]


def _classify(svc, secret_id: str, accessed_by: str) -> tuple[str, str, dict | None, dict | None]:
    """(outcome-if-not-strippable | '', provider label, secret row, bundle)."""
    secret, creds = _read_bundle(svc, secret_id, accessed_by)
    if creds is None:
        return UNREADABLE, UNKNOWN_PROVIDER, secret, None
    label = _provider_label(creds)
    if not any(k in creds for k in APP_CREDENTIAL_KEYS):
        return CLEAN, label, secret, creds
    if not _provider_configured(creds):
        return SKIPPED_UNCONFIGURED, label, secret, creds
    return "", label, secret, creds


def preview_sync(svc, accessed_by: str) -> StripReport:
    """Dry run: what a strip WOULD do. ``stripped`` here means 'would be stripped'. Writes nothing."""
    report = StripReport()
    for secret_id in _list_bundle_ids(svc):
        outcome, label, _, _ = _classify(svc, secret_id, accessed_by)
        report.add(outcome or STRIPPED, label, secret_id)
    return report


def _stripped_value(creds: dict) -> str:
    return json.dumps({k: v for k, v in creds.items() if k not in APP_CREDENTIAL_KEYS}, ensure_ascii=False)


def _write_verified(svc, secret_id: str, original: str, creds: dict, actor: str) -> bool:
    """Write the stripped bundle, verify the digest, restore the original on mismatch or error.

    MUST run under the credential's refresh lease: ``original`` and ``creds`` were
    read under it, and the restore is only safe because nothing else can have
    written in between.
    """
    before = token_digest(creds)
    try:
        svc.update_secret(secret_id=secret_id, value=_stripped_value(creds), updated_by=actor)
        _, after = _read_bundle(svc, secret_id, actor)
        if after is not None and token_digest(after) == before and not any(k in after for k in APP_CREDENTIAL_KEYS):
            return True
    except Exception as exc:
        _restore(svc, secret_id, original, actor, cause=exc)
        raise
    _restore(svc, secret_id, original, actor)
    return False


def _restore(svc, secret_id: str, original: str, actor: str, cause: Exception | None = None) -> None:
    """Put the original value back. A failing restore is chained to *cause*, never masking it."""
    try:
        svc.update_secret(secret_id=secret_id, value=original, updated_by=actor)
    except Exception as restore_exc:
        raise restore_exc from cause


def strip_one_sync(svc, secret_id: str, actor: str, report: StripReport) -> str | None:
    """Strip one bundle (caller holds its lease); returns the new value to mirror, or None."""
    outcome, label, secret, creds = _classify(svc, secret_id, actor)
    if outcome:
        report.add(outcome, label, secret_id)
        return None
    if not _write_verified(svc, secret_id, secret["value"], creds, actor):
        # The bundle id goes to the report and audit trail, not the log (the log carries no identifiers).
        logger.error("OAuth bundle strip verification failed for one bundle; original restored")
        report.add(VERIFY_FAILED, label, secret_id)
        return None
    report.add(STRIPPED, label, secret_id)
    return _stripped_value(creds)


async def preview(svc, accessed_by: str) -> StripReport:
    return await asyncio.get_running_loop().run_in_executor(None, preview_sync, svc, accessed_by)


async def _strip_under_lease(svc, secret_id: str, actor: str, report: StripReport) -> str | None:
    """Take the shared refresh lease, strip AND mirror under it, release. No lease -> skip and record.

    The vault mirror is part of the critical section: a refresh that rotates and
    mirrors the tokens between the strip's write and its mirror would otherwise be
    overwritten in the vault by the strip's stale value.
    """
    from knowledge.connectors.credential_store import _release_quietly, _vault_write_enabled, refresh_lease

    lease = refresh_lease(secret_id)
    if not await lease.update_leadership():
        report.add(LEASE_UNAVAILABLE, UNKNOWN_PROVIDER, secret_id)
        return None
    try:
        new_value = await _run_shielded(strip_one_sync, svc, secret_id, actor, report)
        if new_value is not None and _vault_write_enabled():
            await _mirror(svc, secret_id, new_value)
        return new_value
    finally:
        await _release_quietly(lease)


async def _run_shielded(fn, *args):
    """Run *fn* in the executor; on cancellation WAIT for the thread before re-raising.

    The lease must not be released while the thread may still be writing.
    """
    future = asyncio.get_running_loop().run_in_executor(None, fn, *args)
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        await asyncio.wait({future})
        raise


async def _mirror(svc, secret_id: str, new_value: str) -> None:
    secret = await asyncio.get_running_loop().run_in_executor(None, svc.get_secret, secret_id)
    await mirror_credential_to_vault(secret_id, (secret or {}).get("created_by") or "", new_value)


async def strip_all(svc, actor: str, report: StripReport | None = None) -> StripReport:
    """Strip every legacy bundle whose provider is configured. Run ONLY after human approval.

    Records into *report* as it goes, so a caller that passes its own report still
    holds the partial trail when this raises. One bundle's failure is recorded and
    the loop continues; an interruption (cancellation) records the in-flight bundle
    as ``interrupted`` and re-raises.
    """
    report = report if report is not None else StripReport()
    for secret_id in await asyncio.get_running_loop().run_in_executor(None, _list_bundle_ids, svc):
        try:
            await _strip_under_lease(svc, secret_id, actor, report)
        except Exception:
            # The bundle id is in the report and audit trail; the log carries no identifiers.
            logger.exception("OAuth bundle strip failed for one bundle")
            report.add(ERROR, UNKNOWN_PROVIDER, secret_id)
        except BaseException:
            report.add(INTERRUPTED, UNKNOWN_PROVIDER, secret_id)
            raise
    return report
