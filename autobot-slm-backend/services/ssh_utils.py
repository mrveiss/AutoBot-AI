# Copyright 2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical ssh-key usability gate (#11793).

``Path(SSH_KEY_PATH).exists()`` propagates ``PermissionError`` when the key's
parent directory is unreadable (EACCES is not in pathlib's ignored-errno set),
so every ssh command build crashed with an unhandled exception instead of
degrading.  ``_ssh_key_usable`` is the one safe gate: it returns ``True`` only
when the key is confirmed readable and fails closed (``False`` -> no ``-i``
flag, ssh uses its default identity) on ANY doubt, logging an actionable
WARNING once per path instead of crashing.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths already warned about — warn once per path per process so a persistent
# permissions misconfiguration degrades with a single actionable line instead
# of replacing crash spam with log spam (#11793).
_WARNED_PATHS: set = set()


def _warn_once(path: str, detail: str) -> None:
    """Log the not-usable WARNING for *path* at most once per process."""
    if path in _WARNED_PATHS:
        return
    _WARNED_PATHS.add(path)
    logger.warning(
        "SSH key %s is not usable (%s); falling back to default ssh identity",
        path,
        detail,
    )


def _ssh_key_usable(key_path) -> bool:
    """Return True only when *key_path* is confirmed readable.

    Fail-closed replacement for the inline ``Path(KEY).exists()`` gates:

    - missing key -> ``False``, quiet (matches the old behavior);
    - unreadable key, or any ``OSError`` while checking (e.g. EACCES on the
      key's parent directory) -> ``False`` plus a single WARNING per path.

    ``False`` means the caller builds its ssh/rsync command WITHOUT ``-i`` and
    ssh falls back to the default identity — never an unhandled
    ``PermissionError`` (#11793).
    """
    path = os.fspath(key_path)
    try:
        if not Path(path).exists():
            return False
        if os.access(path, os.R_OK):
            return True
    except OSError as exc:  # PermissionError included — EACCES on parent dir
        _warn_once(path, f"errno {exc.errno}: {exc.strerror or exc}")
        return False
    _warn_once(path, "exists but is not readable by the SLM process")
    return False
