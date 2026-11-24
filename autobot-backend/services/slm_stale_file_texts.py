# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The approval text for a stale code-sync file proposal: one line per file, as the inbox renders it (#22033, D1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping

_UNITS = ("B", "KiB", "MiB", "GiB")


def human_size(size: int) -> str:
    """*size* in bytes as ``1.5 KiB``."""
    value = float(size)
    for unit in _UNITS[:-1]:
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {_UNITS[-1]}"


def age_days(modified_at: datetime, now: datetime) -> int:
    """Whole days between *modified_at* and *now*, never negative."""
    stamp = modified_at if modified_at.tzinfo else modified_at.replace(tzinfo=timezone.utc)
    return max(0, (now - stamp).days)


def file_line(old_target: str, entry: Mapping[str, object], now: datetime) -> str:
    """``<old target>/<path>  <size>  <age> days old`` for one file."""
    modified = entry["modified_at"]
    modified = modified if isinstance(modified, datetime) else datetime.fromisoformat(str(modified))
    return (
        f"{old_target.rstrip('/')}/{entry['path']}  {human_size(int(entry['size_bytes']))}  "
        f"{age_days(modified, now)} days old (modified {modified:%Y-%m-%d})"
    )


def proposal_text(
    node_id: str, old_target: str, files: Iterable[Mapping[str, object]], total_found: int, now: datetime | None = None
) -> tuple[str, str]:
    """The approval's title and description: the header, then every listed file on its own line."""
    now = now or datetime.now(timezone.utc)
    lines = [file_line(old_target, entry, now) for entry in files]
    more = total_found - len(lines)
    header = (
        f"Node {node_id} still holds {total_found} file(s) the code-sync left in {old_target} before each "
        f"role got its own directory. Each is byte-identical to a version git tracked at that path; any file "
        f"changed on the node is kept and not listed. Approving removes exactly the {len(lines)} file(s) below "
        f"that are still unchanged; rejecting changes nothing."
    )
    if more > 0:
        header += f" {more} more are proposed after this one is decided."
    return f"Remove stale code-sync files from {old_target} on node {node_id}", "\n".join([header, "", *lines])
