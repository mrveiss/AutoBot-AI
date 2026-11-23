# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend Vue ``<script>`` body extractor is defined once, in ``autobot_shared/vue_sfc.py`` (#21641).

Detected: a ``_VUE_SCRIPT_RE`` or ``vue_script_body`` definition, or the old ``<script[^>]*>([\\s\\S]*?)</script``
text, in tracked backend/shared ``.py`` outside the owner. NOT detected: a differently spelled equivalent pattern.
The extractor is linear-time: a lazy-body regex is polynomial on many unclosed tags (CodeQL py/polynomial-redos).
"""

from __future__ import annotations

import time

import pytest
from repo_tests._paths import repo_root

from autobot_shared.vue_sfc import vue_script_body
from tools.lint._scan_helpers import tracked_paths

OWNER = "autobot_shared/vue_sfc.py"
SELF = "repo_tests/vue_script_regex_single_21641_test.py"
NEEDLES = ("_VUE_SCRIPT_RE =", "_VUE_SCRIPT_RE:", "<script[^>]*>([", "def vue_script_body")


def defines_the_pattern(text: str) -> bool:
    """Whether *text* holds a local definition of the extractor (an import of ``vue_script_body`` is not one)."""
    return any(n in text for n in NEEDLES)


def test_the_pattern_is_defined_in_one_module_only():
    root = repo_root()
    paths = [p for p in tracked_paths(root, "autobot-backend", "autobot_shared") if p.endswith(".py")]
    assert paths, "no tracked python found; the scan would pass vacuously"
    found = [p for p in paths if p not in (OWNER, SELF) and defines_the_pattern((root / p).read_text(encoding="utf-8"))]
    assert found == []


def test_a_local_definition_trips_the_detector():
    assert defines_the_pattern('_VUE_SCRIPT_RE = re.compile(r"<script[^>]*>([\\s\\S]*?)</script>")')
    assert defines_the_pattern('m = re.search(r"<script[^>]*>([\\s\\S]*?)</script>", code)')
    assert defines_the_pattern("def vue_script_body(text):\n    return None")


def test_an_import_of_the_shared_pattern_does_not_trip_it():
    assert not defines_the_pattern("from autobot_shared.vue_sfc import vue_script_body\nvue_script_body(code)")


@pytest.mark.parametrize(
    "source",
    [
        "<script>BODY</script>",
        "<SCRIPT lang='ts'>BODY</SCRIPT>",
        "<script setup>BODY</script >",
        "<script>BODY</script foo='x'>",
        "<script>BODY</SCRIPT\n>",
    ],
)
def test_the_body_is_extracted_whatever_the_closing_tag_looks_like(source):
    assert vue_script_body(source) == "BODY"


def test_a_lookalike_tag_is_not_a_script():
    assert vue_script_body("<scripts>BODY</scripts>") is None


@pytest.mark.parametrize(
    "source", ["<script>BODY", "BODY</script>", "<script", "<script>BODY</script", "<script>BODY</scripts>"]
)
def test_an_unclosed_or_unopened_script_has_no_body(source):
    assert vue_script_body(source) is None


def test_the_first_script_element_wins():
    assert vue_script_body("<scripts><script>A</script><script>B</script>") == "A"


@pytest.mark.parametrize(
    "source", ["<script " * 50_000, "<script>" + "</script" * 50_000, "<script>" + "</scriptx" * 50_000]
)
def test_many_unclosed_tags_take_linear_time(source):
    start = time.perf_counter()
    vue_script_body(source)
    assert time.perf_counter() - start < 1.0, "the extractor re-scans the input per tag"
