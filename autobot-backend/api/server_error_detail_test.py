# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Server-side failures never interpolate exception text into the client-visible ``detail`` (#17601)."""

import re
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parent
_LEAK = re.compile(r"detail=f[\"'].*\{(?:str\()?(?:e|exc)\)?\}")
_FILES = [
    "knowledge_chroma.py",
    "chat.py",
    "analytics.py",
    "diagnostics.py",
    "mcp_registry.py",
    "knowledge_site_map.py",
    "onboarding.py",
    "skills_hub.py",
    "marketplace_sources.py",
]


@pytest.mark.parametrize("name", _FILES)
def test_no_exception_text_in_a_client_detail(name):
    leaks = [ln for ln in (_API / name).read_text(encoding="utf-8").splitlines() if _LEAK.search(ln)]
    # marketplace_sources keeps the two user-facing parse messages (JSON / schema invalid) by design
    allowed = 2 if name == "marketplace_sources.py" else 0
    assert len(leaks) == allowed, leaks
    assert _LEAK.search('detail=f"x: {exc}"')  # contrast: the pattern does catch a leak
