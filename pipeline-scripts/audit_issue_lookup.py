#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``gh`` lookups behind ``audit_unwired_trackers``: the closed-tracker set and the audit-issue dedup keys.

Every lookup raises ``TrackerLookupError`` on failure or truncation, so "could not look" never reads
as "found nothing" (#21582).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Optional


class TrackerLookupError(RuntimeError):
    """A ``gh`` lookup failed, was unreadable or was truncated (#21582).

    An empty closed set makes ``scan`` skip every file (state != CLOSED), so a failed lookup would
    render as a clean audit. "Could not look" must not read as "found nothing".
    """


#: ``gh issue list --limit`` for closed issues. A result of exactly this size may be truncated, so it fails.
CLOSED_ISSUE_LIMIT = 10000
_CLOSED_ISSUES_CMD = [
    *("gh", "issue", "list", "--state", "closed", "--limit", str(CLOSED_ISSUE_LIMIT), "--json", "number"),
]
#: ``--limit`` for each audit-issue listing (open and closed); a result of exactly this size fails.
OPEN_AUDIT_ISSUE_LIMIT = 1000
# Unquoted, GitHub search drops the parentheses and matches nothing; quote the phrase and scope it to the title.
_AUDIT_QUERY = '"discovery(unwired-tracker)" in:title'


def _audit_cmd(state: str, fields: str) -> list[str]:
    return [
        *("gh", "issue", "list", "--state", state, "--search", _AUDIT_QUERY),
        *("--limit", str(OPEN_AUDIT_ISSUE_LIMIT), "--json", fields),
    ]


_OPEN_AUDIT_CMD = _audit_cmd("open", "number,title,body")
_CLOSED_AUDIT_CMD = _audit_cmd("closed", "number,title,body,stateReason,comments")


def _gh_json(cmd: list[str], timeout: int, what: str) -> list[dict]:
    """Run a ``gh ... --json`` listing; raise ``TrackerLookupError`` unless it yields a JSON list of objects."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True).stdout
        data = json.loads(out)
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError) as e:
        raise TrackerLookupError(f"{what} failed or was unreadable ({e!r})") from e
    if not isinstance(data, list) or not all(isinstance(i, dict) for i in data):
        raise TrackerLookupError(f"{what} was not a list of objects")
    return data


def fetch_closed_tracker_set() -> set[int]:
    """One-shot fetch of all CLOSED issues so per-finding lookups are O(1).

    Raises ``TrackerLookupError`` when ``gh`` fails, its output is unusable, or it hit the limit.
    """
    data = _gh_json(_CLOSED_ISSUES_CMD, 120, "closed issue list")
    if len(data) >= CLOSED_ISSUE_LIMIT:
        raise TrackerLookupError(f"closed issue list hit its {CLOSED_ISSUE_LIMIT}-issue limit; older trackers unseen")
    try:
        return {item["number"] for item in data}
    except KeyError as e:
        raise TrackerLookupError(f"closed issue list item without a number ({e!r})") from e


_TRACKER_RE = re.compile(r"tracker #(\d+) closed prematurely")
_TITLE_STEM_RE = re.compile(r"wire in (\S+) \(tracker #")
_BODY_PATH_RE = re.compile(r"\[`([^`]+)`\]\(")
# A real deferral note is a heading line; the issue template only mentions it inline in backticks.
_DEFERRAL_RE = re.compile(r"^#{1,6}\s*Wire-in deferred\s*$", re.MULTILINE)


def _audit_issue_key(item: dict) -> Optional[tuple[str, int]]:
    """``(module, tracker)`` of one audit issue; the module is the body's path link, else the title stem."""
    title = item.get("title") or ""
    if not (m := _TRACKER_RE.search(title)):
        return None
    found = _BODY_PATH_RE.search(item.get("body") or "") or _TITLE_STEM_RE.search(title)
    return (found.group(1) if found else ""), int(m.group(1))


def _is_deliberate_deferral(item: dict) -> bool:
    """True for a closed issue the owner dismissed: closed NOT_PLANNED, or carrying a ``### Wire-in deferred`` note."""
    if item.get("stateReason") == "NOT_PLANNED":
        return True
    texts = [item.get("body") or "", *((c or {}).get("body") or "" for c in item.get("comments") or [])]
    return any(_DEFERRAL_RE.search(t) for t in texts)


def _listed(state: str, cmd: list[str]) -> list[dict]:
    data = _gh_json(cmd, 60, f"{state} audit issue list")
    if len(data) >= OPEN_AUDIT_ISSUE_LIMIT:
        raise TrackerLookupError(f"{state} audit issue list hit its {OPEN_AUDIT_ISSUE_LIMIT}-issue limit; some unseen")
    return data


def existing_audit_issue_keys() -> set[tuple[str, int]]:
    """``(module, tracker)`` per audit issue that must not be re-filed (#22199).

    Open issues count, so do closed ones dismissed as NOT_PLANNED or carrying a deferral note. A closed
    COMPLETED issue without a note does not: its module is still unwired, which is a regression, so
    the audit files it again. Keyed per module so modules sharing a tracker do not shadow each other.
    """
    keys = {k for k in map(_audit_issue_key, _listed("open", _OPEN_AUDIT_CMD)) if k}
    for item in _listed("closed", _CLOSED_AUDIT_CMD):
        if _is_deliberate_deferral(item) and (k := _audit_issue_key(item)):
            keys.add(k)
    return keys


def already_filed(file: str, tracker: int, filed: set[tuple[str, int]]) -> bool:
    """True when an issue covers this module+tracker (by path, or by stem for a body-less issue)."""
    return (file, tracker) in filed or (Path(file).stem, tracker) in filed
