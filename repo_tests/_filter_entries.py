# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Path-filter entries, read line by line and judged against a snapshot and the merge base (#21205).

The equivalence guard used to carry a per-PR table of allowed additions and a frozen digest of
each filter file, so two PRs that each widened a filter edited the same lines and conflicted.
The rules here need no table:

1. every entry of the pre-conversion snapshot is still in head, in order;
2. every head entry the snapshot lacks is DECLARED IN PLACE: its own line, or the contiguous
   comment block directly above its run of entries, cites an issue number;
3. no entry the merge base had is gone, unless the head file carries a tombstone comment
   ``# retired #NNNN: '<entry>'`` (the base is read fail-closed by ``_ratchet_base``);
4. the line-level reading agrees with ``yaml.safe_load`` (checked by :func:`agreed_entries`).

An entry is ``(key, value)``. A ``- *anchor`` line expands to the entries of the anchored key,
each keeping the line it was written on, so a citation sits where the entry is defined.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import yaml

CITATION = re.compile(r"#\d{4,}")
_KEY = re.compile(r"^([A-Za-z0-9_-]+):\s*(?:&(\w+))?\s*(?:#.*)?$")
_ENTRY = re.compile(r"^\s+-\s+(?:'((?:[^']|'')*)'|\"([^\"]*)\"|\*(\w+)|([^#'\"*\s][^#]*?))\s*(?:#(.*))?$")
_COMMENT = re.compile(r"^\s*#")
_TOMBSTONE = re.compile(r"#\s*retired\s+#\d{4,}:")


class Entry(NamedTuple):
    key: str
    value: str
    line: int  # index into the text's lines, where the entry is written


def _value(match: re.Match[str]) -> str | None:
    single, double, _alias, plain, _comment = match.groups()
    if single is not None:
        return single.replace("''", "'")
    return double if double is not None else plain


def parse_entries(text: str) -> list[Entry]:
    """Every ``- value`` under a top-level key, aliases expanded, in file order."""
    lines = text.split("\n")
    out: list[Entry] = []
    anchored: dict[str, str] = {}
    key = None
    for i, raw in enumerate(lines):
        if (m := _KEY.match(raw)) is not None:
            key = m.group(1)
            if m.group(2):
                anchored[m.group(2)] = key
            continue
        m = _ENTRY.match(raw)
        if m is None or key is None:
            continue
        if m.group(3) is not None:
            source = anchored[m.group(3)]
            out.extend([Entry(key, e.value, e.line) for e in out if e.key == source])
        else:
            out.append(Entry(key, _value(m), i))
    return out


def _flatten(items: list) -> list[str]:
    return [v for item in items for v in (_flatten(item) if isinstance(item, list) else [item])]


def doc_entries(doc: dict) -> list[tuple[str, str]]:
    """The entries of an already-parsed filter, nested alias lists flattened."""
    return [(k, v) for k, items in doc.items() for v in _flatten(items)]


def yaml_entries(text: str) -> list[tuple[str, str]]:
    return doc_entries(yaml.safe_load(text))


def agreed_entries(text: str) -> list[Entry]:
    """:func:`parse_entries`, asserted equal to what ``yaml.safe_load`` reads from the same text."""
    entries = parse_entries(text)
    assert [(e.key, e.value) for e in entries] == yaml_entries(text), "the line reader and yaml disagree"
    return entries


def is_cited(
    text: str, entry: Entry, old: frozenset[tuple[str, str]] = frozenset(), grandfathered: bool = False
) -> bool:
    """True if the entry's own line, or the comment block directly above its run, cites ``#NNNN``.

    The run's block covers an entry only if no entry above it in the same run is in ``old`` (the
    snapshot and the base): a block that cites the entries already there must not vouch for one
    appended to them. ``grandfathered`` entries (already at the base, judged when they landed) may
    still inherit their run's block.

    LIMIT: the check is FORMAT-ONLY. ``#\\d{4,}`` proves a number is written there, not that the
    issue exists or concerns this entry; an offline index of issues would need the network, which a
    guard must not use. A reviewer reads the citation.
    """
    lines = text.split("\n")
    own = _ENTRY.match(lines[entry.line])
    if own is not None and own.group(5) and CITATION.search(own.group(5)):
        return True
    top = entry.line
    while top > 0 and _ENTRY.match(lines[top - 1]):
        top -= 1
        before = _ENTRY.match(lines[top])
        value = _value(before) if before is not None else None
        if not grandfathered and (value is None or (entry.key, value) in old):
            return False
    block = []
    while top > 0 and _COMMENT.match(lines[top - 1]):
        top -= 1
        block.append(lines[top])
    return any(CITATION.search(c) for c in block if not _TOMBSTONE.search(c))


def split_against_snapshot(
    snapshot: list[tuple[str, str]], head: list[Entry]
) -> tuple[list[tuple[str, str]], list[Entry]]:
    """``(snapshot entries missing or out of order in head, head entries the snapshot lacks)``."""
    missing: list[tuple[str, str]] = []
    new: list[Entry] = []
    for key in dict.fromkeys([k for k, _ in snapshot] + [e.key for e in head]):
        want = [v for k, v in snapshot if k == key]
        at = 0
        for e in (e for e in head if e.key == key):
            if at < len(want) and e.value == want[at]:
                at += 1
            else:
                new.append(e)
        missing.extend((key, v) for v in want[at:])
    return missing, new


def uncited(text: str, snapshot: list[tuple[str, str]], base: str | None = None) -> list[str]:
    """Rule 1 and 2 findings for one filter text, as readable lines. ``base`` is the same file at the merge base."""
    head = agreed_entries(text)
    missing, new = split_against_snapshot(snapshot, head)
    at_base = {(e.key, e.value) for e in parse_entries(base)} if base else set()
    old = frozenset(snapshot) | frozenset(at_base)
    found = [f"{k}: snapshot entry {v!r} is gone or out of order" for k, v in missing]
    found += [
        f"{e.key}: {e.value!r} (line {e.line + 1}) cites no #NNNN of its own"
        for e in new
        if not is_cited(text, e, old, (e.key, e.value) in at_base)
    ]
    return found


def removed_without_tombstone(base: str | None, head: str, tombstones_in: str | None = None) -> list[str]:
    """Rule 3: entries the base had that head lacks, with no ``# retired #NNNN: '<entry>'`` tombstone."""
    if base is None:
        return []
    kept = {(e.key, e.value) for e in parse_entries(head)}
    found = []
    for e in parse_entries(base):
        if (e.key, e.value) in kept:
            continue
        pattern = rf"#\s*retired\s+#\d{{4,}}:\s*['\"]{re.escape(e.value)}['\"]"
        if not re.search(pattern, tombstones_in or head):
            found.append(f"{e.key}: {e.value!r} was at the base and is gone, with no retired tombstone")
    return found
