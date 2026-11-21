# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``VITE_SLM_API_TIMEOUT_MS`` is read by both frontends with the same default (#21810).

ARCHITECTURE_EXCEPTIONS.md, "SLM API Timeout": ADR-012 keeps the SLM a separate app, so the setting is
declared twice on purpose. This guard fails when the two defaults drift or a read site disappears.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

SITES = (
    "autobot-frontend/src/utils/slmClient.ts",
    "autobot-slm-frontend/src/utils/ApiClient.ts",
)
_READ = re.compile(r"getEnvPositiveInt\(\s*import\.meta\.env,\s*'VITE_SLM_API_TIMEOUT_MS',\s*([\d_]+)\s*\)")


def _default(text: str) -> int | None:
    match = _READ.search(text)
    return int(match.group(1).replace("_", "")) if match else None


def _defaults() -> dict[str, int | None]:
    root = repo_root()
    return {s: _default((root / s).read_text(encoding="utf-8")) for s in SITES}


def test_both_sites_read_the_variable_with_a_default():
    assert all(v is not None for v in _defaults().values()), _defaults()


def test_the_two_defaults_are_equal():
    assert len(set(_defaults().values())) == 1, _defaults()


def test_detector_reads_a_default():
    src = "getEnvPositiveInt(import.meta.env, 'VITE_SLM_API_TIMEOUT_MS', 45_000)"
    assert _default(src) == 45000
    assert _default("const X = 1") is None
