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
from datetime import datetime, timezone
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

# #13125: logrotate rotates /var/log/autobot/*.log daily with ``copytruncate``
# (roles/common/templates/autobot-logrotate.j2) — mandatory for the append: units
# that hold their fd open. It copies the file aside and truncates the original to
# zero bytes, so from the 01:00 rotation until the next self-update runs, the
# live log EXISTS and is EMPTY.
#
# The reader distinguished missing from present but not present-but-empty, so an
# empty log reached the parse path, found zero play headers, and produced "the
# run was cut short; later plays did not execute" — on a deployment whose last
# self-update finished normally. For most of every day, on every node. It was
# discounted as noise once before the cause was found, which is the real damage:
# a detector that cries wolf daily teaches everyone to ignore that whole class of
# alert.
#
# Suppressing to "nothing to say" would fix the false positive and lose a true
# one — the last run's actual verdict is sitting in the rotation, and going
# silent all day is its own gap. So the rotation is read instead.
#
# That fallback is only SAFE because a started run stamps the log with
# ``SELF_UPDATE_RUN_HEADER`` (playbook_executor._write_fresh_log_file). The
# executor also truncates this file per run, so without the stamp "empty" would
# have two causes — rotation, and a run that started and emitted nothing (a
# systemd-run exec failure, or output diverted to the #12425 fallback path) —
# and reading the rotation would report the PREVIOUS run's clean verdict over a
# live failure. With the stamp, an empty live log means only "no run since the
# rotation", and a header-only log is a started run with no plays: degraded, as
# it should be.
#
# ``.1`` only: the stanza sets ``delaycompress``, so the most recent rotation is
# always the uncompressed ``.1`` (each cycle compresses the previous ``.1`` to
# ``.2.gz``). ``notifempty`` is load-bearing here too — it stops logrotate
# rotating an already-empty live log, so ``.1`` keeps holding the last real run
# instead of ageing into ``.2.gz`` on an idle node. That also means ``.1`` can be
# far older than a day, which is why the reason carries its mtime rather than
# implying "yesterday".
_ROTATED_SUFFIX = ".1"

# Kept in step with services.playbook_executor.SELF_UPDATE_RUN_HEADER. Not
# imported from it: that module pulls in ansible/inventory machinery this reader
# has no business loading on the status path, and the value is a log format both
# sides agree on. The pairing is pinned by a test.
_RUN_HEADER = "SELF-UPDATE RUN STARTED"


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
    #: #13125: the verdict was parsed from the rotated log because the live one
    #: had been truncated to zero bytes by logrotate. The verdict is real but
    #: describes a run from before the last rotation, so the reason says so.
    from_rotated_log: bool = False
    #: When that rotation was last written (ISO-8601 UTC). ``notifempty`` means
    #: an idle node's rotation is never superseded, so it can be far older than
    #: a day — the reason states the date instead of implying "yesterday".
    rotated_log_mtime: str | None = None

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


@dataclass
class _LogSource:
    """Which log the verdict came from, and whether it could be read at all."""

    text: str | None = None
    from_rotated: bool = False
    rotated_age: str | None = None
    unreadable: bool = False


def _rotated_path(log_path: Path) -> Path:
    return log_path.with_name(log_path.name + _ROTATED_SUFFIX)


def _read_log_text(log_path: Path) -> _LogSource:
    """Return the newest log that actually describes a run.

    Prefers the live log. When logrotate's ``copytruncate`` has emptied it
    (#13125) the most recent rotation is read instead, so the verdict keeps
    describing the last real run rather than going blank until the next one.

    ``text=None`` with ``unreadable=False`` is the genuine "nothing to say" case,
    which is NOT a failure (see :attr:`SelfUpdateVerdict.degraded`).
    """
    if log_path.exists():
        text = _read_tail(log_path)
        if text is None:
            # A log that is a directory, or one this process cannot read, is a
            # broken deployment — reported as its own thing rather than folded
            # into "no log yet", which would look like a fresh box.
            return _LogSource(unreadable=True)
        if text.strip():
            return _LogSource(text=text)

    rotated = _rotated_path(log_path)
    rotated_text = _read_tail(rotated) if rotated.exists() else None
    if rotated_text and rotated_text.strip():
        logger.info(
            "self-update log %s is empty (logrotate copytruncate) — reading %s instead (#13125)",
            log_path,
            rotated,
        )
        return _LogSource(text=rotated_text, from_rotated=True, rotated_age=_mtime_iso(rotated))

    return _LogSource()


def _mtime_iso(path: Path) -> str | None:
    """UTC mtime of *path* as an ISO-8601 string, or None if unavailable.

    The rotation can be far older than a day (``notifempty`` skips an idle
    node's empty log), so the verdict states when it is from rather than letting
    "rotated away" imply yesterday.
    """
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def read_self_update_verdict(log_path: Path) -> SelfUpdateVerdict:
    """Parse *log_path* and report whether the last self-update run completed.

    Never raises: a status endpoint must not fail because a log is missing or
    malformed. A log that is missing, or empty on both the live and rotated
    paths, yields ``log_present=False``, which is treated as "nothing to say"
    rather than as a failure.
    """
    source = _read_log_text(log_path)
    if source.unreadable:
        # Path-free on purpose: this string reaches an API response, and an
        # internal filesystem path does not belong in one.
        return SelfUpdateVerdict(reason="self-update log unreadable")
    if source.text is None:
        # #13125: an empty live log with no usable rotation is the same
        # situation as no log at all — a box that has nothing to report. It was
        # previously parsed as zero plays and reported as a run cut short.
        return SelfUpdateVerdict(reason="no self-update log yet")

    text = source.text
    from_rotated = source.from_rotated
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
        from_rotated_log=from_rotated,
        rotated_log_mtime=source.rotated_age,
    )
    verdict.reason = _describe(verdict)
    if verdict.degraded:
        logger.error("self-update verdict: %s", verdict.reason)
    return verdict


def _describe(v: SelfUpdateVerdict) -> str:
    """Human-readable reason, naming what is missing rather than just 'failed'.

    #13125: when the verdict came from the rotated log it is qualified as such.
    An operator reading "completed, no failures" needs to know it describes the
    run before the last rotation, not one since.
    """
    if not v.from_rotated_log:
        suffix = ""
    elif v.rotated_log_mtime:
        suffix = f" (from the log rotated at {v.rotated_log_mtime}; no self-update has run since)"
    else:
        suffix = " (from the rotated log; no self-update has run since)"
    if not v.complete:
        seen = ", ".join(v.plays_seen) if v.plays_seen else "none"
        return (
            f"self-update run did not finish — no PLAY RECAP in the log "
            f"(plays started: {seen}). The run was cut short; later plays did not execute.{suffix}"
        )
    if v.unreachable_hosts:
        return f"self-update finished with {v.unreachable_hosts} unreachable host(s){suffix}"
    if v.failed_hosts:
        return f"self-update finished with {v.failed_hosts} failed task(s){suffix}"
    return f"self-update completed ({len(v.plays_seen)} plays, no failures){suffix}"


__all__ = ["SelfUpdateVerdict", "read_self_update_verdict", "MAX_LOG_BYTES"]
