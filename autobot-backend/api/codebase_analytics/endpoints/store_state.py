# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a read endpoint can tell a panel about the code index store (#17651).

A panel has four things to say, and they are four different answers:

* the store could not be read           -> HTTP 503 (``store_unavailable``)
* the source was never indexed          -> ``status: "no_data"``, ``indexed: false``
* indexed, but nothing of this kind     -> ``status: "success"``, ``indexed: true``, empty list
* indexed, with results                 -> ``status: "success"``, ``indexed: true``

Endpoints used to answer the first two with the same empty list, so a Chroma
outage and a source nobody had indexed both rendered as a blank panel.
"""

from fastapi import HTTPException, status

STORE_UNAVAILABLE_DETAIL = "Code index store unavailable"
NOT_INDEXED_MESSAGE = "This source has not been indexed yet. Run indexing first."


def store_unavailable() -> HTTPException:
    """The one response for an unreadable code index store; the cause is logged by the caller."""
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=STORE_UNAVAILABLE_DETAIL)


def source_is_indexed(collection, source_id: str | None) -> bool:
    """True when the store holds at least one row of any type for ``source_id``.

    Any row counts, whatever its ``type``: this answers "was it indexed", not
    "did it contain functions". A read failure propagates; it is not "not indexed".
    """
    where = {"source_id": source_id} if source_id else None
    found = collection.get(where=where, limit=1, include=[])
    return bool(found.get("ids"))


def index_state(collection, source_id: str | None, has_results: bool) -> dict:
    """The ``status``/``indexed`` fields for a list response (never reads the store when results exist)."""
    indexed = has_results or source_is_indexed(collection, source_id)
    if indexed:
        return {"status": "success", "indexed": True}
    return {"status": "no_data", "indexed": False, "message": NOT_INDEXED_MESSAGE}
