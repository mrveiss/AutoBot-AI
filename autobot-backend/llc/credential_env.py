# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Role credentials as agent environment variables (#20533).

A role's active credentials reach a subprocess agent as environment variables
named after the secret. The secret name is the variable name (owner decision
2026-11-17), so the name is the trust boundary: it is validated here and a bad
one is **refused**, never silently renamed.

Policy: a true name allow-list is impossible (secret names double as env
names), so the strict format regex is the allow-*pattern* and the one shared
denylist, ``services.execution.env_sanitizer.is_reserved_env_name`` (loader,
interpreter, shell, proxy/TLS, resolver, toolchain and provider-credential
families plus AutoBot's own ``AUTOBOT_*`` / ``LLC_*``), is the guard. There is
no second list here. Values are never logged or returned from here; a refusal
is a short reason code.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.secret_redaction import REDACTED_PLACEHOLDER
from services.execution.env_sanitizer import is_reserved_env_name

logger = get_logger(__name__)

# Context key carrying ``{env_name: value}`` from the scheduler to the adapter.
ROLE_CREDENTIALS_KEY = "role_credentials"

REFUSED_BAD_FORMAT = "invalid_env_name"
REFUSED_PROTECTED = "protected_env_name"
REFUSED_DUPLICATE = "duplicate_name"

_ENV_NAME_MAX = 128
_ENV_NAME_RE = re.compile(rf"[A-Z][A-Z0-9_]{{0,{_ENV_NAME_MAX - 1}}}")


def env_name_refusal(name: Any) -> Optional[str]:
    """The reason code *name* may not be injected as an env var, or ``None`` when it may."""
    if not isinstance(name, str) or not _ENV_NAME_RE.fullmatch(name):
        return REFUSED_BAD_FORMAT
    if is_reserved_env_name(name):
        return REFUSED_PROTECTED
    return None


def inject_role_credentials(env: dict, context: Mapping[str, Any]) -> None:
    """Copy ``context["role_credentials"]`` into *env*, skipping any refused name.

    The scheduler already filtered; this re-checks because *env* is the process
    boundary and the context is a plain dict anyone upstream can write to.
    """
    for name, value in (context.get(ROLE_CREDENTIALS_KEY) or {}).items():
        reason = env_name_refusal(name)
        if reason is not None:
            logger.warning("role credential not injected: reason=%s", reason)
            continue
        env[name] = str(value)


def redact_role_credentials(context: dict) -> dict:
    """*context* with every injected credential value masked (names kept)."""
    creds = context.get(ROLE_CREDENTIALS_KEY)
    if not creds:
        return context
    return {
        **context,
        ROLE_CREDENTIALS_KEY: {name: REDACTED_PLACEHOLDER for name in creds},
    }
