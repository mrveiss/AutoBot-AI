# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The analytics dedup key goes through the one content digest, byte-identical (#15722)."""

import hashlib

import pytest

from code_intelligence.analytics_infrastructure import AnalyticsInfrastructureMixin


@pytest.mark.parametrize("content", ["", "def f():\n    return 1\n", "ünïcödé — 漢字", "/srv/project/src"])
def test_key_is_unchanged_from_the_inline_digest(content: str) -> None:
    previous = hashlib.sha256(content.encode()).hexdigest()[:16]

    assert AnalyticsInfrastructureMixin._generate_content_hash(None, content) == previous
