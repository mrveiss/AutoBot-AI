# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The one "log this once per process" helper (#21071).

Modules used to hand-write the same behaviour: a module-level ``set`` or flag plus a private
``_warn_once``. Each copy had its own state, key scheme and (lack of) locking, so a fix to one
never reached the rest. ``log_once`` is the single implementation.

Scope: a record is identified by ``(logger.name, key)``, so two modules may use the same short
key without silencing each other. The seen-set is bounded by ``AUTOBOT_LOG_ONCE_MAX_KEYS``; past
the bound the least-recently-seen key is forgotten, so a very long-lived process may repeat an
old line rather than grow without limit.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Any

from autobot_shared.env_utils import env_int_clamped

_MAX_KEYS = env_int_clamped("AUTOBOT_LOG_ONCE_MAX_KEYS", 1024, min_v=1)

_LOCK = threading.Lock()
_SEEN: "OrderedDict[tuple[str, str], None]" = OrderedDict()


def _first_sight(scope: str, key: str, max_keys: int) -> bool:
    """True the first time ``(scope, key)`` is seen; evicts the oldest key past ``max_keys``."""
    ident = (scope, key)
    with _LOCK:
        if ident in _SEEN:
            _SEEN.move_to_end(ident)
            return False
        _SEEN[ident] = None
        while len(_SEEN) > max_keys:
            _SEEN.popitem(last=False)
        return True


def first_time(scope: str, key: str) -> bool:
    """True the first time ``(scope, key)`` is seen in this process (bounded, thread-safe).

    For sites that do more than log, or log somewhere other than a logger (stderr while a logger is
    being built): they ask here instead of keeping their own set. ``log_once`` is built on it.
    """
    return _first_sight(scope, key, _MAX_KEYS)


def log_once(logger: logging.Logger, level: int, key: str, msg: str, *args: Any, **kwargs: Any) -> bool:
    """Log ``msg % args`` at ``level`` the first time ``key`` is used with ``logger``.

    ``kwargs`` (``extra=``, ``exc_info=``) go to the logger call unchanged. Returns True when the
    record was emitted. Thread-safe. The record's call site is the caller of ``log_once``, not this
    module. Only stdlib loggers: a structlog logger has no ``name``; its caller uses ``first_time``.
    """
    if not first_time(logger.name, key):
        return False
    logger.log(level, msg, *args, stacklevel=2, **kwargs)
    return True


def reset_log_once(scope: logging.Logger | str | None = None, key: str | None = None) -> None:
    """Forget remembered keys (tests): all of them, one scope's (a logger or its name), or one key."""
    name = scope.name if isinstance(scope, logging.Logger) else scope
    with _LOCK:
        if name is None:
            _SEEN.clear()
            return
        for ident in [i for i in _SEEN if i[0] == name and (key is None or i[1] == key)]:
            del _SEEN[ident]
