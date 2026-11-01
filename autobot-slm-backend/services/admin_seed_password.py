# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one place the SLM resolves its admin password from its environment (#19318, #19368).

Two inputs, one name each, both registered in ``autobot_shared/env_registry_npu.py``:

- ``SLM_ADMIN_PASSWORD``: the value itself (slm-secrets.env, compose ``--env-file``). When set,
  startup keeps an existing admin in step with it (``admin_password_sync``), as before.
- ``SLM_ADMIN_PASSWORD_FILE``: a path to the value (the hardened compose overlay's mounted
  secret). Owner decision on #19368, **migrate-safe**: it seeds a FRESH install only. An
  existing admin keeps its stored password and nothing is reset on upgrade -- otherwise every
  hardened host would have its admin password replaced at its next start.

Both are read with the registry's default ("") -- the env-forks hook fails any reader whose
fallback disagrees with it. Not through ``env_registry.env``: importing the registry pulls in
logging_manager, which reads the config the SLM test conftest mocks.

There is no default password: neither input set means the caller generates a random one.
A ``_FILE`` that is set but unreadable or empty raises, so a broken secret mount stops the
first start with a clear error instead of seeding a password nobody knows.
"""

import os
from pathlib import Path

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.password_weakness import check_guessable

logger = get_logger(__name__)  # #19288: the stdlib exception is retired; admin_password_sync does the same


class AdminPasswordFileError(RuntimeError):
    """SLM_ADMIN_PASSWORD_FILE is set but cannot supply a password (#19368)."""


def _read_password_file(path: str) -> str:
    """The password in *path*, stripped; raises naming the variable, never the value."""
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AdminPasswordFileError(f"SLM_ADMIN_PASSWORD_FILE ({path}) is unreadable: {exc.strerror}") from None
    if not value:
        raise AdminPasswordFileError(f"SLM_ADMIN_PASSWORD_FILE ({path}) is empty")
    return value


def password_for_new_admin() -> str:
    """Password to create the admin with: SLM_ADMIN_PASSWORD, else the _FILE secret, else "" (generate one).

    A guessable one is refused, which also means "" (#16299): a host whose admin was renamed can come here
    with an old short password on file, and a refusal must not stop every restart. An existing admin is
    never checked: changing a live password is its owner's decision.
    """
    password = os.getenv("SLM_ADMIN_PASSWORD", "")
    path = os.getenv("SLM_ADMIN_PASSWORD_FILE", "")
    chosen = password or (_read_password_file(path) if path else "")
    reason = check_guessable(chosen) if chosen else None
    if reason:
        logger.error("The configured SLM admin password was refused, so a random one is used: %s", reason)
        return ""
    return chosen


def password_for_existing_admin() -> str:
    """Password to keep an existing admin in step with: SLM_ADMIN_PASSWORD only, never the _FILE.

    "" means keep the stored password. When only the _FILE is set, that is the migrate-safe
    path (#19368): say so at info, so an operator who expected a reset can see why not.
    """
    password = os.getenv("SLM_ADMIN_PASSWORD", "")
    if not password and os.getenv("SLM_ADMIN_PASSWORD_FILE", ""):
        logger.info(
            "Admin user already exists: stored password kept; "
            "SLM_ADMIN_PASSWORD_FILE seeds a fresh install only (#19368)"
        )
    return password
