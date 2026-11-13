# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The ONE log-directory resolver (#20894): logs are never written inside the source tree.

Stdlib-only on purpose: ``logging_manager`` runs before ``ssot_config`` can initialise, so it
cannot import config, yet it, ``ssot_config`` and ``ssot_constants`` must all answer the same.

Order:
  1. ``AUTOBOT_LOGS_DIR`` -- the single env name. Every deploy route sets it to the path that
     route provides: the ansible env templates and units, and docker-compose (the ``/app/logs``
     volume), so a deployed process never reaches the default.
  2. ``AUTOBOT_LOG_DIR`` -- deprecated alias, read through; using it logs one warning.
  3. ``LOGS_DIR_DEFAULT`` (unset) -- ``$XDG_STATE_HOME/autobot/logs`` (``~/.local/state/autobot/logs``),
     the dev route. A test run never gets here: the root conftest points ``AUTOBOT_LOGS_DIR`` at
     the run's temp directory. Never the cwd, never the repo root.

A relative value is anchored at the install base (``AUTOBOT_BASE_DIR``, else the project root),
the same anchor ``ssot_config`` uses for its relative path settings, never the cwd.

Resolving touches nothing on disk: a module may resolve at import. The directory and the file are
created by ``FirstWriteFileHandler`` when the first record is written, so importing writes nothing.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable

from autobot_shared.paths import install_base_dir

LOGS_DIR_ENV = "AUTOBOT_LOGS_DIR"
DEPRECATED_LOGS_DIR_ENV = "AUTOBOT_LOG_DIR"
#: The ONE declared default for ``AUTOBOT_LOGS_DIR`` -- the env registry and ``PathConfig`` both use it.
#: Unset: there is no single deploy path (each route sets its own), so the resolver decides.
LOGS_DIR_DEFAULT = ""
_STATE_HOME_ENV = "XDG_STATE_HOME"
_warned_alias = False

#: Called with the path that could not be created or opened, and the error, at the first write.
UnwritableCallback = Callable[[Path, OSError], None]


def _state_home() -> Path:
    """``$XDG_STATE_HOME`` when it is an absolute path (the spec), else ``~/.local/state``.

    With no resolvable home (``Path.home()`` raises ``RuntimeError``) a per-user temp directory.
    """
    configured = os.environ.get(_STATE_HOME_ENV, "")
    if configured and os.path.isabs(configured):
        return Path(configured)
    try:
        return Path.home() / ".local" / "state"
    except RuntimeError:  # no resolvable home (a bare container user): never raise at import
        return Path(tempfile.gettempdir()) / f"autobot-state-{os.getuid() if hasattr(os, 'getuid') else 0}"


def _configured() -> str:
    """The env value in force: the one name, else the deprecated alias (warned once)."""
    global _warned_alias
    value = os.environ.get(LOGS_DIR_ENV, LOGS_DIR_DEFAULT).strip()
    if value:
        return value
    legacy = os.environ.get(DEPRECATED_LOGS_DIR_ENV, "").strip()
    if legacy and not _warned_alias:
        _warned_alias = True
        logging.getLogger(__name__).warning(
            "%s is deprecated; set %s instead (#20894)", DEPRECATED_LOGS_DIR_ENV, LOGS_DIR_ENV
        )
    return legacy


def resolve_logs_dir(configured: str | None = None) -> Path:
    """The absolute log directory for this process. Neither created nor probed here.

    *configured* is a value already read from the environment (``PathConfig.logs_dir``); None reads it.
    """
    value = (_configured() if configured is None else configured).strip()
    if not value:
        return _state_home() / "autobot" / "logs"
    path = Path(value).expanduser()
    return path if path.is_absolute() else install_base_dir() / path


def _warn_unwritable(path: Path, exc: OSError) -> None:
    """The default *on_unwritable*: one stderr line -- a logger cannot log its own failure (#19628)."""
    sys.stderr.write(f"autobot logging: cannot write logs at {str(path)!r} ({exc.strerror}); file handler off\n")


class FirstWriteFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating file handler that creates its directory and opens its file at the first record (#20894).

    Constructing one touches nothing on disk, so a module that builds a logger at import writes nothing.
    A directory or file that cannot be written turns this handler off with one *on_unwritable* call
    (default: one stderr line); the logger's other handlers (console, which journald captures) keep working.
    """

    def __init__(
        self,
        filename: str,
        *,
        max_bytes: int = 0,
        backup_count: int = 0,
        on_unwritable: UnwritableCallback = _warn_unwritable,
    ) -> None:
        super().__init__(filename, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8", delay=True)
        self._on_unwritable = on_unwritable
        self._unwritable = False

    @property
    def unwritable(self) -> bool:
        """True once a first write failed; this handler writes nothing from then on."""
        return self._unwritable

    def _open_at_first_write(self) -> bool:
        """Create the directory, then open the file; False (and the handler off) when either fails."""
        directory = Path(self.baseFilename).parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return self._turn_off(directory, exc)
        try:
            self.stream = self._open()
        except OSError as exc:
            return self._turn_off(Path(self.baseFilename), exc)
        return True

    def _turn_off(self, path: Path, exc: OSError) -> bool:
        """Stop writing for good and report *path* once; called with the handler lock held."""
        self._unwritable = True
        self._on_unwritable(path, exc)
        return False

    def emit(self, record: logging.LogRecord) -> None:
        """Write *record*, opening the file first if this is the first one; a no-op once unwritable."""
        if self._unwritable:
            return
        if self.stream is None and not self._open_at_first_write():
            return
        super().emit(record)
