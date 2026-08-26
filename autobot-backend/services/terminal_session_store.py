# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis-backed terminal session config registry, shared across workers (#14961).

``api.terminal_handlers.TerminalManager.session_configs`` used to be a plain
process-local ``dict``. The deployed backend runs uvicorn with multiple
workers plus request-count recycling (see
``autobot-infrastructure/autobot-backend/templates/autobot-user-backend.service``),
so a session created on one worker was invisible to a WebSocket handshake
served by another -- and, after #14989 turned an unknown session_id from a
default-configured terminal into a hard `1008` refusal, that invisibility
reads on the wire exactly like "you are not the owner of this session"
instead of what it actually is: this worker never saw the write.

``SessionConfigStore`` is a drop-in, dict-like replacement backed by the
canonical Redis client (``autobot_shared.redis_client.get_redis_client``,
database="sessions") so every worker resolves the same session. It implements
exactly the subset of the ``dict`` protocol the call sites in
``api/terminal.py``, ``api/terminal_handlers.py`` and
``services/agent_terminal/session_manager.py`` use --
``__setitem__``/``__getitem__``/``__delitem__``/``get``/``pop``/``__contains__``/
``items`` -- so neither of those two ceiling-frozen files (#14961: both
``api/terminal.py`` and ``api/terminal_handlers.py`` are grandfathered at an
exact line count and may not grow) needs to change its access pattern, only
what `session_configs` is constructed from.

Fail-closed on a Redis outage, deliberately (#14961): this lookup gates
whether a WebSocket may attach to a live shell, i.e. it is
authorization-adjacent. A `get()` (or `__contains__`) that cannot reach Redis
returns "not found" exactly like a session that never existed, rather than
falling back to an in-process cache that would silently readmit the
permissive behaviour #14989 just closed. A write (`__setitem__`) that cannot
reach Redis raises, so `create_terminal_session` surfaces a 500 instead of
minting a session only this worker will ever be able to see.
"""

import json
from enum import Enum
from typing import Any, Iterator

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from constants.ttl_constants import TTL_24_HOURS

logger = get_logger(__name__)

# Module-level constant, backed by an env var -- never a literal (CLAUDE.md).
# Registered in autobot_shared/env_registry_terminal.py; see that module for
# the default's rationale.
_SESSION_CONFIG_TTL_SECONDS = env_int("AUTOBOT_TERMINAL_SESSION_TTL_SECONDS", TTL_24_HOURS)

_KEY_PREFIX = "terminal:session_config:"
_SCAN_COUNT = 200


class TerminalSessionStoreWriteError(RuntimeError):
    """Raised when a session config cannot be durably written (#14961).

    Distinct from a plain `RuntimeError` so callers -- and tests -- can tell
    "Redis is unreachable" apart from any other failure `with_error_handling`
    already maps to a 500.
    """


def _default_json(value: Any) -> Any:
    """`json.dumps(default=...)` hook: enum members serialize as their value.

    `TerminalSessionRequest.security_level` is a `SecurityLevel` enum member,
    not a str-enum, so the plain-dict config that used to live safely in
    process memory needs this to round-trip through JSON as `"standard"`
    rather than `str(SecurityLevel.STANDARD)` == `"SecurityLevel.STANDARD"`,
    which `SecurityLevel(...)` cannot parse back.
    """
    if isinstance(value, Enum):
        return value.value
    return str(value)


class SessionConfigStore:
    """Dict-like, Redis-backed replacement for the old process-local dict.

    One instance per `TerminalManager` (see `api/terminal_handlers.py`), but
    every instance -- in this process or another worker's -- reads and writes
    the same Redis keys, so "created on worker A, attached from worker B"
    resolves. Accepts an injected client for tests (#14961: "do not write to
    the live Redis; tests use their own fixture") -- production code leaves
    it unset and resolves the canonical client lazily on every call, matching
    every other call site in this codebase (`get_redis_client` owns pooling
    and the circuit breaker; nothing here should cache a client across calls).
    """

    def __init__(self, redis_client: Any = None, database: str = "sessions") -> None:
        self._injected_client = redis_client
        self._database = database

    def _client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        try:
            return get_redis_client(database=self._database)
        except Exception as exc:  # pragma: no cover - defensive, mirrors get() below
            logger.warning("SessionConfigStore: could not obtain Redis client: %s", exc)
            return None

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{_KEY_PREFIX}{session_id}"

    def __setitem__(self, session_id: str, config: dict) -> None:
        client = self._client()
        if client is None:
            raise TerminalSessionStoreWriteError(
                f"Cannot persist terminal session config for {session_id}: " "Redis (database=sessions) is unavailable."
            )
        payload = json.dumps(config, default=_default_json)
        client.setex(self._key(session_id), _SESSION_CONFIG_TTL_SECONDS, payload)

    def get(self, session_id: str, default: Any = None) -> Any:
        client = self._client()
        if client is None:
            # Fail closed (#14961): a lookup that cannot reach Redis is
            # indistinguishable, on purpose, from "session does not exist".
            logger.warning(
                "SessionConfigStore: Redis unavailable, treating session %s as not found (fail-closed)",
                session_id,
            )
            return default
        raw = client.get(self._key(session_id))
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            logger.error("SessionConfigStore: corrupt config for session %s: %s", session_id, exc)
            return default

    def __getitem__(self, session_id: str) -> dict:
        sentinel = object()
        value = self.get(session_id, sentinel)
        if value is sentinel:
            raise KeyError(session_id)
        return value

    def __delitem__(self, session_id: str) -> None:
        client = self._client()
        if client is None:
            return
        client.delete(self._key(session_id))

    def pop(self, session_id: str, default: Any = None) -> Any:
        value = self.get(session_id, default)
        self.__delitem__(session_id)
        return value

    def __contains__(self, session_id: str) -> bool:
        sentinel = object()
        return self.get(session_id, sentinel) is not sentinel

    def items(self) -> Iterator[tuple]:
        """Yield (session_id, config) for every live session, this worker's or not.

        Scans rather than KEYS (non-blocking) and skips any entry that
        expired or was deleted between the scan and the read, rather than
        raising -- a session config with a live TTL that vanished mid-scan is
        not this iterator's problem to report.
        """
        client = self._client()
        if client is None:
            logger.warning("SessionConfigStore: Redis unavailable, listing zero sessions (fail-closed)")
            return
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match=f"{_KEY_PREFIX}*", count=_SCAN_COUNT)
            for key in keys:
                raw = client.get(key)
                if raw is None:
                    continue
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                session_id = key_str[len(_KEY_PREFIX) :]
                try:
                    yield session_id, json.loads(raw)
                except (TypeError, ValueError) as exc:
                    logger.error("SessionConfigStore: corrupt config for session %s: %s", session_id, exc)
            if cursor == 0:
                break
