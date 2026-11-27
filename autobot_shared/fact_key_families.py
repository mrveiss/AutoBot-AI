# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The ``fact:`` Redis key families that are NOT fact hashes: one definition for writers and readers (#17530).

The fact hash itself is ``fact:<id>``. These other families share the ``fact:`` scan prefix; their writers
(``collections.py``, ``facts.py``, ``versioning.py``, ``selected_delete.py``) and the readers that must skip them
(the backend's ``fact_stream`` and the infrastructure scripts) all import from here -- ``autobot_shared`` is the one
package both can reach -- so a new family is added once.
"""

from typing import Any, List

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


def is_fact_key(key: Any) -> bool:
    """True for a real ``fact:<id>`` hash; the other ``fact:`` key families share the scan prefix and are not hashes.

    Fact ids legitimately contain ``:`` (``claude_code_memory:<owner>:<slug>``, connector ``<src>:<id>:file:<path>``,
    ``ext:...``, ``stream:...``), so a colon cannot be the discriminator. A key is a fact hash unless it starts
    with one of :data:`NON_HASH_FACT_PREFIXES`. A prefix test is chosen over a pipelined ``TYPE`` check because it
    costs no round trip and no production id starts with one of those four namespaced prefixes. A WRONGTYPE
    ``hgetall`` on a non-hash family would fail the whole pipelined batch.
    """
    text = key.decode("utf-8") if isinstance(key, bytes) else key
    return text.startswith("fact:") and not text.startswith(NON_HASH_FACT_PREFIXES)


def fact_keys_only(keys: Any) -> List[Any]:
    """*keys* without the non-hash ``fact:`` families: the filter for a ``fact:*`` SCAN/KEYS that reads hashes."""
    return [k for k in keys if is_fact_key(k)]
