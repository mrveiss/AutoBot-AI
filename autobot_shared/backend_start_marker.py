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
#: No AutoBot backend started before this; an earlier marker is corrupt or forged.
MARKER_FLOOR = datetime(2024, 1, 1, tzinfo=timezone.utc)
_UNIX = re.compile(r"^@(\d+)$")


def marker_path(data_dir: Path | None = None) -> Path:
    """The marker file in *data_dir*; the backend's own data directory when none is given.

    The reader (the backend) uses its own ``AUTOBOT_DATA_DIR``. The writer (the SLM updater) runs with a
    different environment and passes the backend's data directory explicitly (``SLM_BACKEND_DATA_DIR``).
    """
    return (data_dir if data_dir is not None else config.path.data_path) / _MARKER_NAME


def parse_unix_timestamp(text: str) -> datetime | None:
    """``systemctl show --timestamp=unix`` prints ``@<seconds>``; empty or ``@0`` means never active."""
    match = _UNIX.match(text.strip())
    seconds = int(match.group(1)) if match else 0
    return datetime.fromtimestamp(seconds, tz=timezone.utc) if seconds else None


def write_marker(started_at: datetime, data_dir: Path | None = None) -> None:
    path = marker_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(started_at.astimezone(timezone.utc).isoformat(), encoding="utf-8")


def read_marker() -> datetime | None:
    """The recorded previous start, or None when absent, unreadable, forged or implausible.

    A value in the future (forged or a skewed clock) or before ``MARKER_FLOOR`` is rejected, so a bad
    marker can only make the gate grandfather less, never more. A naive value is read as UTC.
    """
    try:
        value = datetime.fromisoformat(marker_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return value if MARKER_FLOOR <= value <= datetime.now(timezone.utc) else None
