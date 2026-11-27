# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Package and command inventory of this node for the heartbeat (#22277).

Every heartbeat carries ``inventory_hash``; the full ``inventory`` rides along only when the hash
changed since the last report, plus once every ``INVENTORY_RESEND_S`` as a backstop for a lost
report. The scan is cheap: it is repeated only when the mtime signature of the package database
and of the ``PATH`` directories changed (a handful of ``stat`` calls), plus once every
``INVENTORY_RESCAN_S`` because a permission change moves a file's ctime and no directory mtime. A scan that
fails keeps the last good snapshot and its old signature, so the next heartbeat retries it.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.self_model_constants import INVENTORY_RESCAN_S, INVENTORY_RESEND_S

logger = get_logger(__name__)

DPKG_STATUS_PATH = "/var/lib/dpkg/status"
_ABSENT_OR_DENIED = (FileNotFoundError, NotADirectoryError, PermissionError)


def _path_dirs() -> List[str]:
    return [d for d in os.environ.get("PATH", "").split(os.pathsep) if d and os.path.isdir(d)]


def signature() -> Tuple[Tuple[str, int], ...]:
    """``(path, mtime_ns)`` of the package database and every ``PATH`` directory; changes when either does."""
    paths = [DPKG_STATUS_PATH, *_path_dirs()]
    out = []
    for path in paths:
        try:
            out.append((path, os.stat(path).st_mtime_ns))
        except OSError:
            continue
    return tuple(out)


def scan_commands() -> List[str]:
    """Sorted names of the executable files on ``PATH``.

    An entry that cannot be examined (a symlink loop, an over-long name) is skipped on its own; only a
    directory that cannot be opened at all is a scan failure, and a missing or denied one is skipped.
    """
    names = set()
    for directory in _path_dirs():
        try:
            with os.scandir(directory) as entries:
                names.update(e.name for e in entries if _is_executable(e))
        except _ABSENT_OR_DENIED as exc:  # stable across rescans: skipping it is the honest answer
            logger.warning("inventory: cannot scan %s: %s", directory, exc)
    return sorted(names)


def _is_executable(entry: "os.DirEntry[str]") -> bool:
    """Whether *entry* is an executable file; an entry the OS cannot examine (ELOOP, ENAMETOOLONG) is not."""
    try:
        return entry.is_file() and os.access(entry.path, os.X_OK)
    except OSError as exc:
        logger.debug("inventory: skipping %s: %s", entry.path, exc)
        return False


def _parse_dpkg(text: str) -> Dict[str, str]:
    """``package -> version`` of the installed entries of a dpkg status file."""
    packages: Dict[str, str] = {}
    for block in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and line[0] != " ")
        if fields.get("Status", "").endswith(" installed") and "Package" in fields:
            packages[fields["Package"]] = fields.get("Version", "")
    return packages


def scan_packages() -> Dict[str, str]:
    """Installed packages of a dpkg-based node; empty where there is no dpkg database.

    Only a missing database is "no packages"; an unreadable one raises ``OSError`` so the caller keeps its snapshot.
    """
    try:
        with open(DPKG_STATUS_PATH, encoding="utf-8", errors="replace") as handle:
            return _parse_dpkg(handle.read())
    except FileNotFoundError:
        return {}


def inventory_hash(inventory: Dict[str, Any]) -> str:
    """Stable digest of an inventory."""
    return hashlib.sha256(json.dumps(inventory, sort_keys=True).encode("utf-8")).hexdigest()


class InventoryReporter:
    """Decides, per heartbeat, whether the full inventory rides along (hash change or backstop)."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._scanned_mtimes: Optional[Tuple[Tuple[str, int], ...]] = None
        self._scanned_at = 0.0
        self._inventory: Dict[str, Any] = {}
        self._hash: Optional[str] = None
        self._sent_hash: Optional[str] = None
        self._sent_at = 0.0

    def _refresh(self) -> None:
        current, now = signature(), self._clock()
        if current == self._scanned_mtimes and now - self._scanned_at < INVENTORY_RESCAN_S:
            return
        try:
            inventory = {"packages": scan_packages(), "commands": scan_commands()}
        except OSError as exc:
            logger.warning("inventory: scan failed, keeping the last snapshot and retrying: %s", exc)
            return
        self._inventory, self._hash = inventory, inventory_hash(inventory)
        self._scanned_mtimes, self._scanned_at = current, now

    def report(self) -> Dict[str, Any]:
        """The heartbeat ``extra_data`` fragment: always the hash, the full inventory when due."""
        self._refresh()
        if self._hash is None:  # no scan has ever succeeded: nothing true to report yet
            return {}
        now = self._clock()
        due = self._hash != self._sent_hash or now - self._sent_at >= INVENTORY_RESEND_S
        if not due:
            return {"inventory_hash": self._hash}
        return {"inventory_hash": self._hash, "inventory": self._inventory}

    def confirm(self, extra: Dict[str, Any], delivered: bool, acknowledged: Optional[str] = None) -> bool:
        """Record a full report as sent only once the SLM acknowledged both the heartbeat and the inventory.

        *acknowledged* is the hash the SLM says it folded into the model. A lost report, or one the SLM
        accepted as liveness but failed to persist, leaves ``_sent_hash`` behind, so the next heartbeat
        carries the full list again instead of waiting for the backstop while the node's entities go stale.
        Returns *delivered*.
        """
        if delivered and "inventory" in extra and acknowledged == extra["inventory_hash"]:
            self._sent_hash, self._sent_at = extra["inventory_hash"], self._clock()
        return delivered


_reporter: Optional[InventoryReporter] = None


def get_inventory_reporter() -> InventoryReporter:
    """The process's reporter (one agent per process, so its sent-hash state is process state)."""
    global _reporter
    if _reporter is None:
        _reporter = InventoryReporter()
    return _reporter
