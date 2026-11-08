# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The session-metadata keys that carry ownership: the one definition (#20928).

``ChatHistoryManager.get_session_owner`` and the memory-graph owner scope read the owner through
the key tuples here, and every route that stores client-supplied session metadata (POST and PUT
/chat/sessions) passes it through ``strip_server_controlled`` first, so the reads and the strip
cannot drift apart.
"""

#: Metadata keys that name a session's owner, in the order ownership resolves them.
OWNER_IDENTITY_KEYS = ("owner", "username")

#: Metadata keys that name a session's memory-graph owner, in resolution order. ``user_id`` comes
#: first because POST /chat/sessions writes the session's graph entity under the principal's
#: ``user_id`` (falling back to the username), and ``build_owner_metadata`` stamps ``user_id``
#: whenever the principal has one, else ``owner`` = ``username``. So for every server-built
#: session this resolves to the same identity the entity was written under.
GRAPH_OWNER_KEYS = ("user_id", *OWNER_IDENTITY_KEYS)

#: Metadata keys the server alone writes (``build_owner_metadata``) and ownership checks read.
#: Client-supplied metadata must never carry them.
SERVER_CONTROLLED_METADATA_KEYS = frozenset((*GRAPH_OWNER_KEYS, "org_id", "team_id"))


def _first_set(metadata, keys):
    """The value of the first of *keys* set in *metadata*, else the last key's value."""
    value = None
    for key in keys:
        value = metadata.get(key)
        if value:
            break
    return value


def owner_from_metadata(metadata):
    """The owner recorded in session *metadata*: the first of ``OWNER_IDENTITY_KEYS`` that is set.

    Returns the last key's value (possibly None or empty) when none is set, as the inline
    ``owner or username`` read did, so an empty recorded owner stays distinguishable from none.
    """
    return _first_set(metadata, OWNER_IDENTITY_KEYS)


def graph_owner_from_metadata(metadata):
    """The memory-graph owner identity in session *metadata*: the first of ``GRAPH_OWNER_KEYS`` set."""
    return _first_set(metadata, GRAPH_OWNER_KEYS)


def strip_server_controlled(metadata) -> dict:
    """A copy of client *metadata* without ``SERVER_CONTROLLED_METADATA_KEYS`` (None reads as empty).

    Client metadata can't set server-controlled ownership keys; the server adds its own after this.
    """
    return {k: v for k, v in (metadata or {}).items() if k not in SERVER_CONTROLLED_METADATA_KEYS}
