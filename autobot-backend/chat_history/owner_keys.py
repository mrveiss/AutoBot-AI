# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The session-metadata keys that carry ownership: the one definition (#20928).

``ChatHistoryManager.get_session_owner`` reads the owner through ``OWNER_IDENTITY_KEYS``, and the
PUT /chat/sessions/{id} merge drops ``SERVER_CONTROLLED_METADATA_KEYS``, so the read and the strip
cannot drift apart.
"""

#: Metadata keys that name a session's owner, in the order ownership resolves them.
OWNER_IDENTITY_KEYS = ("owner", "username")

#: Metadata keys the server alone writes (``build_owner_metadata``) and ownership checks read.
#: A client-supplied metadata merge must never carry them.
SERVER_CONTROLLED_METADATA_KEYS = frozenset((*OWNER_IDENTITY_KEYS, "user_id", "org_id", "team_id"))


def owner_from_metadata(metadata):
    """The owner recorded in session *metadata*: the first of ``OWNER_IDENTITY_KEYS`` that is set.

    Returns the last key's value (possibly None or empty) when none is set, as the inline
    ``owner or username`` read did, so an empty recorded owner stays distinguishable from none.
    """
    owner = None
    for key in OWNER_IDENTITY_KEYS:
        owner = metadata.get(key)
        if owner:
            break
    return owner
