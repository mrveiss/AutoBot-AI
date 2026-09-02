# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Health probe for the secrets store (#14126).

Registers under ``KnownProbes.SECRETS_STORE``. The probe reports:
  - "ok"       - the store was read
  - "degraded" - the store could not be read

Why this probe exists at all. ``_load_secrets_hosts`` used to answer a store
failure with ``[]``, which is indistinguishable from "the operator has
configured no hosts": the UI rendered an empty, healthy-looking list and
nothing anywhere said the store was broken. That call site now raises
``SecretsStoreUnavailable``, so the two *callers* fail honestly - but a caller
only speaks when someone calls it. An operator opening the health page while
nobody happens to be listing hosts still saw a fully healthy system.

Why "degraded" and not "down". The application is running and everything that
does not need a credential still works. ``down`` would claim the platform is
unavailable, which is both false and the sort of conflation that trains people
to ignore the health page. The distinction is the same one #14872 drew for the
sandbox probe: available-but-unsafe is not the same as unavailable.

Why an empty store is "ok". ``SecretsManager._load_secrets`` returns ``{}``
when the secrets file does not exist yet, which is a legitimate fresh install,
not a fault. Reporting that as degraded would make the probe cry wolf on every
new deployment - and a probe that is degraded by default is a probe nobody
reads.
"""

from __future__ import annotations

import asyncio

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe


@register_health_probe(KnownProbes.SECRETS_STORE)
async def _secrets_store_health_probe(request: Request | None = None) -> ComponentHealth:
    try:
        from api.secrets import secrets_manager

        # `list_secrets` is synchronous blocking file I/O under a lock, and
        # `asyncio.wait_for` cannot cancel a blocking call - without the thread
        # hop a wedged store would hold the whole aggregator past its timeout
        # instead of being reported. Same wrap as api/secrets.py uses.
        await asyncio.to_thread(secrets_manager.list_secrets)
    except Exception as exc:
        # Deliberately no secret material, no store path, and no exception
        # message in `detail`: this payload is served to anyone who can reach
        # the health endpoint. The type name is enough to route the operator to
        # the logs, where the full traceback already is.
        return ComponentHealth(
            name=KnownProbes.SECRETS_STORE,
            status="degraded",
            detail=(
                f"secrets store unreadable ({type(exc).__name__}); credentials cannot be "
                "resolved, so host listings and any operation needing a token will fail"
            ),
        )

    return ComponentHealth(
        name=KnownProbes.SECRETS_STORE,
        status="ok",
        detail=None,
    )
