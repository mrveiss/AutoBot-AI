# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ConnectorCredentialStore — ADR-007 credential isolation shim.

Bridges ConnectorConfig ↔ SecretsService so that sensitive auth fields
(tokens, keys, passwords) are encrypted at rest and never written to Redis.
"""

import asyncio
import contextlib
import hashlib
import json
import os
import time
import uuid
from datetime import timedelta

from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.time_utils import now_utc, parse_utc_iso
from services.credential_read import load_imported_credential
from services.credential_write import delete_credential_from_vault, mirror_credential_to_vault

logger = get_logger(__name__)

# Feature flags (expand/contract cutover — #10088 Task 3c-2), both default off → behaviour
# is byte-identical to before. READ: reads try the vault envelope store first (matching the
# legacy id via the ``imported_from_sqlite`` marker) and fall back to SQLite. WRITE: every
# write also best-effort mirrors into the vault store (SQLite stays canonical). The two are
# independent so dual-write can be enabled first to populate the vault store, then read.
VAULT_READ_ENV = "AUTOBOT_SECRETS_UNIFIED_READ"
VAULT_WRITE_ENV = "AUTOBOT_SECRETS_UNIFIED_WRITE"


def _vault_read_enabled() -> bool:
    return os.environ.get(VAULT_READ_ENV, "false").strip().lower() in ("1", "true", "yes")


def _vault_write_enabled() -> bool:
    return os.environ.get(VAULT_WRITE_ENV, "false").strip().lower() in ("1", "true", "yes")


_AUTH_TYPE_TO_SECRET_TYPE: dict = {
    "OAuthRefreshAuth": "connector_oauth_token",
    "BearerAuth": "connector_api_key",
    "ApiKeyAuth": "connector_api_key",
    "BasicAuth": "connector_password",
}

# Refresh an OAuth access token this many seconds before its stated expiry, so
# in-flight requests never race a hard expiry. Not a cache TTL — a safety skew.
ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60

# #13627: per-credential refresh serialization.
#
# Both windows are derived from the token endpoint's own timeout, not picked
# independently. A lease TTL equal to that timeout expires *during* a slow
# refresh, a second caller wins SET NX, and both POST the same rotating token —
# which is this bug, unchanged. Likewise a wait shorter than the refresh makes
# every loser raise while the winner is still working correctly.
_REFRESH_LOCK_PREFIX = "connector:oauth:refresh:"


def _refresh_lock_key(secret_id: str) -> str:
    """Redis key for the per-credential refresh lease (#13627).

    Hashes the id rather than embedding it. Two reasons, both real: a credential
    identifier does not belong in a Redis keyspace that anyone with KEYS access
    can enumerate, and passing it into ``LeaderLease`` makes that module's own
    log lines taint-reachable from a credential. A stable digest serialises
    exactly as well.
    """
    return _REFRESH_LOCK_PREFIX + hashlib.sha256(secret_id.encode("utf-8")).hexdigest()[:32]


_REFRESH_DB = "knowledge"


def _token_timeout_s() -> float:
    """The token endpoint's HTTP timeout — the floor for every window below."""
    try:
        from knowledge.connectors.oauth_flow import _TOKEN_REQUEST_TIMEOUT

        return float(_TOKEN_REQUEST_TIMEOUT)
    except Exception:
        return 30.0


# Lease must outlive the slowest possible refresh, with headroom for the
# surrounding read/decrypt/write.
_REFRESH_LOCK_TTL_MS = int(os.getenv("AUTOBOT_OAUTH_REFRESH_LOCK_TTL_MS", str(int(_token_timeout_s() * 3 * 1000))))
# A loser must outwait the lease, or it gives up on a refresh still in progress.
_REFRESH_WAIT_S = max(float(os.getenv("AUTOBOT_OAUTH_REFRESH_WAIT_S", "0")), (_REFRESH_LOCK_TTL_MS / 1000.0) + 5.0)
# Guarded against 0 from the environment, which would busy-loop the executor.
_REFRESH_POLL_S = max(float(os.getenv("AUTOBOT_OAUTH_REFRESH_POLL_S", "0.2")), 0.05)


async def _release_quietly(lease: LeaderLease) -> None:
    """Release without letting cancellation or a Redis blip strand the lease (#13627).

    A bare ``await lease.release()`` in a ``finally`` re-raises ``CancelledError``
    if the request was cancelled mid-refresh, leaving the lease held for its full
    TTL and every other caller waiting it out.
    """
    with contextlib.suppress(Exception):
        await asyncio.shield(lease.release())


class ConnectorCredentialStore:
    """Bridges ConnectorConfig ↔ SecretsService for credential isolation (ADR-007).

    All methods are async-safe; the underlying SecretsService calls are
    synchronous and are dispatched via run_in_executor to avoid blocking the
    event loop.
    """

    def __init__(self, secrets_service) -> None:
        self._svc = secrets_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store(
        self,
        connector_id: str,
        owner_id: str,
        auth_cls: type,
        config: dict,
    ) -> tuple[str, dict]:
        """Extract sensitive fields from config, store them encrypted.

        Returns (secret_id, sanitized_config) where sanitized_config has
        sensitive fields removed.  Raises ValueError when auth_cls has no
        __sensitive_fields__.
        """
        sensitive = self._sensitive_fields(auth_cls)
        creds = {k: v for k, v in config.items() if k in sensitive}
        sanitized = {k: v for k, v in config.items() if k not in sensitive}

        name = f"connector:{connector_id}:auth"
        secret_type = _AUTH_TYPE_TO_SECRET_TYPE.get(auth_cls.__name__, "connector_api_key")

        value = json.dumps(creds, ensure_ascii=False)
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.create_secret(
                name=name,
                secret_type=secret_type,
                value=value,
                scope="user",
                created_by=owner_id,
            ),
        )
        if _vault_write_enabled():
            await mirror_credential_to_vault(result["id"], owner_id, value, name=name, secret_type=secret_type)
        return result["id"], sanitized

    async def load(
        self,
        secret_id: str,
        sanitized_config: dict,
        auth_cls: type,
        owner_id: str,
    ) -> dict:
        """Reconstruct full config by merging decrypted credentials back in.

        Raises PermissionError when owner_id does not match the stored secret.
        Raises LookupError when secret_id is not found or has expired.

        When the vault-read flag is on, the vault envelope store is tried first
        (by the legacy-id marker) and the SQLite store is the fallback.
        """
        secret = None
        if _vault_read_enabled():
            secret = await load_imported_credential(secret_id, owner_id)
        if secret is None:
            secret = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._svc.get_secret(
                    secret_id=secret_id,
                    include_value=True,
                    accessed_by=owner_id,
                ),
            )
        if secret is None:
            raise LookupError(f"Credential secret {secret_id!r} not found or expired")

        self._require_owner(secret, secret_id, owner_id)

        creds = json.loads(secret["value"])
        return {**sanitized_config, **creds}

    async def rotate(
        self,
        secret_id: str,
        new_credentials: dict,
        owner_id: str,
    ) -> None:
        """Replace the stored secret value with new_credentials in-place."""
        existing = await asyncio.get_running_loop().run_in_executor(
            None,
            # accessed_by drives the access audit (#13628): rotation decrypts the
            # full plaintext bundle and was the one read path leaving no attribution.
            lambda: self._svc.get_secret(secret_id=secret_id, include_value=True, accessed_by=owner_id),
        )
        if existing is None:
            raise LookupError(f"Credential secret {secret_id!r} not found or expired")
        self._require_owner(existing, secret_id, owner_id)

        current_creds = json.loads(existing["value"])
        current_creds.update(new_credentials)
        new_value = json.dumps(current_creds, ensure_ascii=False)

        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.update_secret(
                secret_id=secret_id,
                value=new_value,
                updated_by=owner_id,
            ),
        )
        if _vault_write_enabled():
            await mirror_credential_to_vault(secret_id, owner_id, new_value)

    async def revoke(self, secret_id: str, owner_id: str) -> None:
        """Delete the secret. Called on connector delete.

        #13628: guarded like the read paths. This was the one mutating site with
        no ownership check at all — any caller holding a ``secret_id`` could
        delete another owner's credential. A missing secret is left to
        ``delete_secret`` so revoking an already-gone credential stays idempotent.
        """
        existing = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.get_secret(secret_id=secret_id, include_value=False),
        )
        if existing is not None:
            self._require_owner(existing, secret_id, owner_id)
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.delete_secret(
                secret_id=secret_id,
                deleted_by=owner_id,
            ),
        )
        if _vault_write_enabled():
            await delete_credential_from_vault(secret_id, owner_id)

    # ------------------------------------------------------------------
    # OAuth 2.0 authorization-code tokens (ADR-007 §7 / GH#9019)
    # ------------------------------------------------------------------

    async def store_oauth(
        self,
        connector_id: str,
        owner_id: str,
        provider: str,
        token_response: dict,
        client_id: str,
        client_secret: str,
        token_url: str,
        scopes: list,
    ) -> str:
        """Persist a token set obtained via the OAuth auth-code flow.

        Stores a self-contained credential bundle (access + refresh token,
        client app creds, token endpoint) so :meth:`get_access_token` can
        refresh later without re-reading provider config.  Returns the secret id.
        """
        creds = self._oauth_bundle(token_response, client_id, client_secret, token_url, scopes, provider)
        name = f"connector:{connector_id}:auth"
        value = json.dumps(creds, ensure_ascii=False)
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.create_secret(
                name=name,
                secret_type="connector_oauth_token",  # nosec B106  # SecretType label, not a credential
                value=value,
                scope="user",
                created_by=owner_id,
                metadata={"provider": provider, "connector_id": connector_id},
            ),
        )
        if _vault_write_enabled():
            await mirror_credential_to_vault(
                result["id"],
                owner_id,
                value,
                name=name,
                secret_type="connector_oauth_token",  # nosec B106  # SecretType label, not a credential
            )
        return result["id"]

    async def _read_oauth_creds(self, secret_id: str, owner_id: str) -> dict:
        """Read + authorize the OAuth bundle. Used for both the first read and the
        double-check inside the lease (#13627)."""
        secret = None
        if _vault_read_enabled():
            secret = await load_imported_credential(secret_id, owner_id)
        if secret is None:
            secret = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._svc.get_secret(secret_id=secret_id, include_value=True, accessed_by=owner_id),
            )
        if secret is None:
            raise LookupError(f"OAuth secret {secret_id!r} not found or expired")
        self._require_owner(secret, secret_id, owner_id)
        return json.loads(secret["value"])

    @staticmethod
    async def _refresh_lock_available(secret_id: str) -> bool:
        """Whether the refresh lease can be taken at all (#13627).

        Distinguishes "another worker holds the lease" from "there is no Redis to
        hold it in" — ``LeaderLease`` reports both as a failed acquisition.
        """
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client(database=_REFRESH_DB)
            if redis is None:
                return False
            # Ask whether the key is actually held. "A client object exists" is the
            # wrong question: LeaderLease swallows any Redis error and returns
            # False, so a degraded-but-pingable Redis (OOM, MISCONF, read-only
            # replica) would look like "someone else is refreshing" and make every
            # refresh wait then fail — the same total outage this guards against.
            return await redis.get(_refresh_lock_key(secret_id)) is not None
        except Exception:
            return False

    async def _await_refreshed_token(self, secret_id: str, owner_id: str) -> str:
        """Wait for the lease holder's refresh to land, then return its token (#13627).

        The loser of the race must not call the token endpoint — that is the whole
        point of serializing. Polls the stored credential until the holder's write
        appears, then fails loudly rather than falling through to an
        unsynchronized refresh, which would reintroduce the bug.
        """
        deadline = time.monotonic() + _REFRESH_WAIT_S
        delay = _REFRESH_POLL_S
        while time.monotonic() < deadline:
            await asyncio.sleep(delay)
            # Back off: a waiter polling every 200ms drives a sqlite
            # connect/decrypt/UPDATE/commit per iteration through
            # ``_update_access_tracking``, inflating the access audit with
            # non-accesses and loading the shared executor.
            delay = min(delay * 2, 2.0)
            creds = await self._read_oauth_creds(secret_id, owner_id)
            token = creds.get("access_token")
            if token and not self._access_token_expired(creds.get("access_token_expires_at")):
                return token
            # Take over if the holder died or its refresh failed — otherwise one
            # provider error costs every waiter the full wait and then reports a
            # misleading "timed out waiting for a concurrent refresh".
            takeover = LeaderLease(
                key=_refresh_lock_key(secret_id),
                database=_REFRESH_DB,
                ttl_ms=_REFRESH_LOCK_TTL_MS,
                worker_id=uuid.uuid4().hex,
                label="OAuth refresh",
            )
            if await takeover.update_leadership():
                try:
                    return await self._refresh_and_store(secret_id, owner_id, creds)
                finally:
                    await _release_quietly(takeover)
        raise TimeoutError(
            f"Timed out after {_REFRESH_WAIT_S}s waiting for a concurrent OAuth refresh of {secret_id!r}. "
            "Refusing to refresh unsynchronized — a second refresh can invalidate the rotated token."
        )

    async def get_access_token(self, secret_id: str, owner_id: str) -> str:
        """Return a valid access token, refreshing + rotating the secret in place.

        Raises PermissionError on owner mismatch, LookupError when the secret is
        missing or holds no refresh token while the access token is expired.
        Propagates RuntimeError from the token endpoint on a failed refresh.
        Raises TimeoutError (#13627) when another worker holds the refresh lease
        and does not publish a token within the wait window — the caller should
        treat that as retryable rather than fatal.

        When the vault-read flag is on, the vault envelope store is tried first
        (matching :meth:`load`'s expand-phase read-first behaviour, #10088 Task 5) —
        OAuth-managed connector tokens follow the same cutover path as static creds.
        """
        creds = await self._read_oauth_creds(secret_id, owner_id)
        access_token = creds.get("access_token")
        if access_token and not self._access_token_expired(creds.get("access_token_expires_at")):
            return access_token

        # #13627: serialize the refresh per credential. A scheduled sync overlapping
        # a user-triggered one is ordinary operation, and both would otherwise
        # refresh with the same token. Providers that rotate on each use (GitLab,
        # see below) then issue two successors, the second write wins, and the
        # stored token may not be the provider's valid one — the next refresh fails
        # permanently and the user must re-authorize. Some providers treat reuse of
        # a rotated token as a breach signal and revoke the whole grant family
        # (OAuth 2.0 Security BCP 4.14.2), turning the race into a full disconnect.
        lease = LeaderLease(
            key=_refresh_lock_key(secret_id),
            database=_REFRESH_DB,
            ttl_ms=_REFRESH_LOCK_TTL_MS,
            # A unique id per lease, NOT the default hostname-pid. Two refreshes in
            # one process would otherwise share an identity, and ``release()``'s
            # "only delete if it is still mine" guard would happily delete the other
            # holder's key — letting a third caller in while the second still
            # refreshes. The scheduler never hit this because it holds one lease per
            # process; this is the first multi-lease-per-process user.
            worker_id=uuid.uuid4().hex,
            label="OAuth refresh",
        )
        if not await lease.update_leadership():
            # LeaderLease returns False both when another holder has the lease and
            # when Redis is simply unavailable, and the two need opposite handling.
            # Treating "no Redis" as "someone else is refreshing" would make every
            # refresh wait and then fail — a total outage of connector auth wherever
            # Redis is not running, which is far worse than the race being fixed.
            if await self._refresh_lock_available(secret_id):
                # Someone else holds it. Wait for their write instead of issuing a
                # second refresh — the loser must not touch the token endpoint.
                return await self._await_refreshed_token(secret_id, owner_id)
            logger.warning(
                "OAuth refresh could not be serialized (no Redis) — proceeding unsynchronized. "
                "A concurrent refresh may invalidate a rotated refresh token (#13627)."
            )
            return await self._refresh_and_store(secret_id, owner_id, creds)

        try:
            # Double-checked read: the holder may have finished between our first
            # read and our acquiring the lease.
            recheck = await self._read_oauth_creds(secret_id, owner_id)
            token = recheck.get("access_token")
            if token and not self._access_token_expired(recheck.get("access_token_expires_at")):
                return token
            creds = recheck
            return await self._refresh_and_store(secret_id, owner_id, creds)
        finally:
            await _release_quietly(lease)

    async def _refresh_and_store(self, secret_id: str, owner_id: str, creds: dict) -> str:
        """Refresh at the provider and persist. Caller MUST hold the lease (#13627)."""
        refresh_token = creds.get("refresh_token")
        if not refresh_token:
            raise LookupError(
                f"OAuth secret {secret_id!r} access token expired and no refresh token — re-auth required"
            )

        from knowledge.connectors import oauth_flow

        token_response = await oauth_flow.refresh_access_token(
            creds["token_url"], creds["client_id"], creds["client_secret"], refresh_token
        )
        creds["access_token"] = token_response["access_token"]
        # #13626: ``expires_in`` is RECOMMENDED, not REQUIRED, on a refresh
        # response (RFC 6749 §5.1) and several providers omit it. Writing None
        # through here set the expiry to "never", and since a missing expiry is
        # treated as non-expiring the credential was never refreshed again — the
        # token lapsed server-side and every later sync failed with a 401, hours
        # or days after the refresh that caused it.
        #
        # Reuse the lifetime the provider last reported. Carrying the old
        # ``access_token_expires_at`` forward instead would not work: a refresh
        # only runs once that timestamp is already past, so the credential would
        # look expired immediately and re-refresh on every single call.
        # Parse first, then branch on the parsed value. Guarding on the raw one
        # let a malformed ``expires_in`` ("", "n/a", "3600s", []) pass the
        # "reported?" test while still deriving None — which cleared the expiry
        # (recreating this very bug) *and* overwrote the stored lifetime, so even
        # a later well-formed refresh had nothing to fall back to.
        reported_expires_in = self._lifetime_seconds(token_response.get("expires_in"))
        effective_expires_in = (
            reported_expires_in if reported_expires_in is not None else creds.get("access_token_lifetime_seconds")
        )
        if reported_expires_in is None and effective_expires_in is not None:
            # No interpolation from *creds*: every value read out of the
            # decrypted bundle is sensitive, including the provider name and the
            # lifetime, and this warning is not worth putting any of it in logs.
            # The actionable signal is simply that the fallback fired — the
            # original bug's whole character was leaving no trace at all.
            logger.warning(
                "OAuth refresh response omitted a usable expires_in — reusing the stored lifetime for this credential"
            )
        creds["access_token_expires_at"] = self._expiry_iso(effective_expires_in)
        if reported_expires_in is not None:
            creds["access_token_lifetime_seconds"] = reported_expires_in
        if token_response.get("refresh_token"):
            # Providers like GitLab rotate the refresh token on each use.
            creds["refresh_token"] = token_response["refresh_token"]

        value = json.dumps(creds, ensure_ascii=False)
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.update_secret(
                secret_id=secret_id,
                value=value,
                updated_by=owner_id,
            ),
        )
        if _vault_write_enabled():
            await mirror_credential_to_vault(secret_id, owner_id, value)
        return creds["access_token"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _oauth_bundle(
        cls,
        token_response: dict,
        client_id: str,
        client_secret: str,
        token_url: str,
        scopes: list,
        provider: str,
    ) -> dict:
        """Build the stored OAuth credential bundle from a token response."""
        return {
            "provider": provider,
            "access_token": token_response.get("access_token", ""),
            "refresh_token": token_response.get("refresh_token", ""),
            "access_token_expires_at": cls._expiry_iso(token_response.get("expires_in")),
            # The lifetime, kept alongside the derived timestamp so a refresh
            # response that omits ``expires_in`` can recompute one (#13626).
            "access_token_lifetime_seconds": cls._lifetime_seconds(token_response.get("expires_in")),
            "token_type": token_response.get("token_type", "Bearer"),
            "scope": token_response.get("scope", " ".join(scopes)),
            "client_id": client_id,
            "client_secret": client_secret,
            "token_url": token_url,
        }

    @staticmethod
    def _require_owner(secret: dict, secret_id: str, owner_id: str) -> None:
        """Refuse to release a credential that is not provably *owner_id*'s (#13628).

        A missing ``created_by`` is a **denial**, not a skip. The previous form
        was ``if stored_owner and stored_owner != owner_id``, so a secret with an
        empty owner was readable, rotatable and refreshable by *any* caller.

        Defence in depth rather than a known live hole: every writer in this repo
        goes through ``store()``, which always sets ``created_by``. The exposure
        is a row that reaches the table another way — a direct DB write, a NULL
        column, or a future writer that forgets. This guard is the only per-user
        boundary on a decrypted connector secret, so an unattributable credential
        must fail closed rather than open.
        """
        stored_owner = secret.get("created_by") or ""
        if not stored_owner:
            raise PermissionError(
                f"Credential secret {secret_id!r} has no recorded owner — refusing to release it. "
                "Re-create the credential so it carries an owner."
            )
        if stored_owner != owner_id:
            raise PermissionError(f"owner_id mismatch for secret {secret_id!r}: expected {stored_owner!r}")

    @staticmethod
    def _lifetime_seconds(expires_in) -> int | None:
        """Return *expires_in* as whole seconds, or None when not reported (#13626).

        Kept separate from :meth:`_expiry_iso` so the stored lifetime survives a
        refresh response that omits ``expires_in``. Parsing failures return None
        for the same reason ``_expiry_iso`` does — an unusable value is treated
        as "not reported" rather than guessed at.
        """
        if expires_in is None:
            return None
        try:
            return int(expires_in)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _expiry_iso(expires_in) -> str | None:
        """Return ISO expiry timestamp for *expires_in* seconds, or None.

        Only a missing value (None) means non-expiring; ``expires_in == 0`` is a
        real, immediate expiry.
        """
        if expires_in is None:
            return None
        try:
            seconds = int(expires_in)
        except (TypeError, ValueError):
            return None
        return (now_utc() + timedelta(seconds=seconds)).isoformat()

    @staticmethod
    def _access_token_expired(expires_at_iso: str | None) -> bool:
        """True when the access token is unusable within the refresh skew window.

        A missing expiry is treated as non-expiring (some providers omit it).
        """
        if not expires_at_iso:
            return False
        try:
            expires_at = parse_utc_iso(expires_at_iso)
        except (ValueError, TypeError):
            return True
        return now_utc() + timedelta(seconds=ACCESS_TOKEN_REFRESH_SKEW_SECONDS) >= expires_at

    @staticmethod
    def _sensitive_fields(auth_cls: type) -> frozenset:
        fields = getattr(auth_cls, "__sensitive_fields__", None)
        if fields is None:
            raise ValueError(f"{auth_cls.__name__} has no __sensitive_fields__ — cannot separate credentials")
        return fields


# ---------------------------------------------------------------------------
# Module-level singleton factory (ADR-007, GH#9099)
# ---------------------------------------------------------------------------


def _build_credential_store() -> "ConnectorCredentialStore":
    from services.secrets_service import get_secrets_service

    return ConnectorCredentialStore(get_secrets_service())


get_credential_store = lazy_singleton(_build_credential_store)


def reset_credential_store() -> None:
    """Reset the singleton (test isolation / key rotation).

    Creates a fresh lazy_singleton closure so the next get_credential_store()
    call rebuilds with the current SecretsService instance.
    """
    global get_credential_store
    get_credential_store = lazy_singleton(_build_credential_store)
