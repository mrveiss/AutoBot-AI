# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``AUTOBOT_KB_CHUNK_MAX_TOKENS`` honours its registered range (50, 100000) (#17530)."""

import importlib

import pytest

import knowledge.document_ingest as ingest


@pytest.fixture(autouse=True)
def _restore():
    yield
    importlib.reload(ingest)


@pytest.mark.parametrize(
    "raw,expected", [("0", 50), ("-5", 50), ("10", 50), ("9999999", 100000), ("junk", 800), ("1200", 1200)]
)
def test_chunk_budget_is_clamped(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("AUTOBOT_KB_CHUNK_MAX_TOKENS", raw)
    assert importlib.reload(ingest).KB_CHUNK_MAX_TOKENS == expected
