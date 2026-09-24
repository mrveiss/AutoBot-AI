# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The vault-owned GitHub service credential, and the env that carries it (#13859).

Extracted from `workers/audit_tasks.py` (#17090), unchanged in behaviour: the
audit worker was the first caller, and AutoBot's acceptance-criteria verifier is
the second, so the credential path became shared rather than copied. A forked
copy of a secrets path is the worst kind of duplication -- the two drift, and
the one nobody is looking at is the one that keeps working after a revocation.

The rule this encodes, from #13859: a background task authenticates with a
token the SYSTEM vault owns and `PrincipalKind.SERVICE` attributes, never with
whatever ambient `gh` CLI auth the host happens to carry. Nothing owns ambient
auth, nothing rotates it, nothing audits it, and its absence shows up only as a
log line -- which is exactly how it lapsed unnoticed in #13570.

`gh_env` takes an optional resolver so a caller that already has its own
patchable resolution point keeps it; `audit_tasks` passes its own, which is why
its tests still govern what its `gh` subprocesses see.
"""

from __future__ import annotations

import os
from typing import Callable

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: The vault entry every background GitHub write authenticates with. Named for
#: the credential rather than for the token it holds: this is a lookup key, and
#: a name containing "token" reads to bandit's B105 as a hardcoded secret.
FILING_CREDENTIAL_VAULT_KEY = "github_issue_filing_token"


def resolve_service_token() -> str | None:
    """Read the issue-filing token from the SYSTEM vault (#13859).

    The worker used to rely entirely on ambient `gh` CLI auth for whichever
    account Celery happened to run as. Nothing owned that credential, nothing
    rotated it, nothing audited its use, and the only place its absence showed
    up was a log line — which is exactly how it lapsed unnoticed in #13570.

    SYSTEM vault and `PrincipalKind.SERVICE`: this is a background task, not a
    user session, so there is no user vault it could belong to and the audit
    trail should attribute filings to the service rather than to whoever last
    logged into the host. `VaultKind.SYSTEM` is documented as the home for
    "admin-only system secrets (provider keys, internal tokens)".

    Returns None when no token is stored — the caller decides what that means,
    and says so loudly rather than silently continuing on ambient state.
    """
    try:
        return run_or_schedule(_read_service_token())
    except Exception as exc:  # noqa: BLE001 — a vault outage must not kill the audit run
        # Class name only, never the exception text. This is a secrets path, and
        # a message that happens to interpolate a value would put it in the log.
        # CodeQL flags it as clear-text-logging-sensitive-data and is right to:
        # the guarantee should be structural, not a reader having audited every
        # exception type these calls can raise.
        logger.warning("github credential: vault lookup for the service token failed (%s)", type(exc).__name__)
        return None


async def _read_service_token() -> str | None:
    from sqlalchemy import select  # noqa: PLC0415

    from api.user_management.dependencies import get_async_session  # noqa: PLC0415
    from autobot_shared.secrets_vault import VaultKind, VaultRef  # noqa: PLC0415
    from models.secret import Secret  # noqa: PLC0415
    from services.envelope_secrets_service import (  # noqa: PLC0415
        EnvelopeSecretsService,
        SecretAccessError,
        SecretNotFoundError,
    )

    owner = VaultRef(kind=VaultKind.SYSTEM)
    owner_str = owner.to_str()
    async for session in get_async_session():
        result = await session.execute(
            select(Secret).where(Secret.name == FILING_CREDENTIAL_VAULT_KEY, Secret.owner_vault == owner_str)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        try:
            raw = await EnvelopeSecretsService().read(session, secret_id=row.id, accessible_vaults=[owner])
        except (SecretNotFoundError, SecretAccessError) as exc:
            # Class name only — same reason as above.
            logger.warning("github credential: service token present but unreadable (%s)", type(exc).__name__)
            return None
        return raw.decode("utf-8").strip() or None
    return None


# (env, came_from_vault) — one fact, cached together. Deriving the second from
# the first is what made the detector lie (#13859 review).
_env_cache: tuple[dict[str, str], bool] | None = None


def reset_env_cache() -> None:
    """Drop the cached credential so the next run re-reads the vault (#13859).

    Called at the start of every audit task. Celery workers are long-lived, so
    without this a rotated or revoked token would keep working for the life of
    the process — which would defeat the revocation this issue is about.
    """
    global _env_cache
    _env_cache = None


def gh_env(resolve: Callable[[], str | None] | None = None) -> tuple[dict[str, str], bool]:
    """Subprocess environment for every `gh` call, and whether the vault
    supplied the token (#13859).

    Mirrors the LLC Copilot adapter: both GH_TOKEN and GITHUB_TOKEN, because
    different gh subcommands read different ones.

    Returns the flag rather than letting callers test `"GH_TOKEN" in env`. That
    test answers "does this process have a token anywhere?", which is a
    different question: the env starts as a copy of os.environ, and an ambient
    GH_TOKEN is exactly what the pre-#13859 CRITICAL log told operators to set
    — docker-compose injects an empty one unconditionally. Deriving the flag
    that way reported ambient state as vault-owned, suppressed the warning this
    change exists to emit, and told the operator the credential came from the
    vault while asking them to put one there.

    Cached per run: a task files one issue per finding, and a vault round-trip
    per finding would be pure waste.
    """
    global _env_cache
    if _env_cache is not None:
        env, from_vault = _env_cache
        return dict(env), from_vault
    env = dict(os.environ)
    token = (resolve or resolve_service_token)()
    if token:
        env["GH_TOKEN"] = token
        env["GITHUB_TOKEN"] = token
    _env_cache = (env, bool(token))
    return dict(env), bool(token)


def vault_backed_now() -> bool:
    """Did THIS run resolve a vault-owned token? Read, never re-derive.

    Reads the cache `_gh_available` already populated rather than calling
    `_gh_env()` again. Re-deriving would trigger a second vault round-trip --
    and, where `_gh_available` is substituted, a lookup that the run itself
    never made, so the recorded credential source would describe a code path
    that did not execute. An empty cache means nothing resolved a token, which
    is exactly "not vault-backed".
    """
    return bool(_env_cache[1]) if _env_cache is not None else False
