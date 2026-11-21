# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""When the previous user-backend process started, handed from the builtin updater to the new backend (#17421).

The updater writes this just before it restarts ``autobot-backend``; the plugin enable gate reads it on the
upgrade boot, when the database has no recorded start yet, to tell plugins that predate the last run from
plugins dropped in since. It is a heuristic input (file times can be forged), not a trust boundary.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from autobot_shared.ssot_config import config

#: The systemd unit the updater restarts; its ``ActiveEnterTimestamp`` is the old process's start.
BACKEND_UNIT = "autobot-backend"
_MARKER_NAME = "previous_backend_start"
_UNIX = re.compile(r"^@(\d+)$")


def marker_path() -> Path:
    return config.path.data_path / _MARKER_NAME


def parse_unix_timestamp(text: str) -> datetime | None:
    """``systemctl show --timestamp=unix`` prints ``@<seconds>``; empty or ``@0`` means never active."""
    match = _UNIX.match(text.strip())
    seconds = int(match.group(1)) if match else 0
    return datetime.fromtimestamp(seconds, tz=timezone.utc) if seconds else None


def write_marker(started_at: datetime) -> None:
    path = marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(started_at.astimezone(timezone.utc).isoformat(), encoding="utf-8")


def read_marker() -> datetime | None:
    """The recorded previous start, or None when absent or unreadable."""
    try:
        return datetime.fromisoformat(marker_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
