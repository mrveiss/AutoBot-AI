# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend Vue ``<script>`` body pattern is defined once, in ``autobot_shared/vue_sfc.py`` (#21641).

Detected: a ``_VUE_SCRIPT_RE`` definition or the old ``<script[^>]*>([\\s\\S]*?)</script`` text in tracked
backend/shared ``.py`` outside the owner. NOT detected: a differently spelled equivalent pattern.
"""

from __future__ import annotations

import pytest
from repo_tests._paths import repo_root

from autobot_shared.vue_sfc import VUE_SCRIPT_RE
from tools.lint._scan_helpers import tracked_paths

OWNER = "autobot_shared/vue_sfc.py"
SELF = "repo_tests/vue_script_regex_single_21641_test.py"
NEEDLES = ("_VUE_SCRIPT_RE =", "_VUE_SCRIPT_RE:", "<script[^>]*>([")


def test_the_pattern_is_defined_in_one_module_only():
    root = repo_root()
    paths = [p for p in tracked_paths(root, "autobot-backend", "autobot_shared") if p.endswith(".py")]
    assert paths, "no tracked python found; the scan would pass vacuously"
    found = [
        p for p in paths if p not in (OWNER, SELF) and any(n in (root / p).read_text(encoding="utf-8") for n in NEEDLES)
    ]
    assert found == []


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
    match = VUE_SCRIPT_RE.search(source)
    assert match and match.group(1) == "BODY"


def test_a_lookalike_tag_is_not_a_script():
    assert VUE_SCRIPT_RE.search("<scripts>BODY</scripts>") is None
