# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How a caller's messages combine with the file it is about to write (#20862).

A caller loads a session, changes the list and saves it whole. When another writer changed the
file in between, replacing it with that snapshot drops their change. After the writer holds the
session lease and has re-read the file, a snapshot is therefore *merged by message id*: a
message it carries updates the stored one, a message it does not have is added, and a stored
message the snapshot lacks is kept. A snapshot can add or update, never silently drop.

Dropping messages is a deliberate operation (``replace=True``: cleaning duplicates, replacing an
imported session), never a side effect of a stale snapshot. ``append=True`` adds new messages to
the file as it is, for the add-a-message routes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from chat_history.message_schema import message_role, message_text

Message = Dict[str, Any]
Key = Tuple[Any, ...]


def message_keys(messages: List[Message]) -> List[Key]:
    """One key per message: its id, else speaker, timestamp, body and which repeat of that it is.

    The repeat counter keeps two identical id-less messages (same body, same second) distinct, so a
    snapshot carrying both is not collapsed into one.
    """
    seen: Dict[Key, int] = {}
    keys: List[Key] = []
    for message in messages:
        stored_id = message.get("id") or message.get("messageId")
        if stored_id:
            keys.append(("id", str(stored_id)))
            continue
        base = ("text", message_role(message), str(message.get("timestamp", "")), message_text(message))
        seen[base] = seen.get(base, 0) + 1
        keys.append(base + (seen[base],))
    return keys


def _occurrence_keys(messages: List[Message]) -> List[Key]:
    """``message_keys`` made unique: a repeated id is told apart by which repeat of it a message is.

    Distinct messages that share an id (an import can carry them) each keep their own slot, so a snapshot
    carrying both updates both rather than overwriting the first with the second.
    """
    seen: Dict[Key, int] = {}
    keys: List[Key] = []
    for key in message_keys(messages):
        seen[key] = seen.get(key, 0) + 1
        keys.append(key + (seen[key],))
    return keys


def dropped_keys(existing: List[Message], kept: List[Message]) -> frozenset:
    """Keys of the *existing* messages absent from *kept*: what a caller's snapshot deliberately dropped."""
    kept_keys = set(_occurrence_keys(kept))
    return frozenset(k for k in _occurrence_keys(existing) if k not in kept_keys)


def merge_snapshot(on_disk: List[Message], supplied: List[Message], discard: frozenset = frozenset()) -> List[Message]:
    """*on_disk* with each *supplied* message updated in place, or inserted after its predecessor.

    One pass over each list: a supplied message the file lacks goes after the nearest preceding
    supplied message the file has (at the end when there is none). A stored message whose key is in
    *discard* (one the snapshot's author dropped on purpose) is left out; a message added to the file
    since the snapshot was taken is not in *discard* and stays.
    """
    disk_keys = _occurrence_keys(on_disk)
    supplied_keys = _occurrence_keys(supplied)
    on_disk_set = set(disk_keys)
    updates = dict(zip(supplied_keys, supplied, strict=True))
    after: Dict[Key, List[Message]] = {}
    tail: List[Message] = []
    predecessor: Key | None = None
    for key, message in zip(supplied_keys, supplied, strict=True):
        if key in on_disk_set:
            predecessor = key
        elif predecessor is None:
            tail.append(message)
        else:
            after.setdefault(predecessor, []).append(message)
    result: List[Message] = []
    for key, message in zip(disk_keys, on_disk, strict=True):
        if key not in discard:
            result.append(updates.get(key, message))
        result.extend(after.get(key, ()))
    return result + tail


def new_messages_only(on_disk: List[Message], supplied: List[Message]) -> List[Message]:
    """*supplied* minus messages whose id is already in the file or earlier in *supplied*.

    A retried append adds nothing twice, and a batch carrying one id twice adds it once.
    """
    seen = {k for k in message_keys(on_disk) if k[0] == "id"}
    fresh: List[Message] = []
    for message, key in zip(supplied, message_keys(supplied), strict=True):
        if key in seen:
            continue
        if key[0] == "id":
            seen.add(key)
        fresh.append(message)
    return fresh


def combine_messages(
    on_disk: List[Message],
    supplied: List[Message],
    *,
    append: bool,
    replace: bool,
    discard: frozenset | None = None,
) -> List[Message]:
    """The message list to write: replaced, appended to, or merged by id (the default)."""
    if replace:
        return supplied
    if append:
        return on_disk + new_messages_only(on_disk, supplied)
    return merge_snapshot(on_disk, supplied, discard or frozenset())
