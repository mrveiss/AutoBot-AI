# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared ChromaDB ``where`` evaluator and its GPU-path caller (#18874)."""

import pytest

from autobot_shared.ssot_config import config
from knowledge.backends.where_filter import matches_where
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER

M = {"a": 5, "s": "x"}


@pytest.mark.parametrize(
    "where,expected",
    [
        ({}, True),
        (None, True),
        ({"a": 5}, True),
        ({"a": 6}, False),
        ({"missing": 5}, False),
        ({"a": 5, "s": "x"}, True),
        ({"a": 5, "s": "y"}, False),
        ({"a": {"$eq": 5}}, True),
        ({"a": {"$eq": 6}}, False),
        ({"a": {"$ne": 6}}, True),
        ({"a": {"$ne": 5}}, False),
        ({"missing": {"$ne": 5}}, True),
        ({"missing": {"$eq": 5}}, False),
        ({"a": {"$gt": 4}}, True),
        ({"a": {"$gt": 5}}, False),
        ({"a": {"$gte": 5}}, True),
        ({"a": {"$gte": 6}}, False),
        ({"a": {"$lt": 6}}, True),
        ({"a": {"$lt": 5}}, False),
        ({"a": {"$lte": 5}}, True),
        ({"a": {"$lte": 4}}, False),
        ({"missing": {"$gt": 1}}, False),
        ({"s": {"$gt": 1}}, False),
        ({"a": {"$in": [1, 5]}}, True),
        ({"a": {"$in": [1, 2]}}, False),
        ({"missing": {"$in": [1]}}, False),
        ({"a": {"$nin": [1, 2]}}, True),
        ({"a": {"$nin": [5]}}, False),
        ({"missing": {"$nin": [5]}}, True),
        ({"a": {"$gt": 1, "$lt": 9}}, True),
        ({"a": {"$gt": 1, "$lt": 3}}, False),
        ({"$and": [{"a": 5}, {"s": "x"}]}, True),
        ({"$and": [{"a": 5}, {"s": "y"}]}, False),
        ({"$or": [{"a": 1}, {"s": "x"}]}, True),
        ({"$or": [{"a": 1}, {"s": "y"}]}, False),
        ({"$and": [{"$or": [{"a": 1}, {"a": 5}]}, {"s": {"$ne": "y"}}]}, True),
        ({"$or": [{"a": 1}, {"$and": [{"a": 5}, {"s": "y"}]}]}, False),
        ({"$and": []}, False),
        ({"$or": []}, False),
        ({"$and": "nope"}, False),
    ],
)
def test_operator_semantics(where, expected):
    assert matches_where(M, where) is expected


@pytest.mark.parametrize(
    "where",
    [{"a": {"$regex": "5"}}, {"a": {"$ne": 6, "$bogus": 1}}, {"$not": {"a": 5}}, {"a": {}}, {"a": {"$in": 5}}],
)
def test_unknown_or_malformed_fails_closed(where):
    assert matches_where(M, where) is False


def test_none_metadata_treated_as_empty():
    assert matches_where(None, {"a": {"$ne": 1}}) is True
    assert matches_where(None, {"a": 1}) is False


def test_quarantine_filter_excludes_quarantined_and_admits_normal():
    q = config.research_quarantine_collection
    assert matches_where({"collection": q}, RESEARCH_QUARANTINE_FILTER) is False
    assert matches_where({"collection": "general"}, RESEARCH_QUARANTINE_FILTER) is True
    assert matches_where({}, RESEARCH_QUARANTINE_FILTER) is True  # predates the field


def test_gpu_path_matches_filter_delegates():
    from utils.gpu_vector_search import HybridVectorSearch

    hs = HybridVectorSearch()
    q = config.research_quarantine_collection
    assert hs._matches_filter({"collection": "general"}, RESEARCH_QUARANTINE_FILTER) is True
    assert hs._matches_filter({"collection": q}, RESEARCH_QUARANTINE_FILTER) is False
    assert hs._matches_filter({"a": 1}, {"a": {"$bogus": 1}}) is False
