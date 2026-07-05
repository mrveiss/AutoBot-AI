# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from datetime import datetime, timezone

import pytest

from source_attribution import Source, SourceReliability, SourceType


@pytest.mark.parametrize("member,value", [
    ("YOUTUBE", "youtube"),
    ("REDDIT", "reddit"),
    ("WEB_PAGE", "web_page"),
    ("SOCIAL", "social"),
])
def test_new_source_types_exist(member, value):
    assert SourceType[member].value == value


def test_new_source_types_have_citation_icons():
    for member in ("YOUTUBE", "REDDIT", "WEB_PAGE", "SOCIAL"):
        src = Source(
            type=SourceType[member],
            reliability=SourceReliability.MEDIUM,
            content="c",
            timestamp=datetime.now(tz=timezone.utc),
            metadata={"name": "x"},
        )
        # Non-default icon means the type was added to the icon map.
        assert not src.format_citation().startswith("📋")
