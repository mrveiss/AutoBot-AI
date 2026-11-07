# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The former ``content_hash`` copies are served by the one canonical digest (#18459, #15722).

Two module-level ``content_hash`` definitions used to exist:

* ``knowledge/connectors/content_extraction.py``: full SHA-256 hex of the UTF-8 text, used by the
  connectors for change detection. It was deleted; the connectors call ``content_digest`` directly.
* ``knowledge/fact_store.py``: the fact deduplication key. It now delegates to ``fact_dedup_key``.

The structural guard (``repo_tests/one_content_digest_15722_test.py``) proves each name exists once.
These tests prove the *callers* still get the values the old copies produced.
"""

from __future__ import annotations

import hashlib

import pytest

from autobot_shared.content_digest import FACT_DEDUP_WIDTH, content_digest, fact_dedup_key
from knowledge import fact_store

_SAMPLES = ("", "plain ascii", "ünïcödé — ✓", "line one\nline two\n", "x" * 10_000)


def _old_connector_content_hash(text: str) -> str:
    """The deleted ``content_extraction.content_hash``, verbatim."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("text", _SAMPLES)
def test_the_connector_digest_equals_the_deleted_copy(text: str) -> None:
    assert content_digest(text) == _old_connector_content_hash(text)


@pytest.mark.parametrize("text", _SAMPLES)
def test_the_fact_store_content_hash_is_the_canonical_dedup_key(text: str) -> None:
    key = fact_store.content_hash(text)
    assert key == fact_dedup_key(text)
    assert key == _old_connector_content_hash(text)[:FACT_DEDUP_WIDTH]


def test_the_dedup_key_is_pinned_to_a_literal() -> None:
    """A change of hash family or width fails here, not just a change of who computes it."""
    assert fact_store.content_hash("a") == "ca978112ca1bbdca"


@pytest.mark.parametrize("text", _SAMPLES)
def test_the_fact_row_stores_the_old_algorithms_value(text: str) -> None:
    """Through the former call site: the row builder writes what the old copy produced."""
    row = fact_store._row_values(text, {})
    assert row["content_hash"] == _old_connector_content_hash(text)[:FACT_DEDUP_WIDTH]


def test_the_row_hashes_the_pre_redaction_content_when_given() -> None:
    row = fact_store._row_values("redacted", {}, hash_content="raw secret")
    assert row["content_hash"] == _old_connector_content_hash("raw secret")[:FACT_DEDUP_WIDTH]


def test_different_content_gets_a_different_key() -> None:
    """Contrast: a constant would satisfy the equalities above only if both sides were broken alike."""
    assert fact_store.content_hash("a") != fact_store.content_hash("b")
