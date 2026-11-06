# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Merge a caller's message snapshot onto the file it is about to replace (#20862).

A caller loads a session, changes the list and saves it whole. When another writer appended in
between, replacing the file with that snapshot drops the append. After the writer holds the
session lease and has re-read the file, messages that sit on disk *after* the last message the
snapshot shares with it are concurrent appends and are kept. A snapshot sharing no message with
a non-empty file is a deliberate replacement and is written as it is.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from chat_history.message_schema import message_role, message_text


def message_key(message: Dict[str, Any]) -> Tuple[str, str, str]:
    """Identity of a message that survives metadata edits: speaker, timestamp and body."""
    return (message_role(message), str(message.get("timestamp", "")), message_text(message))


def merge_concurrent_tail(on_disk: List[Dict[str, Any]], supplied: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """*supplied* plus any messages appended to *on_disk* after the last one both share."""
    supplied_keys = {message_key(m) for m in supplied}
    last_shared = max((i for i, m in enumerate(on_disk) if message_key(m) in supplied_keys), default=-1)
    if last_shared < 0:
        return supplied
    return supplied + [m for m in on_disk[last_shared + 1 :] if message_key(m) not in supplied_keys]
