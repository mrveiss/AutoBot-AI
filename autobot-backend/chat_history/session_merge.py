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

from typing import Any, Dict, Hashable, List

from chat_history.message_schema import message_role, message_text

Message = Dict[str, Any]


def message_key(message: Message) -> Hashable:
    """Stable identity of a message: its id, else speaker, timestamp and body (survives metadata edits)."""
    stored_id = message.get("id") or message.get("messageId")
    if stored_id:
        return ("id", str(stored_id))
    return ("text", message_role(message), str(message.get("timestamp", "")), message_text(message))


def merge_snapshot(on_disk: List[Message], supplied: List[Message]) -> List[Message]:
    """*on_disk* with every *supplied* message updated in place or inserted after its predecessor."""
    result = list(on_disk)
    anchor = -1
    for message in supplied:
        positions = {message_key(m): i for i, m in enumerate(result)}
        index = positions.get(message_key(message))
        if index is None:
            index = anchor + 1 if anchor >= 0 else len(result)
            result.insert(index, message)
        else:
            result[index] = message
        anchor = index
    return result


def combine_messages(on_disk: List[Message], supplied: List[Message], *, append: bool, replace: bool) -> List[Message]:
    """The message list to write: replaced, appended to, or merged by id (the default)."""
    if replace:
        return supplied
    if append:
        return on_disk + supplied
    return merge_snapshot(on_disk, supplied)
