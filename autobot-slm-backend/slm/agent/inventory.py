# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Package and command inventory of this node for the heartbeat (#22277).

Every heartbeat carries ``inventory_hash``; the full ``inventory`` rides along only when the hash
changed since the last report, plus once every ``INVENTORY_RESEND_S`` as a backstop for a lost
report. The scan is cheap: it is repeated only when the mtime signature of the package database
and of the ``PATH`` directories changed, so an unchanged node costs a handful of ``stat`` calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.self_model_constants import INVENTORY_RESEND_S

logger = get_logger(__name__)

DPKG_STATUS_PATH = "/var/lib/dpkg/status"


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
    """Sorted names of the executable files on ``PATH``."""
    names = set()
    for directory in _path_dirs():
        try:
            with os.scandir(directory) as entries:
                names.update(e.name for e in entries if e.is_file() and os.access(e.path, os.X_OK))
        except OSError as exc:
            logger.warning("inventory: cannot scan %s: %s", directory, exc)
    return sorted(names)


def _parse_dpkg(text: str) -> Dict[str, str]:
    """``package -> version`` of the installed entries of a dpkg status file."""
    packages: Dict[str, str] = {}
    for block in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and line[0] != " ")
        if fields.get("Status", "").endswith(" installed") and "Package" in fields:
            packages[fields["Package"]] = fields.get("Version", "")
    return packages


def scan_packages() -> Dict[str, str]:
    """Installed packages of a dpkg-based node; empty where there is no dpkg database."""
    try:
        with open(DPKG_STATUS_PATH, encoding="utf-8", errors="replace") as handle:
            return _parse_dpkg(handle.read())
    except OSError:
        return {}


def inventory_hash(inventory: Dict[str, Any]) -> str:
    """Stable digest of an inventory."""
    return hashlib.sha256(json.dumps(inventory, sort_keys=True).encode("utf-8")).hexdigest()


class InventoryReporter:
    """Decides, per heartbeat, whether the full inventory rides along (hash change or backstop)."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._scanned_mtimes: Optional[Tuple[Tuple[str, int], ...]] = None
        self._inventory: Dict[str, Any] = {}
        self._hash: Optional[str] = None
        self._sent_hash: Optional[str] = None
        self._sent_at = 0.0

    def _refresh(self) -> None:
        current = signature()
        if current == self._scanned_mtimes:
            return
        self._scanned_mtimes = current
        self._inventory = {"packages": scan_packages(), "commands": scan_commands()}
        self._hash = inventory_hash(self._inventory)

    def report(self) -> Dict[str, Any]:
        """The heartbeat ``extra_data`` fragment: always the hash, the full inventory when due."""
        self._refresh()
        now = self._clock()
        due = self._hash != self._sent_hash or now - self._sent_at >= INVENTORY_RESEND_S
        if not due:
            return {"inventory_hash": self._hash}
        return {"inventory_hash": self._hash, "inventory": self._inventory}

    def confirm(self, extra: Dict[str, Any], delivered: bool) -> bool:
        """Record a full report as sent only once the SLM acknowledged the heartbeat that carried it.

        A lost report leaves ``_sent_hash`` behind, so the next heartbeat carries the full list again
        instead of waiting for the backstop while the node's entities go stale. Returns *delivered*.
        """
        if delivered and "inventory" in extra:
            self._sent_hash, self._sent_at = extra["inventory_hash"], self._clock()
        return delivered


_reporter: Optional[InventoryReporter] = None


def get_inventory_reporter() -> InventoryReporter:
    """The process's reporter (one agent per process, so its sent-hash state is process state)."""
    global _reporter
    if _reporter is None:
        _reporter = InventoryReporter()
    return _reporter
