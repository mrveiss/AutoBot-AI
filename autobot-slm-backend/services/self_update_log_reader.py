# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Post-hoc completion verdict for the last self-update run (#12776).

``SELF_UPDATE_LOG_PATH`` was write-only: the executor wrote it and nothing ever
read it back. That is precisely why #12596 stayed invisible across two fix
attempts — the detached run died at the end of Play 1, Plays 2/3 never executed,
and the SLM still reported a successful update. The evidence needed to catch it
was sitting in a log nobody parsed.

A post-hoc reader is structurally required rather than an in-process assertion:
on the self-update path this backend is **restarted mid-run by design**, so the
process that launched the playbook is gone before the playbook finishes.
Completion can only be judged after the fact, on a later start.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Ansible emits "PLAY [name] ****" per play and one "PLAY RECAP" at the end.
# A run that produced no RECAP did not finish, whatever else it logged.
_PLAY_HEADER = re.compile(r"^PLAY \[(?P<name>[^\]]*)\]", re.MULTILINE)
_PLAY_RECAP = re.compile(r"^PLAY RECAP", re.MULTILINE)
# RECAP lines look like: host : ok=12 changed=3 unreachable=0 failed=0 skipped=1
_RECAP_COUNTS = re.compile(r"\b(?P<key>failed|unreachable)=(?P<count>\d+)")

# Read a bounded tail: these logs can be large, and everything the verdict needs
# (play headers and the recap) is cheap to find without holding the whole file.
MAX_LOG_BYTES = 512 * 1024


@dataclass
class SelfUpdateVerdict:
    """What the last self-update run actually did."""

    log_present: bool = False
    complete: bool = False
    plays_seen: list[str] = field(default_factory=list)
    failed_hosts: int = 0
    unreachable_hosts: int = 0
    reason: str | None = None
    #: #12959: set when a role-owned change is verifiably absent from this host.
    #: Independent of the log — a run can reach its recap cleanly and still
    #: deliver nothing, because the updater applies almost none of the roles.
    role_delivery_incomplete: bool = False

    @property
    def degraded(self) -> bool:
        """True when the run cannot be treated as a successful update.

        A missing log is NOT degraded: a box that has never self-updated has
        nothing to report, and flagging that would cry wolf on every fresh
        install. Undelivered role-owned changes ARE degraded regardless of the
        log, since that is the failure the log cannot see (#12959).
        """
        if self.role_delivery_incomplete:
            return True
        if not self.log_present:
            return False
        return not self.complete or self.failed_hosts > 0 or self.unreachable_hosts > 0


def _read_tail(path: Path, max_bytes: int = MAX_LOG_BYTES) -> str | None:
    """Return the last *max_bytes* of *path*, or None when it cannot be read."""
    try:
        size = path.stat().st_size
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # discard the partial line the seek landed in
            return fh.read()
    except (OSError, ValueError) as exc:
        logger.warning("self-update log unreadable at %s: %s", path, exc)
        return None


def read_self_update_verdict(log_path: Path) -> SelfUpdateVerdict:
    """Parse *log_path* and report whether the last self-update run completed.

    Never raises: a status endpoint must not fail because a log is missing or
    malformed. An unreadable log yields ``log_present=False``, which is treated
    as "nothing to say" rather than as a failure.
    """
    if not log_path.exists():
        return SelfUpdateVerdict(reason="no self-update log yet")

    text = _read_tail(log_path)
    if text is None:
        return SelfUpdateVerdict(reason=f"self-update log unreadable: {log_path}")

    plays = _PLAY_HEADER.findall(text)
    has_recap = bool(_PLAY_RECAP.search(text))

    failed = unreachable = 0
    if has_recap:
        recap = text[text.rindex("PLAY RECAP") :]
        for m in _RECAP_COUNTS.finditer(recap):
            if m.group("key") == "failed":
                failed += int(m.group("count"))
            else:
                unreachable += int(m.group("count"))

    verdict = SelfUpdateVerdict(
        log_present=True,
        complete=has_recap,
        plays_seen=plays,
        failed_hosts=failed,
        unreachable_hosts=unreachable,
    )
    verdict.reason = _describe(verdict)
    if verdict.degraded:
        logger.error("self-update verdict: %s", verdict.reason)
    return verdict


def _describe(v: SelfUpdateVerdict) -> str:
    """Human-readable reason, naming what is missing rather than just 'failed'."""
    if not v.complete:
        seen = ", ".join(v.plays_seen) if v.plays_seen else "none"
        return (
            f"self-update run did not finish — no PLAY RECAP in the log "
            f"(plays started: {seen}). The run was cut short; later plays did not execute."
        )
    if v.unreachable_hosts:
        return f"self-update finished with {v.unreachable_hosts} unreachable host(s)"
    if v.failed_hosts:
        return f"self-update finished with {v.failed_hosts} failed task(s)"
    return f"self-update completed ({len(v.plays_seen)} plays, no failures)"


__all__ = ["SelfUpdateVerdict", "read_self_update_verdict", "MAX_LOG_BYTES"]
