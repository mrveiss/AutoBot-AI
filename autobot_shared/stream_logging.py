# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Centralized stdout/stderr log-stream routing (#12488).

Systemd captures each service's raw stdout into an info/access log file and
its raw stderr into an error log file (``StandardOutput=append:...``,
``StandardError=append:...`` — see #12464). Two independent code paths were
sending INFO-level output to stderr regardless of level, flooding
``*-error.log`` with benign lines (e.g. uvicorn's "WebSocket ... [accepted]"
and websockets' "connection open"):

1. Uvicorn's own default ``LOGGING_CONFIG`` sends everything logged via the
   ``uvicorn``/``uvicorn.error`` logger (startup banner, connection
   lifecycle, warnings, errors) to a single stderr ``StreamHandler`` —
   only the separate ``uvicorn.access`` logger goes to stdout.
2. ``autobot_shared.logging_manager.LoggingManager`` attached a bare
   ``logging.StreamHandler()`` (which defaults to ``sys.stderr`` and has no
   level filter) as a "console handler" to every logger it configures.

This module is the single source of truth for the fix: split any logger's
output so DEBUG/INFO goes to stdout and WARNING+ goes to stderr, without
changing formats or the level of what is emitted. Reused by:

- ``autobot_shared/logging_manager.py`` (per-module console handler)
- ``autobot_shared/uvicorn_log_config.json`` (loaded by
  ``load_uvicorn_log_config()`` for ``uvicorn.run(log_config=...)``, and
  referenced directly via the uvicorn CLI's ``--log-config`` flag from the
  systemd ``ExecStart=`` lines for autobot-backend and autobot-slm-backend)
"""

import json
import logging
import sys
from pathlib import Path

_UVICORN_LOG_CONFIG_PATH = Path(__file__).parent / "uvicorn_log_config.json"


class MaxLevelFilter(logging.Filter):
    """Reject any log record at or above ``max_level``.

    Pairs with a sibling handler whose own ``level`` is set to
    ``max_level`` — together the two handlers split a single logger's
    output across streams by level without touching format or level of
    what gets emitted.
    """

    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.max_level


def build_stdout_handler(formatter: logging.Formatter | None = None) -> logging.StreamHandler:
    """Build a DEBUG/INFO handler writing to stdout (WARNING+ filtered out)."""
    handler = logging.StreamHandler(sys.stdout)
    if formatter is not None:
        handler.setFormatter(formatter)
    handler.addFilter(MaxLevelFilter(logging.WARNING))
    return handler


def build_stderr_handler(formatter: logging.Formatter | None = None) -> logging.StreamHandler:
    """Build a WARNING+ handler writing to stderr."""
    handler = logging.StreamHandler(sys.stderr)
    if formatter is not None:
        handler.setFormatter(formatter)
    handler.setLevel(logging.WARNING)
    return handler


def load_uvicorn_log_config() -> dict:
    """Load the shared stdout/stderr-split uvicorn logging config.

    Single JSON source of truth for both the ``uvicorn --log-config`` CLI
    flag (systemd ``ExecStart=``) and ``uvicorn.run(log_config=...)``
    (standalone/dev entry points) so backend and slm-backend never drift.
    """
    with _UVICORN_LOG_CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)
