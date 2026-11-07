# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one SHA-256-of-content computation (#15722, umbrella #13916).

Before this module the same digest was written inline at a dozen sites, in two
widths, under the same name (``content_hash``) in two places:

* ``knowledge/connectors/content_extraction.py`` -- full 64-char digest, change detection
* ``knowledge/fact_store.py`` -- first 16 chars, the fact deduplication key

Both are *the same function* of the content; they differ only in how much of the
digest is kept. That difference is the explicit ``width`` parameter below, so a caller
states which form it stores instead of picking one of two same-named functions.

Stored values are never recomputed differently: ``content_digest(c)`` is the full hex
digest of ``c.encode("utf-8")`` and ``content_digest(c, width=n)`` is its first ``n``
characters -- byte-identical to what each site wrote before. The fact dedup key is
``content_digest(c, width=FACT_DEDUP_WIDTH)`` and nothing else derives it, so the
write path, the delete path and the Redis/Postgres projection cannot drift apart.

Not this function: ``services/content_fingerprint.compute_fingerprint`` hashes
whitespace-normalised text, a different input, so it is a different value by design.
"""

from __future__ import annotations

import hashlib

#: Characters of the digest kept in the fact deduplication key (``content_hash:<key>``).
#: Declared once; the Redis index and the ``knowledge_facts.content_hash`` column share it.
FACT_DEDUP_WIDTH = 16


def content_digest(content: str | bytes, *, width: int | None = None) -> str:
    """Hex SHA-256 of *content* (str is encoded UTF-8); first *width* chars when given."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    digest = hashlib.sha256(data).hexdigest()
    return digest if width is None else digest[:width]


def fact_dedup_key(content: str) -> str:
    """The fact deduplication key: the first ``FACT_DEDUP_WIDTH`` chars of the content digest."""
    return content_digest(content, width=FACT_DEDUP_WIDTH)
