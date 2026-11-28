# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``and_where`` is the one AND-combinator; a caller filter narrows quarantine, never replaces it (#18946)."""

from __future__ import annotations

from autobot_shared.ssot_config import config
from knowledge.backends import InMemoryClient
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER, with_quarantine
from knowledge.where_combine import and_where

A = {"a": 1}
B = {"b": 2}


def test_none_and_empty_clauses_are_dropped():
    assert and_where(None, {}) is None
    assert and_where() is None
    assert and_where(None, A, {}) == A


def test_single_clause_is_returned_unwrapped():
    assert and_where(A) == A


def test_two_clauses_are_anded():
    assert and_where(A, B) == {"$and": [A, B]}


def test_an_existing_and_is_flattened_not_nested():
    assert and_where({"$and": [A, B]}, {"c": 3}) == {"$and": [A, B, {"c": 3}]}
    assert and_where({"$and": [A]}, None) == A


def test_no_caller_filter_is_the_bare_quarantine_filter():
    assert with_quarantine(None) == RESEARCH_QUARANTINE_FILTER
    assert with_quarantine({}) == RESEARCH_QUARANTINE_FILTER


def _collection():
    c = InMemoryClient().get_or_create_collection("where_combine_18946_test")
    c.add(
        ids=["ok", "bad"],
        metadatas=[
            {"category": "docs", "collection": "main"},
            {"category": "docs", "collection": config.research_quarantine_collection},
        ],
    )
    return c


def test_caller_filter_does_not_leak_a_quarantined_fact():
    assert set(_collection().get(where=with_quarantine({"category": "docs"}))["ids"]) == {"ok"}


def test_caller_filter_still_narrows():
    assert set(_collection().get(where=with_quarantine({"category": "other"}))["ids"]) == set()
