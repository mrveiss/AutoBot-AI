#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One endpoint-normalisation rule, and the ordering bug the fork had (#18093).

`autobot_shared/monitoring/metrics/frontend.py` carried a second `_normalize_endpoint`
that ran `re.sub(r"/\\d+", "/{id}")` BEFORE its uuid pattern. The numeric substitution ate
a uuid's leading digits, so the uuid pattern could never match afterwards. The reject
rows below are that bug, asserted as the behaviour the shared rule must NOT have.
"""

import re

import pytest

from autobot_shared.endpoint_normalization import DYNAMIC_SEGMENT_PATTERNS, collapse_dynamic_segments


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/users/42", "/api/users/{id}"),
        ("/api/x/123e4567-e89b-12d3-a456-426614174000", "/api/x/{id}"),
        ("/api/x/123E4567-E89B-12D3-A456-426614174000", "/api/x/{id}"),
        ("/api/commits/4b9a5487f8a1c2d3e4f5a6b7c8d9e0f1a2", "/api/commits/{id}"),
        ("/api/sessions/sess1234abcd", "/api/sessions/{id}"),
        ("/api/a/1/b/2", "/api/a/{id}/b/{id}"),
        ("", ""),
        ("/", "/"),
    ],
)
def test_dynamic_segments_collapse(path: str, expected: str) -> None:
    assert collapse_dynamic_segments(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "/api/settings",
        "/api/v2/health",
        "/api/knowledge_base/search",
        "/api/ai-stack/rag/query",
        "/",
        "/api/users/me",
    ],
)
def test_static_paths_are_untouched(path: str) -> None:
    """A short word slug is not an id. `v2` has a letter and a digit but is 2 chars."""
    assert collapse_dynamic_segments(path) == path


def test_a_uuid_is_collapsed_despite_its_leading_digits() -> None:
    """The fork's bug, pinned.

    `re.sub(r"/\\d+", "/{id}")` applied first turned
    `/api/x/123e4567-e89b-...` into `/api/x/{id}e4567-e89b-...`, after which no uuid
    pattern could match. Per-segment classification is what makes this impossible: a
    segment is decided once.
    """
    broken = re.sub(r"/\d+", "/{id}", "/api/x/123e4567-e89b-12d3-a456-426614174000")
    assert broken == "/api/x/{id}e4567-e89b-12d3-a456-426614174000", "control: the old ordering"
    assert collapse_dynamic_segments("/api/x/123e4567-e89b-12d3-a456-426614174000") == "/api/x/{id}"


def test_sha_like_hex_is_collapsed() -> None:
    """The monitoring copy had no pattern for this at all, so a commit SHA in a path
    produced one `endpoint` label value per commit."""
    assert collapse_dynamic_segments("/api/commits/4b9a5487f8a1c2d3e4f5a6b7c8d9e0f1a2") == "/api/commits/{id}"


def test_a_query_string_survives_on_a_segment_that_is_not_replaced() -> None:
    """Deliberate asymmetry, preserving `analytics_controller`'s existing keys.

    The segment is MATCHED against its query-stripped form, but a segment that is not
    replaced is returned verbatim. Stripping the query globally would change the
    endpoint keys that caller already records.
    """
    assert collapse_dynamic_segments("/api/search?q=x") == "/api/search?q=x"
    assert collapse_dynamic_segments("/api/users/42?full=1") == "/api/users/{id}"


def test_the_placeholder_is_configurable_but_defaults_to_one_spelling() -> None:
    """The fork emitted `{uuid}` for uuids and `{id}` for numbers -- two label values
    for one concept. One default spelling, and no caller passes another."""
    assert collapse_dynamic_segments("/api/users/42") == "/api/users/{id}"
    assert collapse_dynamic_segments("/api/users/42", placeholder="{n}") == "/api/users/{n}"


def test_the_pattern_order_is_load_bearing_and_documented() -> None:
    """First match wins, so uuid must precede the long-hex rule.

    A uuid's first group is 8 hex chars; the long-hex rule needs 16+, so they do not
    actually collide -- but a future edit that loosened long-hex to 8+ would silently
    reclassify every uuid. Asserted so that edit fails here.
    """
    assert len(DYNAMIC_SEGMENT_PATTERNS) == 4
    uuid_rule, long_hex_rule = DYNAMIC_SEGMENT_PATTERNS[0], DYNAMIC_SEGMENT_PATTERNS[1]
    assert uuid_rule.search("123e4567-e89b-12d3-a456-426614174000")
    assert not long_hex_rule.search("123e4567")
