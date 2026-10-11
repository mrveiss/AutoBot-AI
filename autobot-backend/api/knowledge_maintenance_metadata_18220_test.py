# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Maintenance jobs skip a fact with non-object metadata and carry on with the rest (#18220)."""

import json
import logging

import pytest

from api import knowledge_maintenance as mod

GOOD = json.dumps(
    {"fact_id": "g", "category": "c", "title": "t", "file_path": "/nonexistent/x", "source_session_id": "s"}
)
BAD = ["[1, 2]", '"owner"', "42", "null", "{not json"]


@pytest.mark.parametrize("bad", BAD)
def test_dedup_grouping_skips_the_bad_fact_and_keeps_the_rest(bad, caplog):
    batch = [(b"fact:a", GOOD), (b"fact:bad", bad), (b"fact:b", GOOD)]
    with caplog.at_level(logging.WARNING):
        infos = [mod._process_fact_metadata(m, k, "2026-01-01") for k, m in batch]
    assert [i is not None for i in infos] == [True, False, True]
    assert any("fact:bad" in r.getMessage() for r in caplog.records)
    assert not any(bad in r.getMessage() for r in caplog.records if bad not in ("42", "null"))


@pytest.mark.parametrize("bad", BAD)
def test_orphan_check_skips_the_bad_fact_and_keeps_the_rest(bad):
    batch = [("fact:a", GOOD), ("fact:bad", bad), ("fact:b", GOOD)]
    results = [mod._check_orphaned_fact(k, m) for k, m in batch]
    assert [r[0] for r in results] == [True, False, True]
    assert results[1] == (False, False, None)
    assert results[0][1] is True  # the path does not exist: the rest are still judged


@pytest.mark.parametrize("bad", BAD)
def test_session_orphan_parse_skips_the_bad_fact(bad):
    parsed = [
        mod._parse_fact_metadata({b"metadata": m.encode()}, k) for k, m in [(b"fact:a", GOOD), (b"fact:bad", bad)]
    ]
    assert parsed[0]["source_session_id"] == "s"
    assert parsed[1] is None
