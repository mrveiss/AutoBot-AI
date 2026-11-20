# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chroma clients whose every collection takes the per-collection write lease before it writes (#20992).

One choke point: ``get_chromadb_client`` and ``get_async_chromadb_client`` return a :class:`LeasedChromaClient`,
so every collection handle they give out -- the async wrapper, the ``knowledge.backends`` adapters and the raw
handle LlamaIndex's ``ChromaVectorStore`` writes through -- leases ``add``/``upsert``/``update``/``delete``.
The lease lives in ``autobot_shared.coordination.collection_lease``; this module only applies it.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.coordination.collection_lease import CollectionLeaseUnavailable, delete_lease, write_lease

_WRITES = ("add", "upsert", "update", "delete")


class LeasedChromaCollection:
    """A Chroma collection that holds the write lease around each write; everything else passes through."""

    def __init__(self, raw: Any) -> None:
        object.__setattr__(self, "_raw", raw)

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._raw, attr)

    def __setattr__(self, attr: str, value: Any) -> None:
        setattr(self._raw, attr, value)

    def _leased(self, op: str, *args: Any, **kwargs: Any) -> Any:
        with write_lease(self._raw.name) as lease:
            lease.ensure_held()
            return getattr(self._raw, op)(*args, **kwargs)

    def add(self, *args: Any, **kwargs: Any) -> Any:
        return self._leased("add", *args, **kwargs)

    def upsert(self, *args: Any, **kwargs: Any) -> Any:
        return self._leased("upsert", *args, **kwargs)

    def update(self, *args: Any, **kwargs: Any) -> Any:
        return self._leased("update", *args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        return self._leased("delete", *args, **kwargs)


def _lease(collection: Any) -> Any:
    if isinstance(collection, LeasedChromaCollection) or not all(hasattr(collection, op) for op in _WRITES):
        return collection
    return LeasedChromaCollection(collection)


class LeasedChromaClient:
    """A Chroma client whose collections are leased; everything else passes through."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._raw, attr)

    def get_collection(self, *args: Any, **kwargs: Any) -> Any:
        return _lease(self._raw.get_collection(*args, **kwargs))

    def get_or_create_collection(self, *args: Any, **kwargs: Any) -> Any:
        return _lease(self._raw.get_or_create_collection(*args, **kwargs))

    def create_collection(self, *args: Any, **kwargs: Any) -> Any:
        return _lease(self._raw.create_collection(*args, **kwargs))

    def list_collections(self, *args: Any, **kwargs: Any) -> Any:
        return [_lease(c) for c in self._raw.list_collections(*args, **kwargs)]


def lease_client(client: Any) -> Any:
    """*client* with leased collections; idempotent."""
    return client if isinstance(client, LeasedChromaClient) else LeasedChromaClient(client)


def delete_if_empty(client: Any, name: str) -> int:
    """Delete *name* only if it is empty, under its exclusive lease; returns the count seen (0 = deleted).

    Blocking: call it from a worker thread. The thread runs to completion even if the awaiting task is
    cancelled, so the lease is always released and the outcome is delete-or-nothing. The lease is re-checked
    between the count and the delete: one that lapsed in between means "did not run".
    """
    with delete_lease(name) as lease:
        count = client.get_collection(name=name).count()
        if count != 0:
            return count
        if not lease.still_held():
            raise CollectionLeaseUnavailable(name, "the delete lease lapsed after the count; nothing deleted")
        client.delete_collection(name=name)
        return 0
