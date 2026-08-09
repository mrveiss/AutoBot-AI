# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Background vectorization must read the fact's real content (#13274).

Facts are written by ``KnowledgeBase`` with ``hset(fact_key, mapping={"content":
..., "metadata": ...})`` — ``str`` field names — and ``kb.redis()`` is the shared
async client built with ``decode_responses=True``
(``redis_management/connection_manager.py:500`` -> ``config.py:61,153``). So
``hgetall(fact_key)`` returns a ``str``-keyed dict.

``BackgroundVectorizer._extract_fact_content`` probed it with bytes literals::

    content_bytes = fact_data.get(b"content", b"")
    content = self._decode_bytes(content_bytes)

``b"content"`` never matched, so the ``b""`` default came back, ``_decode_bytes``
decoded it to ``""`` without complaint, and metadata fell back to ``{}``. Every
fact was inserted into the vector index as an **empty** ``Document`` and then
marked ``vectorization_status=completed`` — poisoning the index while reporting
success. Sibling readers of the same hash (``api/knowledge.py:2168``,
``knowledge/search_components/keyword_search.py:121``) already probe both key
types, which is why only this path silently produced empty documents.
"""

import json

from background_vectorization import BackgroundVectorizer

# Exactly the mapping KnowledgeBase.store_fact writes (knowledge/facts.py:644).
STORED_FACT = {
    "content": "Redis keys are bytes on the wire but str on a decoding client.",
    "metadata": json.dumps({"source": "manual", "tags": ["redis"]}),
    "timestamp": "2026-08-02T07:00:00+00:00",
}


def test_str_keyed_fact_yields_real_content():
    """The live configuration. Pre-fix content was "" and metadata was {}."""
    content, metadata = BackgroundVectorizer()._extract_fact_content(dict(STORED_FACT))

    assert content == STORED_FACT["content"]
    assert metadata == {"source": "manual", "tags": ["redis"]}


def test_empty_content_is_not_silently_vectorized():
    """Pin the exact symptom: a real fact must never arrive as an empty document."""
    content, _metadata = BackgroundVectorizer()._extract_fact_content(dict(STORED_FACT))

    assert content != "", "every fact was being vectorized as an empty Document"
    assert len(content.split()) > 1


def test_bytes_values_still_decode():
    """``_decode_bytes`` keeps handling a bytes value under the correct str key."""
    raw = {k: v.encode() for k, v in STORED_FACT.items()}

    content, metadata = BackgroundVectorizer()._extract_fact_content(raw)

    assert content == STORED_FACT["content"]
    assert metadata == {"source": "manual", "tags": ["redis"]}


def test_missing_fields_fall_back_to_documented_defaults():
    """A hash with neither field yields "" / {} rather than raising."""
    content, metadata = BackgroundVectorizer()._extract_fact_content({"timestamp": "x"})

    assert content == ""
    assert metadata == {}
