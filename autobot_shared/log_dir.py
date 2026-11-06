# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The ONE log-directory resolver (#20894): logs are never written inside the source tree.

Stdlib-only on purpose: ``logging_manager`` runs before ``ssot_config`` can initialise, so it
cannot import config, yet it, ``ssot_config`` and ``ssot_constants`` must all answer the same.

Order:
  1. ``AUTOBOT_LOGS_DIR`` -- the single env name. Installs set it explicitly (ansible agent.env,
     distributed.env, slm-agent unit, docker-compose), so a deployed node never reaches the default.
  2. ``AUTOBOT_LOG_DIR`` -- deprecated alias, read through; using it logs one warning.
  3. Default: a per-process temp directory under pytest, else ``$XDG_STATE_HOME/autobot/logs``
     (``~/.local/state/autobot/logs``). Never the cwd, never the repo root.

A relative value is anchored at the install base (``AUTOBOT_BASE_DIR``, else the project root),
the same anchor ``ssot_config`` uses for its relative path settings, never the cwd.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
import tempfile
from pathlib import Path

from autobot_shared.paths import install_base_dir

LOGS_DIR_ENV = "AUTOBOT_LOGS_DIR"
DEPRECATED_LOGS_DIR_ENV = "AUTOBOT_LOG_DIR"
_STATE_HOME_ENV = "XDG_STATE_HOME"
_warned_alias = False


def _under_pytest() -> bool:
    """True inside a test run (a pytest process, or a subprocess that opted in)."""
    return "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ or "AUTOBOT_TESTING" in os.environ


@functools.lru_cache(maxsize=1)
def _process_temp_dir() -> Path:
    """One temp directory per process, so every caller in a test run agrees."""
    return Path(tempfile.mkdtemp(prefix="autobot-logs-"))


def _state_home() -> Path:
    """``$XDG_STATE_HOME`` when it is an absolute path (the spec), else ``~/.local/state``."""
    configured = os.environ.get(_STATE_HOME_ENV, "")
    if configured and os.path.isabs(configured):
        return Path(configured)
    return Path.home() / ".local" / "state"


def _default_logs_dir() -> Path:
    if _under_pytest():
        return _process_temp_dir()
    return _state_home() / "autobot" / "logs"


def _configured() -> str:
    """The env value in force: the one name, else the deprecated alias (warned once)."""
    global _warned_alias
    value = os.environ.get(LOGS_DIR_ENV, "")
    if value:
        return value
    legacy = os.environ.get(DEPRECATED_LOGS_DIR_ENV, "")
    if legacy and not _warned_alias:
        _warned_alias = True
        logging.getLogger(__name__).warning(
            "%s is deprecated; set %s instead (#20894)", DEPRECATED_LOGS_DIR_ENV, LOGS_DIR_ENV
        )
    return legacy


def resolve_logs_dir() -> Path:
    """The absolute log directory for this process (not created here)."""
    configured = _configured()
    if not configured:
        return _default_logs_dir()
    path = Path(configured).expanduser()
    return path if path.is_absolute() else install_base_dir() / path
