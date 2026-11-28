# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis connection target for the LangGraph checkpointer (#18953).

``AsyncRedisSaver`` takes a URL, not a client, so the URL must come from the
SSOT builder (ACL user, password, ``rediss://`` and TLS port all included) and
TLS client material must travel as ``connection_args``.

Database choice: the saver creates RediSearch indexes (``FT.CREATE`` through
redisvl) and this deployment's RediSearch only operates on logical db 0
("Cannot create index on db != 0"; see the ``memory`` alias in
``autobot_shared/redis_management/types.py``). The db therefore comes from the
``memory`` entry of ``DATABASE_MAPPING`` (db 0) rather than a hardcoded number.
"""

from typing import Any

from autobot_shared.redis_management.types import DATABASE_MAPPING
from autobot_shared.secret_redaction import redact_content, redact_url_userinfo
from autobot_shared.ssot_config import config as ssot
from autobot_shared.tls import redis_ssl_connection_kwargs

# Named database holding the saver's RediSearch indexes (db 0 alias).
CHECKPOINTER_DB_NAME = "memory"


def get_checkpointer_connection() -> tuple[str, dict[str, Any]]:
    """Return ``(redis_url, connection_args)`` for ``AsyncRedisSaver``.

    The URL is built only by ``get_redis_url_for_db``; ``connection_args`` is
    empty unless Redis TLS is enabled.
    """
    url = ssot.get_redis_url_for_db(DATABASE_MAPPING[CHECKPOINTER_DB_NAME])
    args = redis_ssl_connection_kwargs() if ssot.tls.redis_tls_enabled else {}
    return url, args


def describe_connection(url: str) -> str:
    """Log-safe form of ``url`` (password and username masked)."""
    return redact_url_userinfo(url, mask_username=True)


def describe_error(exc: BaseException) -> str:
    """Log-safe text of ``exc``: Redis errors can echo the credentialed URL."""
    return redact_content(str(exc))
