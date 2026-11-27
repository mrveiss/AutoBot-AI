# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The ``fact:`` Redis key families that are NOT fact hashes: one definition for writers and readers (#17530).

The fact hash itself is ``fact:<id>``. These other families share the ``fact:`` scan prefix; their writers
(``collections.py``, ``facts.py``, ``versioning.py``, ``selected_delete.py``) and the reader that must skip them
(``fact_stream.is_fact_key``) all import the prefixes from here, so a new family is added once.
"""

FACT_COLLECTIONS_PREFIX = "fact:collections:"  # set of collection ids per fact
FACT_ORIGIN_SESSION_PREFIX = "fact:origin:session:"  # string: the session that created a fact
FACT_VERSIONS_PREFIX = "fact:versions:"  # list of version snapshots
FACT_VERSION_META_PREFIX = "fact:version:meta:"  # hash of version metadata

NON_HASH_FACT_PREFIXES = (
    FACT_COLLECTIONS_PREFIX,
    FACT_ORIGIN_SESSION_PREFIX,
    FACT_VERSIONS_PREFIX,
    FACT_VERSION_META_PREFIX,
)

_RESERVED_ID_PREFIXES = tuple(prefix.removeprefix("fact:") for prefix in NON_HASH_FACT_PREFIXES)


def reserved_fact_id_error(fact_id: object) -> "dict | None":
    """An error result when a caller-supplied *fact_id* would key into a non-hash family, else ``None``.

    ``fact:<id>`` with an id starting ``collections:``, ``origin:session:``, ``versions:`` or ``version:meta:``
    IS another family's key. Any other colon id is a legitimate fact id.
    """
    if fact_id is not None and str(fact_id).startswith(_RESERVED_ID_PREFIXES):
        return {"status": "error", "message": "fact_id collides with a reserved fact: key family"}
    return None
